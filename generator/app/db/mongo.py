"""MongoDB: документы-композиции.

Раскладка по task.md: «Для MongoDB – документ с данными и составом группы».

    groups   документ группы со вложенным составом студентов и списком курсов
    courses  документ курса со вложенными лекциями

Смысл именно в композиции: «полная информация о группе» (лаба №3) и «полная
информация о курсе» (лаба №2) читаются одним findOne, без сборки из пяти
таблиц. За это платим дублированием — те же данные лежат и в PostgreSQL.

Идентификаторы хранятся строками, а не BSON-UUID. Причина практическая:
pymongo требует для UUID отдельной настройки uuidRepresentation, и значения
перестают совпадать побайтово с тем, что лежит в Redis и Elasticsearch.
Строка одинаково читается всеми пятью хранилищами.
"""

from pymongo import ASCENDING, MongoClient
from pymongo.database import Database

from generator.app.config import get_settings
from generator.app.models import Dataset

__all__ = ("connect", "load", "drop", "GROUPS", "COURSES")

GROUPS = "groups"
COURSES = "courses"


def connect(url: str | None = None) -> MongoClient:
    settings = get_settings()
    return MongoClient(url or settings.mongo_url)


def database(client: MongoClient) -> Database:
    return client[get_settings().mongo_db]


def load(client: MongoClient, data: Dataset) -> None:
    db = database(client)

    specialties = {s.id: s for s in data.specialties}

    students_by_group: dict[str, list[dict]] = {}
    for student in data.students:
        students_by_group.setdefault(str(student.group_id), []).append(
            {
                "id": str(student.id),
                "card_number": student.student_card_number,
                "last_name": student.last_name,
                "first_name": student.first_name,
                "patronymic": student.patronymic,
                "full_name": f"{student.last_name} {student.first_name} {student.patronymic}".strip(),
                "email": student.email,
                "phone": student.phone,
                "status": student.status,
                "enrollment_date": student.enrollment_date.isoformat(),
            }
        )

    courses_by_specialty: dict[str, list[dict]] = {}
    for course in data.courses:
        courses_by_specialty.setdefault(str(course.specialty_id), []).append(
            {
                "id": str(course.id),
                "name": course.name,
                "semester": course.semester,
                "is_elective": course.is_elective,
                "lecture_hours": course.lecture_hours,
            }
        )

    lectures_by_course: dict[str, list[dict]] = {}
    for lecture in sorted(data.lectures, key=lambda x: x.order_number):
        lectures_by_course.setdefault(str(lecture.course_id), []).append(
            {
                "id": str(lecture.id),
                "title": lecture.title,
                "order_number": lecture.order_number,
                "computer_type": lecture.computer_type,
                "tags": lecture.tags,
                "duration_minutes": lecture.duration_minutes,
            }
        )

    def specialty_doc(specialty_id) -> dict:
        specialty = specialties[specialty_id]
        return {
            "id": str(specialty.id),
            "name": specialty.name,
            "code": specialty.code,
            "degree_level": specialty.degree_level,
            "duration_years": specialty.duration_years,
        }

    group_docs = [
        {
            "_id": str(group.id),
            "name": group.name,
            "enrollment_year": group.enrollment_year,
            "curator": group.curator,
            "specialty": specialty_doc(group.specialty_id),
            "students": students_by_group.get(str(group.id), []),
            "students_count": len(students_by_group.get(str(group.id), [])),
            "courses": courses_by_specialty.get(str(group.specialty_id), []),
        }
        for group in data.groups
    ]

    course_docs = [
        {
            "_id": str(course.id),
            "name": course.name,
            "description": course.description,
            "semester": course.semester,
            "is_elective": course.is_elective,
            "is_special_discipline": course.is_special_discipline,
            "hours": {
                "total": course.total_hours,
                "lecture": course.lecture_hours,
                "practice": course.practice_hours,
                "lab": course.lab_hours,
            },
            "specialty": specialty_doc(course.specialty_id),
            "lectures": lectures_by_course.get(str(course.id), []),
            "lectures_count": len(lectures_by_course.get(str(course.id), [])),
        }
        for course in data.courses
    ]

    db[GROUPS].insert_many(group_docs)
    db[COURSES].insert_many(course_docs)

    # Индексы под запросы лаб: по имени группы (лаба №3),
    # по семестру и признаку спец-дисциплины (лабы №2 и №3).
    db[GROUPS].create_index([("name", ASCENDING)], unique=True)
    db[GROUPS].create_index([("specialty.code", ASCENDING)])
    db[GROUPS].create_index([("students.card_number", ASCENDING)])
    db[COURSES].create_index([("semester", ASCENDING)])
    db[COURSES].create_index([("is_special_discipline", ASCENDING)])
    db[COURSES].create_index([("specialty.code", ASCENDING)])


def drop(client: MongoClient) -> None:
    """Удаляет коллекции целиком — вместе с индексами и документами."""
    db = database(client)
    for name in (GROUPS, COURSES):
        db.drop_collection(name)
