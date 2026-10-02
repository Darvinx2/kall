"""Elasticsearch: полнотекстовый поиск по описаниям курсов и лекций.

Раскладка по task.md: «Для ElasticSearch – данные с полнотекстовым описанием
курса».

    lectures  аннотации и тексты материалов + метаданные (теги, тех.
              средства, тип занятия, семестр)
    courses   описания курсов

Elasticsearch здесь — не хранилище, а инвертированный индекс-фильтр: он
возвращает идентификаторы, а дальше работают PostgreSQL, Neo4j и MongoDB.

Главное в маппинге — анализатор `russian`. Без него поиск «нейронных сетей»
не найдёт текст «нейронные сети»: стандартный анализатор не знает русской
морфологии и сравнивает словоформы буквально.
"""

from elasticsearch import Elasticsearch, helpers

from generator.app.config import get_settings
from generator.app.models import Dataset

__all__ = ("connect", "load", "drop", "LECTURES", "COURSES")

LECTURES = "lectures"
COURSES = "courses"

# text  — разбирается на токены, участвует в полнотекстовом поиске
# keyword — хранится целиком, годится для точных фильтров и агрегаций
MAPPINGS: dict[str, dict] = {
    LECTURES: {
        "properties": {
            "lecture_id": {"type": "keyword"},
            "course_id": {"type": "keyword"},
            "course_name": {
                "type": "text",
                "analyzer": "russian",
                "fields": {"raw": {"type": "keyword"}},
            },
            "title": {"type": "text", "analyzer": "russian"},
            # Лаба №1 ищет термин здесь, лаба №2 — упоминание тех. средств.
            "annotation": {"type": "text", "analyzer": "russian"},
            # Тексты всех материалов занятия, склеенные в одно поле:
            # аннотация коротка, содержание занятия живёт в материалах.
            "content_text": {"type": "text", "analyzer": "russian"},
            "materials_count": {"type": "integer"},
            # Лаба №3 фильтрует по тегу — точное совпадение, поэтому keyword.
            "tags": {"type": "keyword"},
            "computer_type": {"type": "keyword"},
            # Лаба №1 считает процент только по лекциям — точный фильтр.
            "lecture_type": {"type": "keyword"},
            "semester": {"type": "integer"},
            "order_number": {"type": "integer"},
            "specialty_code": {"type": "keyword"},
            "specialty_name": {"type": "keyword"},
        }
    },
    COURSES: {
        "properties": {
            "course_id": {"type": "keyword"},
            "name": {
                "type": "text",
                "analyzer": "russian",
                "fields": {"raw": {"type": "keyword"}},
            },
            "description": {"type": "text", "analyzer": "russian"},
            "semester": {"type": "integer"},
            "specialty_code": {"type": "keyword"},
            "specialty_name": {"type": "keyword"},
            "lecture_hours": {"type": "integer"},
            "total_hours": {"type": "integer"},
        }
    },
}


def connect(url: str | None = None) -> Elasticsearch:
    return Elasticsearch(url or get_settings().elastic_url)


def load(client: Elasticsearch, data: Dataset) -> None:
    specialties = {s.id: s for s in data.specialties}
    courses = {c.id: c for c in data.courses}

    for index, mapping in MAPPINGS.items():
        # Маппинг задаётся явно. Если положить документы без него,
        # Elasticsearch выведет типы сам — и annotation получит
        # стандартный анализатор вместо russian.
        client.indices.create(index=index, mappings=mapping)

    # Материалы склеиваются по занятию: в Elasticsearch нет join, а искать
    # нужно по занятию целиком, а не по каждому файлу отдельно.
    materials_by_lecture: dict[str, list[str]] = {}
    for material in data.lecture_materials:
        materials_by_lecture.setdefault(str(material.lecture_id), []).append(
            material.content_text
        )

    lecture_docs = []
    for lecture in data.lectures:
        course = courses[lecture.course_id]
        specialty = specialties[course.specialty_id]
        lecture_docs.append(
            {
                "_index": LECTURES,
                "_id": str(lecture.id),
                "lecture_id": str(lecture.id),
                "course_id": str(course.id),
                "course_name": course.name,
                "title": lecture.title,
                "annotation": lecture.annotation,
                "content_text": " ".join(materials_by_lecture.get(str(lecture.id), [])),
                "materials_count": len(materials_by_lecture.get(str(lecture.id), [])),
                "tags": lecture.tags,
                "computer_type": lecture.computer_type,
                "lecture_type": lecture.lecture_type,
                "semester": course.semester,
                "order_number": lecture.order_number,
                "specialty_code": specialty.code,
                "specialty_name": specialty.name,
            }
        )

    course_docs = [
        {
            "_index": COURSES,
            "_id": str(course.id),
            "course_id": str(course.id),
            "name": course.name,
            "description": course.description,
            "semester": course.semester,
            "specialty_code": specialties[course.specialty_id].code,
            "specialty_name": specialties[course.specialty_id].name,
            "lecture_hours": course.lecture_hours,
            "total_hours": course.total_hours,
        }
        for course in data.courses
    ]

    helpers.bulk(client, lecture_docs)
    helpers.bulk(client, course_docs)

    # Без refresh документы не видны в поиске сразу: индекс обновляется
    # раз в секунду. Для скрипта, после которого сразу идут проверки,
    # это надо форсировать.
    client.indices.refresh(index=[LECTURES, COURSES])


def drop(client: Elasticsearch) -> None:
    """Удаляет индексы целиком — вместе с маппингом и документами."""
    for index in (LECTURES, COURSES):
        client.indices.delete(index=index, ignore_unavailable=True)
