"""Neo4j: граф связей группа — студент — курс.

Раскладка по task.md: «Для Neo4J – связи между группой-студентом-курсом».

    (:Specialty)-[:HAS_GROUP]->(:Group)-[:HAS_STUDENT]->(:Student)
    (:Specialty)-[:OFFERS]->(:Course)
    (:Student)-[:ENROLLED]->(:Course)

Граф хранит структуру связей, но НЕ факты посещения: их десятки тысяч и они
растут со временем — им место в партиционированной таблице PostgreSQL.
Здесь отвечают на вопросы обхода: кто слушает курс (лаба №2) и какой набор
курсов у каждого студента группы (лаба №3).
"""

from neo4j import Driver, GraphDatabase

from generator.app.config import get_settings
from generator.app.models import Dataset

__all__ = ("connect", "load", "drop", "LABELS")

LABELS = ("Specialty", "Group", "Student", "Course")

# Ограничения уникальности заодно создают индексы. Без них MERGE по id
# делал бы полный перебор узлов метки — на каждой связи.
CONSTRAINTS = tuple(
    f"CREATE CONSTRAINT {label.lower()}_id IF NOT EXISTS "
    f"FOR (n:{label}) REQUIRE n.id IS UNIQUE"
    for label in LABELS
)


def connect(url: str | None = None) -> Driver:
    settings = get_settings()
    return GraphDatabase.driver(
        url or settings.neo4j_url,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
    )


def load(driver: Driver, data: Dataset) -> None:
    with driver.session() as session:
        for statement in CONSTRAINTS:
            session.run(statement)

        # Каждый вызов — один round-trip и один план запроса на весь список.
        # Отдельные CREATE на каждую строку были бы в разы медленнее.
        session.run(
            "UNWIND $rows AS row "
            "MERGE (s:Specialty {id: row.id}) "
            "SET s.name = row.name, s.code = row.code, "
            "    s.degree_level = row.degree_level",
            rows=[
                {
                    "id": str(s.id),
                    "name": s.name,
                    "code": s.code,
                    "degree_level": s.degree_level,
                }
                for s in data.specialties
            ],
        )

        session.run(
            "UNWIND $rows AS row "
            "MERGE (g:Group {id: row.id}) "
            "SET g.name = row.name, g.enrollment_year = row.enrollment_year, "
            "    g.curator = row.curator "
            "WITH g, row "
            "MATCH (s:Specialty {id: row.specialty_id}) "
            "MERGE (s)-[:HAS_GROUP]->(g)",
            rows=[
                {
                    "id": str(g.id),
                    "name": g.name,
                    "enrollment_year": g.enrollment_year,
                    "curator": g.curator,
                    "specialty_id": str(g.specialty_id),
                }
                for g in data.groups
            ],
        )

        session.run(
            "UNWIND $rows AS row "
            "MERGE (st:Student {id: row.id}) "
            "SET st.card_number = row.card_number, st.full_name = row.full_name, "
            "    st.last_name = row.last_name, st.first_name = row.first_name, "
            "    st.patronymic = row.patronymic, st.status = row.status "
            "WITH st, row "
            "MATCH (g:Group {id: row.group_id}) "
            "MERGE (g)-[:HAS_STUDENT]->(st)",
            rows=[
                {
                    "id": str(st.id),
                    "card_number": st.student_card_number,
                    "full_name": f"{st.last_name} {st.first_name} {st.patronymic}".strip(),
                    "last_name": st.last_name,
                    "first_name": st.first_name,
                    "patronymic": st.patronymic,
                    "status": st.status,
                    "group_id": str(st.group_id),
                }
                for st in data.students
            ],
        )

        session.run(
            "UNWIND $rows AS row "
            "MERGE (c:Course {id: row.id}) "
            "SET c.name = row.name, c.semester = row.semester, "
            "    c.lecture_hours = row.lecture_hours "
            "WITH c, row "
            "MATCH (s:Specialty {id: row.specialty_id}) "
            "MERGE (s)-[:OFFERS]->(c)",
            rows=[
                {
                    "id": str(c.id),
                    "name": c.name,
                    "semester": c.semester,
                    "lecture_hours": c.lecture_hours,
                    "specialty_id": str(c.specialty_id),
                }
                for c in data.courses
            ],
        )

        # Связь студент-курс — ядро графа: «группа-студент-курс» из task.md.
        session.run(
            "UNWIND $rows AS row "
            "MATCH (st:Student {id: row.student_id}) "
            "MATCH (c:Course {id: row.course_id}) "
            "MERGE (st)-[e:ENROLLED]->(c) "
            "SET e.enrolled_at = row.enrolled_at",
            rows=[
                {
                    "student_id": str(sc.student_id),
                    "course_id": str(sc.course_id),
                    "enrolled_at": sc.enrolled_at.isoformat(),
                }
                for sc in data.student_courses
            ],
        )


def drop(driver: Driver) -> None:
    """Удаляет наши узлы вместе со связями и снимает ограничения."""
    with driver.session() as session:
        for label in LABELS:
            session.run(f"MATCH (n:{label}) DETACH DELETE n")
            session.run(f"DROP CONSTRAINT {label.lower()}_id IF EXISTS")
