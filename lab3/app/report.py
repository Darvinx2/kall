"""Отчёт лабы №3: четыре хранилища подряд.

Задание: «извлечь отчёт по заданной группе учащихся с указанием объёма
прослушанных часов лекций, а также необходимого объёма запланированных
часов, в рамках всех курсов для каждого студента группы. Одна лекция равна
2-м академическим часам. В отчёт должны попасть только лекции, которые
содержат тег специальной дисциплины кафедры. Вывести полную информацию
о группе, студенте, курсе, количестве запланированных и посещённых часов».

Способ извлечения:

1. Neo4j — по имени группы отдаёт курсы её специальности (обход
   Group <- Specialty -> Course). «В рамках всех курсов» — это обход графа,
   в PostgreSQL он стоил бы отдельных JOIN.
2. PostgreSQL — считает часы. Запрос повторяет hoursReport из Go-реализации
   university: по группе и курсам соединяет schedule -> lecture ->
   lecture_course, фильтрует лекции по тегу спец. дисциплины и типу «лекция»,
   план = число занятий × 2 ак. часа, факт = занятия с отметкой is_present
   × 2. Одна строка на пару (студент, курс).
3. Redis — «полная информация о студенте»: карточки по номеру зачётной
   книжки. При промахе витрины карточка дочитывается из PostgreSQL.
4. MongoDB — «полная информация о группе»: документ группы одним findOne.
"""

from motor.motor_asyncio import AsyncIOMotorDatabase
from neo4j import AsyncDriver
from psycopg_pool import AsyncConnectionPool
from redis.asyncio import Redis

__all__ = ("build_report",)

GROUPS_COLLECTION = "groups"

LESSON_TYPE = "лекция"
ACADEMIC_HOURS_PER_LESSON = 2
SPECIAL_DISCIPLINE_TAG = "специальная дисциплина кафедры"

STUDENT_KEY = "student:{card}"
STUDENT_BY_ID_KEY = "student:id:{student_id}"

CARD_FIELDS = (
    "card_number", "last_name", "first_name", "patronymic",
    "email", "phone", "status", "enrollment_date",
)

# Курсы специальности, по которой учится группа.
GROUP_COURSES_CYPHER = """
    MATCH (g:Group {name: $group_name})<-[:HAS_GROUP]-(:Specialty)-[:OFFERS]->(c:Course)
    RETURN DISTINCT c.id AS course_id
"""

# Часы по спец. дисциплинам кафедры. План — число занятий × 2 ак. часа, факт —
# занятия с отметкой присутствия × 2. Фильтр по тегу идёт через GIN-индекс.
HOURS_SQL = """
    SELECT st.id::text        AS student_id,
           c.id::text         AS course_id,
           c.name             AS course_name,
           c.semester         AS semester,
           c.lecture_hours    AS course_lecture_hours,
           count(DISTINCT sch.id) * %(hours)s AS planned_hours,
           count(DISTINCT CASE WHEN a.is_present THEN sch.id END) * %(hours)s
                                              AS attended_hours
    FROM student_group g
    JOIN student st ON st.group_id = g.id
    JOIN schedule sch ON sch.group_id = g.id
    JOIN lecture l ON l.id = sch.lecture_id
    JOIN lecture_course c ON c.id = l.course_id
    LEFT JOIN attendance a ON a.schedule_id = sch.id AND a.student_id = st.id
    WHERE g.name = %(group_name)s
      AND c.id = ANY(%(course_ids)s::uuid[])
      AND l.lecture_type = %(lesson_type)s
      AND l.tags @> ARRAY[%(special_tag)s]::text[]
    GROUP BY st.id, c.id
    ORDER BY st.id, c.name
"""

CARDS_FALLBACK_SQL = """
    SELECT st.id::text            AS student_id,
           st.student_card_number AS card_number,
           st.last_name, st.first_name, st.patronymic,
           st.email, st.phone, st.status, st.enrollment_date
    FROM student st
    WHERE st.id = ANY(%(student_ids)s::uuid[])
"""


async def build_report(
    *,
    neo4j_driver: AsyncDriver,
    pg_pool: AsyncConnectionPool,
    redis_client: Redis,
    mongo_db: AsyncIOMotorDatabase,
    group_name: str,
) -> dict:
    # 1. Neo4j: курсы специальности, по которой учится группа.
    async with neo4j_driver.session() as session:
        result = await session.run(GROUP_COURSES_CYPHER, group_name=group_name)
        course_ids = [record["course_id"] async for record in result]

    if not course_ids:
        return _empty_report(group_name)

    # 2. PostgreSQL: часы по спец. дисциплинам, строка на пару (студент, курс).
    async with pg_pool.connection() as conn:
        cursor = await conn.execute(
            HOURS_SQL,
            {
                "group_name": group_name,
                "course_ids": course_ids,
                "lesson_type": LESSON_TYPE,
                "special_tag": SPECIAL_DISCIPLINE_TAG,
                "hours": ACADEMIC_HOURS_PER_LESSON,
            },
        )
        rows = await cursor.fetchall()

    if not rows:
        return _empty_report(group_name)

    # 3. Redis: карточки студентов по номеру зачётки.
    student_ids = sorted({row[0] for row in rows})
    cards = await _load_cards(redis_client, pg_pool, student_ids)

    # 4. MongoDB: полная информация о группе одним документом.
    group_doc = await mongo_db[GROUPS_COLLECTION].find_one({"name": group_name}) or {}

    by_student: dict[str, dict] = {}
    for student_id, course_id, name, semester, lecture_hours, planned, attended in rows:
        entry = by_student.setdefault(
            student_id,
            {
                "student": cards.get(student_id, {}),
                "courses": [],
                "total_planned_hours": 0,
                "total_attended_hours": 0,
            },
        )
        entry["courses"].append(
            {
                "id": course_id,
                "name": name,
                "semester": semester,
                "course_lecture_hours": lecture_hours,
                "planned_hours": planned,
                "attended_hours": attended,
            }
        )
        entry["total_planned_hours"] += planned
        entry["total_attended_hours"] += attended

    items = [
        {
            **entry,
            "attendance_percent": (
                round(100 * entry["total_attended_hours"] / entry["total_planned_hours"], 1)
                if entry["total_planned_hours"]
                else 0.0
            ),
        }
        for entry in by_student.values()
        if entry["student"]
    ]
    items.sort(key=lambda item: (item["attendance_percent"], item["student"]["card_number"]))

    return {
        "group": {
            "name": group_name,
            "enrollment_year": group_doc.get("enrollment_year", 0),
            "curator": group_doc.get("curator", ""),
            "students_count": group_doc.get("students_count", len(items)),
            "specialty_name": group_doc.get("specialty", {}).get("name", ""),
            "specialty_code": group_doc.get("specialty", {}).get("code", ""),
        },
        "special_discipline_tag": SPECIAL_DISCIPLINE_TAG,
        "academic_hours_per_lesson": ACADEMIC_HOURS_PER_LESSON,
        "items": items,
    }


async def _load_cards(
    redis_client: Redis, pg_pool: AsyncConnectionPool, student_ids: list[str]
) -> dict[str, dict]:
    """Карточки студентов: сначала витрина Redis, при промахе — PostgreSQL."""
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
        async with pg_pool.connection() as conn:
            cursor = await conn.execute(CARDS_FALLBACK_SQL, {"student_ids": missing})
            for student_id, *values in await cursor.fetchall():
                card = dict(zip(CARD_FIELDS, values))
                card["enrollment_date"] = card["enrollment_date"].isoformat()
                cards[student_id] = card
    return cards


def _empty_report(group_name: str) -> dict:
    return {
        "group": {
            "name": group_name, "enrollment_year": 0, "curator": "",
            "students_count": 0, "specialty_name": "", "specialty_code": "",
        },
        "special_discipline_tag": SPECIAL_DISCIPLINE_TAG,
        "academic_hours_per_lesson": ACADEMIC_HOURS_PER_LESSON,
        "items": [],
    }
