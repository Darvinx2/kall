"""Отчёт лабы №1: одна функция, три хранилища подряд.

Задание: «извлечь отчёт о 10 студентах с минимальным процентом посещения
лекций, содержащих заданный термин или фразу, за определённый период
обучения. Состав полей: полная информация о студенте, процент посещения,
период отчёта, термин в занятиях курса».

Способ извлечения:

1. Elasticsearch — по термину отдаёт id лекций. Обратный индекс с
   анализатором russian находит любую словоформу; в PostgreSQL тот же
   поиск был бы полным перебором по ILIKE без индекса.
2. PostgreSQL — агрегирует посещаемость по этим лекциям за период.
   Фильтр идёт по ключу партиционирования (week_start_date), поэтому
   читаются только недели из запрошенного диапазона.
3. Redis — отдаёт карточки студентов по номеру зачётки за O(1), без join
   к student/student_group/specialty в PostgreSQL.
"""

from datetime import date, timedelta

from elasticsearch import AsyncElasticsearch
from psycopg_pool import AsyncConnectionPool
from redis.asyncio import Redis

__all__ = ("build_report",)

LECTURES_INDEX = "lectures"

ATTENDANCE_SQL = """
    SELECT a.student_id::text,
           count(*)               AS lectures_planned,
           sum(a.is_present::int) AS lectures_attended
    FROM attendance a
    JOIN schedule s ON s.id = a.schedule_id
    WHERE a.week_start_date >= %(week_from)s
      AND a.week_start_date <= %(week_to)s
      AND s.lecture_id = ANY(%(lecture_ids)s::uuid[])
    GROUP BY a.student_id
    ORDER BY sum(a.is_present::int)::numeric / count(*) ASC, a.student_id
    LIMIT %(limit)s
"""


async def build_report(
    *,
    elastic: AsyncElasticsearch,
    pg_pool: AsyncConnectionPool,
    redis: Redis,
    term: str,
    period_from: date,
    period_to: date,
    limit: int,
) -> dict:
    # 1. Elasticsearch: термин -> лекции.
    # match_phrase, а не match: задание про термин ИЛИ ФРАЗУ, и «нейронные
    # сети» не должно совпадать с текстом, где слова встретились порознь.
    search = await elastic.search(
        index=LECTURES_INDEX,
        query={"match_phrase": {"annotation": term}},
        size=1000,
        source_includes=["lecture_id", "course_name"],
    )
    hits = search["hits"]["hits"]
    lecture_ids = [hit["_source"]["lecture_id"] for hit in hits]
    matched_courses = sorted({hit["_source"]["course_name"] for hit in hits})

    if not lecture_ids:
        return _empty_report(term, period_from, period_to)

    # 2. PostgreSQL: посещаемость за период по отобранным лекциям.
    # Ключ партиционирования — начало недели, сдвигаем левую границу
    # на понедельник, иначе первая неделя периода отсечётся.
    week_from = period_from - timedelta(days=period_from.weekday())
    async with pg_pool.connection() as conn:
        cursor = await conn.execute(
            ATTENDANCE_SQL,
            {
                "lecture_ids": lecture_ids,
                "week_from": week_from,
                "week_to": period_to,
                "limit": limit,
            },
        )
        rows = await cursor.fetchall()

    if not rows:
        return _empty_report(term, period_from, period_to, matched_courses, len(lecture_ids))

    # 3. Redis: id студента -> зачётка -> карточка. Два прохода pipeline
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
