"""Отчёт лабы №1: одна функция, три хранилища подряд.

Задание: «извлечь отчёт о 10 студентах с минимальным процентом посещения
лекций, содержащих заданный термин или фразу, за определённый период
обучения. Состав полей: полная информация о студенте, процент посещения,
период отчёта, термин в занятиях курса».

Способ извлечения:

1. Elasticsearch — по термину отдаёт id лекций и id курсов, которым они
   принадлежат. Обратный индекс с анализатором russian находит любую
   словоформу; в PostgreSQL тот же поиск был бы перебором по ILIKE без
   индекса.
2. Neo4j — по id курсов отдаёт ПАРЫ (студент, курс), а не плоский список
   студентов (обход связи ENROLLED). Пара обязательна: среди отобранных
   курсов есть и выборные, и если просто собрать множество студентов,
   отчёт спутает разные курсы одного студента — тот, кто записан на один
   из совпавших курсов, получит в план ещё и занятия другого совпавшего
   курса, на который не записывался. Пара (student_id, course_id)
   держит эту связь явной вплоть до SQL.
3. PostgreSQL — считает посещаемость по занятиям с отобранными лекциями
   за период, но только по парам (студент, курс) из шага 2 — join идёт
   именно по паре, не по двум независимым спискам. Знаменатель — сами
   занятия из schedule (LEFT JOIN к attendance): если отметки нет, это
   пропуск, а не повод исключить занятие из отчёта. Фильтр по
   week_start_date идёт по ключу партиционирования, поэтому читаются
   только недели из запрошенного диапазона. Карточка студента (ФИО,
   зачётка, группа, специальность) джойнится тут же, к student/
   student_group/specialty — отдельного похода в Redis не нужно.
"""

from datetime import date, timedelta

from elasticsearch import AsyncElasticsearch
from neo4j import AsyncDriver
from psycopg_pool import AsyncConnectionPool

__all__ = ("build_report",)

LECTURES_INDEX = "lectures"

ELIGIBLE_PAIRS_CYPHER = """
    MATCH (st:Student)-[:ENROLLED]->(c:Course)
    WHERE c.id IN $course_ids
    RETURN st.id AS student_id, c.id AS course_id
"""

# eligible — пары (студент, курс) из Neo4j как таблица: unnest двух
# параллельных массивов zip'ует их по позиции. Дальше join идёт по паре
# (e.student_id, e.course_id) = (st.id, l.course_id), а не по двум
# независимым спискам — иначе студент, записанный на один из совпавших
# курсов, получил бы в план и занятия другого совпавшего курса.
ATTENDANCE_SQL = """
    WITH eligible AS (
        SELECT * FROM unnest(%(student_ids)s::uuid[], %(course_ids)s::uuid[])
                 AS e(student_id, course_id)
    )
    SELECT st.id::text              AS student_id,
           st.student_card_number   AS card_number,
           st.last_name             AS last_name,
           st.first_name            AS first_name,
           st.patronymic            AS patronymic,
           st.email                 AS email,
           st.phone                 AS phone,
           st.status                AS status,
           st.enrollment_date       AS enrollment_date,
           sg.name                  AS group_name,
           sp.name                  AS specialty_name,
           sp.code                  AS specialty_code,
           count(*)                 AS lectures_planned,
           sum(coalesce(a.is_present::int, 0)) AS lectures_attended
    FROM schedule sch
    JOIN lecture l ON l.id = sch.lecture_id
    JOIN student st ON st.group_id = sch.group_id
    JOIN student_group sg ON sg.id = st.group_id
    JOIN specialty sp ON sp.id = sg.specialty_id
    JOIN eligible e ON e.student_id = st.id AND e.course_id = l.course_id
    LEFT JOIN attendance a
           ON a.schedule_id = sch.id
          AND a.student_id = st.id
          AND a.week_start_date >= %(week_from)s
          AND a.week_start_date <= %(week_to)s
    WHERE sch.lecture_id = ANY(%(lecture_ids)s::uuid[])
      AND sch.week_start_date >= %(week_from)s
      AND sch.week_start_date <= %(week_to)s
    -- Группировка по первичным ключам student/student_group/specialty:
    -- Postgres выводит функциональную зависимость остальных их колонок
    -- и не требует перечислять каждую в GROUP BY.
    GROUP BY st.id, sg.id, sp.id
    ORDER BY sum(coalesce(a.is_present::int, 0))::numeric / count(*) ASC, st.id
    LIMIT %(limit)s
"""


async def build_report(
    *,
    elastic: AsyncElasticsearch,
    neo4j_driver: AsyncDriver,
    pg_pool: AsyncConnectionPool,
    term: str,
    period_from: date,
    period_to: date,
    limit: int,
) -> dict:
    # 1. Elasticsearch: термин -> лекции и курсы, которым они принадлежат.
    # match_phrase, а не match: задание про термин ИЛИ ФРАЗУ
    search = await elastic.search(
        index=LECTURES_INDEX,
        query={"match_phrase": {"annotation": term}},
        size=1000,
        source_includes=["lecture_id", "course_id", "course_name"],
    )
    hits = search["hits"]["hits"]
    lecture_ids = [hit["_source"]["lecture_id"] for hit in hits]
    course_ids = sorted({hit["_source"]["course_id"] for hit in hits})
    matched_courses = sorted({hit["_source"]["course_name"] for hit in hits})

    if not lecture_ids:
        return _empty_report(term, period_from, period_to)

    # 2. Neo4j: курсы -> пары (студент, курс), на который он реально
    # записан. Среди отобранных курсов могут быть выборные — обход
    # ENROLLED отсекает тех, кто конкретный курс не выбирал, и не путает
    # его с другим совпавшим курсом того же студента.
    async with neo4j_driver.session() as session:
        result = await session.run(ELIGIBLE_PAIRS_CYPHER, course_ids=course_ids)
        pairs = [(record["student_id"], record["course_id"]) async for record in result]

    if not pairs:
        return _empty_report(term, period_from, period_to, matched_courses, len(lecture_ids))

    # 3. PostgreSQL: посещаемость за период по отобранным лекциям,
    # только по парам (студент, курс) из шага 2. Ключ партиционирования —
    # начало недели, сдвигаем левую границу на понедельник, иначе первая
    # неделя периода отсечётся.
    week_from = period_from - timedelta(days=period_from.weekday())
    async with pg_pool.connection() as conn:
        cursor = await conn.execute(
            ATTENDANCE_SQL,
            {
                "lecture_ids": lecture_ids,
                "student_ids": [pair[0] for pair in pairs],
                "course_ids": [pair[1] for pair in pairs],
                "week_from": week_from,
                "week_to": period_to,
                "limit": limit,
            },
        )
        rows = await cursor.fetchall()

    if not rows:
        return _empty_report(term, period_from, period_to, matched_courses, len(lecture_ids))

    items = []
    for (
        student_id,
        card_number,
        last_name,
        first_name,
        patronymic,
        email,
        phone,
        status,
        enrollment_date,
        group_name,
        specialty_name,
        specialty_code,
        planned,
        attended,
    ) in rows:
        items.append(
            {
                "student": {
                    "card_number": card_number,
                    "last_name": last_name,
                    "first_name": first_name,
                    "patronymic": patronymic,
                    "email": email,
                    "phone": phone,
                    "status": status,
                    "enrollment_date": enrollment_date.isoformat(),
                    "group_name": group_name,
                    "specialty_name": specialty_name,
                    "specialty_code": specialty_code,
                },
                "attendance_percent": round(100 * attended / planned, 1) if planned else 0.0,
                "lectures_planned": planned,
                "lectures_attended": attended,
            }
        )

    return {
        "term": term,
        "period_from": period_from,
        "period_to": period_to,
        "matched_lectures_count": len(lecture_ids),
        "matched_courses": matched_courses,
        "items": items,
    }


def _empty_report(
    term: str,
    period_from: date,
    period_to: date,
    matched_courses: list[str] | None = None,
    matched_lectures_count: int = 0,
) -> dict:
    return {
        "term": term,
        "period_from": period_from,
        "period_to": period_to,
        "matched_lectures_count": matched_lectures_count,
        "matched_courses": matched_courses or [],
        "items": [],
    }
