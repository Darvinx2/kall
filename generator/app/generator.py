"""Сборка: построить датасет и разложить его по пяти хранилищам.

Порядок не случаен. PostgreSQL — источник истины, остальные четыре хранилища
получают проекции того же датасета. Идентификаторы присвоены в data.py,
поэтому одна и та же лекция имеет один UUID во всех пяти базах.
"""

from generator.app.data import generate
from generator.app.db import elastic, mongo, postgres
from generator.app.db import neo4j as neo4j_store
from generator.app.db import redis as redis_store
from generator.app.models import Dataset

__all__ = (
    "run",
    "load_postgres",
    "load_redis",
    "load_mongo",
    "load_neo4j",
    "load_elastic",
    "drop_all",
)


def run(*, recreate: bool = True) -> Dataset:
    """Полный проход: генерация датасета и загрузка во все хранилища."""
    data = generate()

    load_postgres(data, recreate=recreate)
    load_redis(data, recreate=recreate)
    load_mongo(data, recreate=recreate)
    load_neo4j(data, recreate=recreate)
    load_elastic(data, recreate=recreate)

    return data


def load_postgres(data: Dataset, *, recreate: bool = True) -> None:
    with postgres.connect() as conn:
        if recreate:
            postgres.drop_tables(conn)
        postgres.create_tables(conn)
        postgres.load(conn, data)

        counts = {
            table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in (
                "student", "lecture_course", "lecture", "lecture_material",
                "schedule", "attendance",
            )
        }
    print("PostgreSQL:   " + ", ".join(f"{k}={v}" for k, v in counts.items()))


def load_redis(data: Dataset, *, recreate: bool = True) -> None:
    client = redis_store.connect()
    try:
        if recreate:
            redis_store.drop(client)
        redis_store.load(client, data)
        cards = client.scard(redis_store.STUDENTS_SET)
        keys = sum(1 for _ in client.scan_iter(match="student:*", count=500))
    finally:
        client.close()
    print(f"Redis:        карточек={cards}, ключей student:*={keys}")


def load_mongo(data: Dataset, *, recreate: bool = True) -> None:
    client = mongo.connect()
    try:
        if recreate:
            mongo.drop(client)
        mongo.load(client, data)
        db = mongo.database(client)
        groups = db[mongo.GROUPS].count_documents({})
        courses = db[mongo.COURSES].count_documents({})
        university = db[mongo.UNIVERSITY].count_documents({})
    finally:
        client.close()
    print(f"MongoDB:      groups={groups}, courses={courses}, university={university}")


def load_neo4j(data: Dataset, *, recreate: bool = True) -> None:
    driver = neo4j_store.connect()
    try:
        if recreate:
            neo4j_store.drop(driver)
        neo4j_store.load(driver, data)
        with driver.session() as session:
            nodes = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            rels = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
            enrolled = session.run(
                "MATCH ()-[r:ENROLLED]->() RETURN count(r) AS c"
            ).single()["c"]
    finally:
        driver.close()
    print(f"Neo4j:        узлов={nodes}, связей={rels} (ENROLLED={enrolled})")


def load_elastic(data: Dataset, *, recreate: bool = True) -> None:
    client = elastic.connect()
    try:
        if recreate:
            elastic.drop(client)
        elastic.load(client, data)
        lectures = client.count(index=elastic.LECTURES)["count"]
        courses = client.count(index=elastic.COURSES)["count"]
    finally:
        client.close()
    print(f"Elasticsearch: lectures={lectures}, courses={courses}")


def drop_all() -> None:
    """Удаляет данные во всех хранилищах, чтобы generate можно было
    прогонять повторно с чистого листа."""
    with postgres.connect() as conn:
        postgres.drop_tables(conn)
    print("PostgreSQL:   схема удалена")

    client = redis_store.connect()
    try:
        redis_store.drop(client)
    finally:
        client.close()
    print("Redis:        ключи удалены")

    client = mongo.connect()
    try:
        mongo.drop(client)
    finally:
        client.close()
    print("MongoDB:      коллекции удалены")

    driver = neo4j_store.connect()
    try:
        neo4j_store.drop(driver)
    finally:
        driver.close()
    print("Neo4j:        узлы удалены")

    client = elastic.connect()
    try:
        elastic.drop(client)
    finally:
        client.close()
    print("Elasticsearch: индексы удалены")
