"""Отчёт лабы №1: одна функция, четыре хранилища подряд.

Задание: «извлечь отчёт о 10 студентах с минимальным процентом посещения
лекций, содержащих заданный термин или фразу, за определённый период
обучения. Состав полей: полная информация о студенте, процент посещения,
период отчёта, термин в занятиях курса».

Способ извлечения:

1. Elasticsearch — по термину отдаёт id лекций и id курсов, которым они
   принадлежат. Обратный индекс с анализатором russian находит любую
   словоформу; в PostgreSQL тот же поиск был бы перебором по ILIKE без
   индекса. Термин ищется в названии, аннотации и склеенных текстах
   материалов занятия. Фильтр по lecture_type оставляет только лекции:
   практики и лабораторные в процент посещения лекций не входят.
2. Neo4j — по id курсов отдаёт ПАРЫ (студент, курс), а не плоский список
   студентов (обход связи ENROLLED). Пара обязательна: если собрать только
   множество студентов, отчёт спутает разные курсы одного студента — тот,
   кто записан на один из совпавших курсов, получит в план ещё и занятия
   другого совпавшего курса. Пара (student_id, course_id) держит эту связь
   явной вплоть до SQL.
3. PostgreSQL — считает посещаемость по занятиям с отобранными лекциями
   за период, но только по парам (студент, курс) из шага 2 — join идёт
   именно по паре, не по двум независимым спискам. Знаменатель — сами
   занятия из schedule (LEFT JOIN к attendance): если отметки нет, это
   пропуск, а не повод исключить занятие из отчёта. Фильтр по
   week_start_date идёт по ключу партиционирования, поэтому читаются
   только недели из запрошенного диапазона, а по scheduled_date —
   чтобы в знаменатель не попали занятия той же недели, но вне периода.
   В знаменатель идут только состоявшиеся занятия. Запрос чисто
   аналитический:
   возвращает идентификаторы и числа, полей карточки в нём нет.
4. Redis — по десяти идентификаторам отдаёт карточки студентов. Первичный
   ключ там — номер зачётной книжки (task.md), а аналитика оперирует UUID,
   поэтому сначала MGET по вторичному индексу student:id:{uuid}, затем
   пайплайн HGETALL. Два round-trip на весь отчёт вместо десяти.

   Redis здесь не источник истины, а витрина ключ-значение: при промахе
   (ключи вычистили, витрина отстала) карточка дочитывается из PostgreSQL,
   поэтому отчёт не ломается никогда.
"""

from datetime import date, timedelta

from elasticsearch import AsyncElasticsearch
from neo4j import AsyncDriver
from psycopg_pool import AsyncConnectionPool
from redis.asyncio import Redis

__all__ = ("build_report",)

LECTURES_INDEX = "lectures"

# Задание: «процент посещения ЛЕКЦИЙ». Практики и лабораторные входят
# в состав курса, но в знаменатель процента не попадают.
LESSON_TYPE = "лекция"

# В знаменатель идут только состоявшиеся занятия: отменённую пару
# нельзя засчитать студенту как пропуск.
LESSON_STATUS = "held"

# Раскладка ключей повторяет generator/app/db/redis.py.
STUDENT_KEY = "student:{card}"
STUDENT_BY_ID_KEY = "student:id:{student_id}"

# Поля карточки, которые ожидает StudentInfo. Один список на оба источника:
# и на HASH из Redis, и на запрос отката в PostgreSQL.
CARD_FIELDS = (
    "card_number",
    "last_name",
    "first_name",
    "patronymic",
    "email",
    "phone",
    "status",
    "enrollment_date",
    "group_name",
    "specialty_name",
    "specialty_code",
)

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
    SELECT st.id::text                          AS student_id,
           count(*)                             AS lectures_planned,
           count(*) FILTER (WHERE a.is_present) AS lectures_attended,
           round(100.0 * count(*) FILTER (WHERE a.is_present) / count(*), 1)
                                                AS attendance_percent
    FROM schedule sch
    -- Пары (лекция, курс) пришли из Elasticsearch, поэтому course_id
    -- известен заранее и таблица lecture в запросе не нужна.
    JOIN unnest(%(lecture_ids)s::uuid[], %(lecture_course_ids)s::uuid[])
         AS m(lecture_id, course_id)
      ON m.lecture_id = sch.lecture_id
    JOIN student st ON st.group_id = sch.group_id
    -- Пары (студент, курс) из Neo4j: join идёт по паре, а не по двум
    -- независимым спискам — иначе студент, записанный на один из
    -- совпавших курсов, получил бы в план занятия другого.
    JOIN unnest(%(student_ids)s::uuid[], %(course_ids)s::uuid[])
         AS e(student_id, course_id)
      ON e.student_id = st.id AND e.course_id = m.course_id
    LEFT JOIN attendance a
           ON a.schedule_id = sch.id
          AND a.student_id = st.id
          AND a.week_start_date >= %(week_from)s
          AND a.week_start_date <= %(period_to)s
    -- Две границы на разных колонках делают разную работу. По неделе —
    -- чтобы PostgreSQL отсёк лишние партиции и не читал весь год.
    -- По дате занятия — чтобы в знаменатель не попали занятия той же
    -- недели, но вне запрошенного периода.
    WHERE sch.week_start_date >= %(week_from)s
      AND sch.week_start_date <= %(period_to)s
      AND sch.scheduled_date BETWEEN %(period_from)s AND %(period_to)s
      AND sch.status = %(lesson_status)s
    GROUP BY st.id
    ORDER BY attendance_percent ASC, st.id
    LIMIT %(limit)s
"""

# Откат на случай промаха витрины: ровно те же поля, что лежат в HASH.
CARDS_FALLBACK_SQL = """
    SELECT st.id::text            AS student_id,
           st.student_card_number AS card_number,
           st.last_name,
           st.first_name,
           st.patronymic,
           st.email,
           st.phone,
           st.status,
           st.enrollment_date,
           sg.name                AS group_name,
           sp.name                AS specialty_name,
           sp.code                AS specialty_code
    FROM student st
    JOIN student_group sg ON sg.id = st.group_id
    JOIN specialty sp ON sp.id = sg.specialty_id
    WHERE st.id = ANY(%(student_ids)s::uuid[])
"""


async def build_report(
    *,
    elastic: AsyncElasticsearch,
    neo4j_driver: AsyncDriver,
    pg_pool: AsyncConnectionPool,
    redis_client: Redis,
    term: str,
    period_from: date,
    period_to: date,
    limit: int,
) -> dict:
    # 1. Elasticsearch: термин -> лекции и курсы, которым они принадлежат.
    # filter, а не must: тип занятия — точное совпадение
    search = await elastic.search(
        index=LECTURES_INDEX,
        query={
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": term,
                            "type": "phrase",
                            "fields": ["title^3", "annotation^2", "content_text"],
                        }
                    }
                ],
                "filter": [{"term": {"lecture_type": LESSON_TYPE}}],
            }
        },
        size=1000,
        source_includes=["lecture_id", "course_id", "course_name"],
    )
    hits = search["hits"]["hits"]
    # Два параллельных массива — пары (лекция, курс) для unnest в SQL.
    lecture_ids = [hit["_source"]["lecture_id"] for hit in hits]
    lecture_course_ids = [hit["_source"]["course_id"] for hit in hits]
    course_ids = sorted(set(lecture_course_ids))
    matched_courses = sorted({hit["_source"]["course_name"] for hit in hits})

    if not lecture_ids:
        return _empty_report(term, period_from, period_to)

    # 2. Neo4j: курсы -> пары (студент, курс), на который он записан.
    # Обход ENROLLED не путает разные совпавшие курсы одного студента.
    async with neo4j_driver.session() as session:
        result = await session.run(ELIGIBLE_PAIRS_CYPHER, course_ids=course_ids)
        pairs = [(record["student_id"], record["course_id"]) async for record in result]

    if not pairs:
        return _empty_report(term, period_from, period_to, matched_courses, len(lecture_ids))

    # 3. PostgreSQL: посещаемость за период по отобранным лекциям,
    # только по парам (студент, курс) из шага 2. Левую границу недели
    # сдвигаем на понедельник, иначе партиция первой недели периода
    # отсеклась бы целиком вместе с нужными занятиями.
    week_from = period_from - timedelta(days=period_from.weekday())
    async with pg_pool.connection() as conn:
        cursor = await conn.execute(
            ATTENDANCE_SQL,
            {
                "lecture_ids": lecture_ids,
                "lecture_course_ids": lecture_course_ids,
                "student_ids": [pair[0] for pair in pairs],
                "course_ids": [pair[1] for pair in pairs],
                "week_from": week_from,
                "period_from": period_from,
                "period_to": period_to,
                "lesson_status": LESSON_STATUS,
                "limit": limit,
            },
        )
        stats = await cursor.fetchall()

    if not stats:
        return _empty_report(term, period_from, period_to, matched_courses, len(lecture_ids))

    # 4. Redis: карточки отобранных студентов из витрины ключ-значение.
    cards = await _load_cards(redis_client, pg_pool, [row[0] for row in stats])

    items = [
        {
            "student": cards[student_id],
            "attendance_percent": float(percent),
            "lectures_planned": planned,
            "lectures_attended": attended,
        }
        for student_id, planned, attended, percent in stats
        if student_id in cards
    ]

    return {
        "term": term,
        "period_from": period_from,
        "period_to": period_to,
        "matched_lectures_count": len(lecture_ids),
        "matched_courses": matched_courses,
        "items": items,
    }


async def _load_cards(
    redis_client: Redis, pg_pool: AsyncConnectionPool, student_ids: list[str]
) -> dict[str, dict]:
    """Карточки студентов: сначала витрина, при промахе — источник истины.

    Два round-trip в Redis на весь отчёт: MGET переводит UUID в номера
    зачёток через вторичный индекс, затем пайплайн HGETALL забирает сами
    карточки. Поштучных обращений нет.
    """
    numbers = await redis_client.mget(
        [STUDENT_BY_ID_KEY.format(student_id=student_id) for student_id in student_ids]
    )
    known = [(sid, card) for sid, card in zip(student_ids, numbers) if card]

    hashes = []
    if known:
        pipe = redis_client.pipeline(transaction=False)
        for _student_id, card in known:
            pipe.hgetall(STUDENT_KEY.format(card=card))
        hashes = await pipe.execute()

    cards: dict[str, dict] = {}
    for (student_id, _card), payload in zip(known, hashes):
        if payload:
            cards[student_id] = {field: payload.get(field, "") for field in CARD_FIELDS}

    missing = [student_id for student_id in student_ids if student_id not in cards]
    if missing:
        cards.update(await _load_cards_from_postgres(pg_pool, missing))
    return cards


async def _load_cards_from_postgres(
    pg_pool: AsyncConnectionPool, student_ids: list[str]
) -> dict[str, dict]:
    """Откат: витрина отстала или её вычистили — читаем источник истины."""
    async with pg_pool.connection() as conn:
        cursor = await conn.execute(CARDS_FALLBACK_SQL, {"student_ids": student_ids})
        rows = await cursor.fetchall()

    cards = {}
    for student_id, *values in rows:
        card = dict(zip(CARD_FIELDS, values))
        card["enrollment_date"] = card["enrollment_date"].isoformat()
        cards[student_id] = card
    return cards


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
