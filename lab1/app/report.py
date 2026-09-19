"""Отчёт лабы №1: одна функция, четыре хранилища подряд.

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
   только недели из запрошенного диапазона.
4. Redis — отдаёт карточки студентов по номеру зачётки за O(1), без join
   к student/student_group/specialty в PostgreSQL.
"""

from datetime import date, timedelta

from elasticsearch import AsyncElasticsearch
from neo4j import AsyncDriver
from psycopg_pool import AsyncConnectionPool
from redis.asyncio import Redis

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
    SELECT st.id::text AS student_id,
           count(*)                                    AS lectures_planned,
           sum(coalesce(a.is_present::int, 0))          AS lectures_attended
    FROM schedule sch
    JOIN lecture l ON l.id = sch.lecture_id
    JOIN student st ON st.group_id = sch.group_id
    JOIN eligible e ON e.student_id = st.id AND e.course_id = l.course_id
    LEFT JOIN attendance a
           ON a.schedule_id = sch.id
          AND a.student_id = st.id
          AND a.week_start_date >= %(week_from)s
          AND a.week_start_date <= %(week_to)s
    WHERE sch.lecture_id = ANY(%(lecture_ids)s::uuid[])
      AND sch.week_start_date >= %(week_from)s
      AND sch.week_start_date <= %(week_to)s
    GROUP BY st.id
    ORDER BY sum(coalesce(a.is_present::int, 0))::numeric / count(*) ASC, st.id
    LIMIT %(limit)s
"""


async def build_report(
    *,
    elastic: AsyncElasticsearch,
    neo4j_driver: AsyncDriver,
    pg_pool: AsyncConnectionPool,
    redis: Redis,
    term: str,
    period_from: date,
    period_to: date,
    limit: int,
) -> dict:
    # 1. Elasticsearch: термин -> лекции и курсы, которым они принадлежат.
    # match_phrase, а не match: задание про термин ИЛИ ФРАЗУ, и «нейронные
    # сети» не должно совпадать с текстом, где слова встретились порознь.
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

    # 4. Redis: id студента -> зачётка -> карточка. Два прохода pipeline
    # вместо 2*N round-trip до сервера.
    student_ids = [student_id for student_id, _, _ in rows]

    pipe = redis.pipeline(transaction=False)
    for student_id in student_ids:
        pipe.get(f"student:id:{student_id}")
    cards = await pipe.execute()

    pipe = redis.pipeline(transaction=False)
    for card in cards:
        if card is not None:
            pipe.hgetall(f"student:{card}")
    profiles = await pipe.execute()
    profiles_by_id = {p["id"]: p for p in profiles if p}

    items = []
    for student_id, planned, attended in rows:
        profile = profiles_by_id.get(student_id)
        if profile is None:
            continue
        items.append(
            {
                "student": profile,
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
