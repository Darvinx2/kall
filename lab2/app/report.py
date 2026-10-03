"""Отчёт лабы №2: три хранилища подряд.

Задание: «извлечь отчёт о необходимом объёме аудитории для проведения
занятий по курсу заданного семестра и года обучения с требованиями
в описании к использованию технических средств. Вывести полную информацию
о курсе, лекции и количестве слушателей».

«Необходимый объём аудитории» — это количество слушателей: сколько человек
надо вместить. Вместимость самих аудиторий в схеме не хранится, задание её
и не требует.

Способ извлечения:

1. Elasticsearch — по описанию требований к техническим средствам отдаёт
   id занятий. Требование продублировано в поле computer_type (keyword,
   точный фильтр) и в тексте аннотации, поэтому один запрос находит и
   значение поля, и упоминание в описании занятия. Фильтр по семестру — там
   же.
2. PostgreSQL — по отобранным занятиям считает слушателей и отдаёт полную
   информацию о курсе и лекции. Запрос повторяет audienceReport из
   Go-реализации university: соединяет lecture -> lecture_course -> schedule
   -> student_group -> student, фильтрует по семестру курса и году набора
   группы, count(DISTINCT student) даёт число слушателей.
3. MongoDB — документ курса (courses) со вложенными лекциями: «полная
   информация о курсе» одним findOne, без сборки из нескольких таблиц.
"""

from elasticsearch import AsyncElasticsearch
from motor.motor_asyncio import AsyncIOMotorDatabase
from psycopg_pool import AsyncConnectionPool

__all__ = ("build_report",)

LECTURES_INDEX = "lectures"
COURSES_COLLECTION = "courses"

# Число слушателей по занятию + полная информация о курсе и лекции.
# Структура запроса повторяет audienceReport из Go-проекта university.
LISTENERS_SQL = """
    SELECT c.id::text          AS course_id,
           c.name              AS course_name,
           c.description       AS description,
           c.semester          AS semester,
           c.total_hours       AS total_hours,
           c.lecture_hours     AS lecture_hours,
           c.practice_hours    AS practice_hours,
           c.lab_hours         AS lab_hours,
           l.id::text          AS lecture_id,
           l.title             AS lecture_title,
           l.lecture_type      AS lecture_type,
           l.order_number      AS order_number,
           l.duration_minutes  AS duration_minutes,
           l.computer_type     AS computer_type,
           count(DISTINCT st.id) AS listeners
    FROM lecture l
    JOIN lecture_course c ON c.id = l.course_id
    JOIN schedule sch ON sch.lecture_id = l.id
    JOIN student_group g ON g.id = sch.group_id
    JOIN student st ON st.group_id = g.id
    WHERE l.id = ANY(%(lecture_ids)s::uuid[])
      AND c.semester = %(semester)s
      AND g.enrollment_year = %(enrollment_year)s
    GROUP BY c.id, l.id
    ORDER BY c.name, l.order_number
"""


async def build_report(
    *,
    elastic: AsyncElasticsearch,
    pg_pool: AsyncConnectionPool,
    mongo_db: AsyncIOMotorDatabase,
    technical_requirement: str,
    semester: int,
    enrollment_year: int,
    limit: int,
) -> dict:
    # 1. Elasticsearch: требование к тех. средствам -> id занятий.
    # should с minimum_should_match=1: точное совпадение по computer_type
    # ИЛИ упоминание в тексте аннотации («требования в описании»).
    search = await elastic.search(
        index=LECTURES_INDEX,
        query={
            "bool": {
                "should": [
                    {"term": {"computer_type": technical_requirement}},
                    {"match_phrase": {"annotation": technical_requirement}},
                ],
                "minimum_should_match": 1,
                "filter": [{"term": {"semester": semester}}],
            }
        },
        size=1000,
        source_includes=["lecture_id"],
    )
    lecture_ids = [hit["_source"]["lecture_id"] for hit in search["hits"]["hits"]]
    if not lecture_ids:
        return _empty_report(technical_requirement, semester, enrollment_year)

    # 2. PostgreSQL: число слушателей и данные курса/лекции.
    async with pg_pool.connection() as conn:
        cursor = await conn.execute(
            LISTENERS_SQL,
            {
                "lecture_ids": lecture_ids,
                "semester": semester,
                "enrollment_year": enrollment_year,
            },
        )
        rows = await cursor.fetchall()

    if not rows:
        return _empty_report(technical_requirement, semester, enrollment_year)

    rows = rows[:limit]

    # 3. MongoDB: полная информация о курсе одним документом на курс.
    course_ids = sorted({row[0] for row in rows})
    courses = {
        doc["_id"]: doc
        async for doc in mongo_db[COURSES_COLLECTION].find({"_id": {"$in": course_ids}})
    }

    items = []
    for row in rows:
        (course_id, course_name, description, sem, total_h, lec_h, prac_h, lab_h,
         lecture_id, lecture_title, lecture_type, order_number, duration, computer_type,
         listeners) = row
        course_doc = courses.get(course_id, {})
        items.append(
            {
                "course": {
                    "id": course_id,
                    "name": course_name,
                    "description": description or "",
                    "semester": sem,
                    "total_hours": total_h,
                    "lecture_hours": lec_h,
                    "practice_hours": prac_h,
                    "lab_hours": lab_h,
                    "specialty_name": course_doc.get("specialty", {}).get("name", ""),
                    "specialty_code": course_doc.get("specialty", {}).get("code", ""),
                },
                "lecture": {
                    "id": lecture_id,
                    "title": lecture_title,
                    "lecture_type": lecture_type,
                    "order_number": order_number,
                    "duration_minutes": duration,
                    "computer_type": computer_type or "",
                },
                "listeners": listeners,
            }
        )

    return {
        "technical_requirement": technical_requirement,
        "semester": semester,
        "enrollment_year": enrollment_year,
        "required_capacity": max(item["listeners"] for item in items),
        "items": items,
    }


def _empty_report(technical_requirement: str, semester: int, enrollment_year: int) -> dict:
    return {
        "technical_requirement": technical_requirement,
        "semester": semester,
        "enrollment_year": enrollment_year,
        "required_capacity": 0,
        "items": [],
    }
