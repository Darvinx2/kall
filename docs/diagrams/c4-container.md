@startuml C4_Container
!include <C4/C4_Container>

LAYOUT_WITH_LEGEND()

AddElementTag("gateway",  $bgColor="#1a237e", $fontColor="#ffffff", $legendText="«api gateway»")
AddElementTag("service",  $bgColor="#1565c0", $fontColor="#ffffff", $legendText="«microservice»")
AddElementTag("job",      $bgColor="#37474f", $fontColor="#ffffff", $legendText="«batch job»")
AddElementTag("db_pg",    $bgColor="#0d47a1", $fontColor="#ffffff", $legendText="«relational DB»")
AddElementTag("db_redis", $bgColor="#7f0000", $fontColor="#ffffff", $legendText="«key-value store»")
AddElementTag("db_mongo", $bgColor="#1b5e20", $fontColor="#ffffff", $legendText="«document DB»")
AddElementTag("db_neo4j", $bgColor="#4a148c", $fontColor="#ffffff", $legendText="«graph DB»")
AddElementTag("db_es",    $bgColor="#f57f17", $fontColor="#000000", $legendText="«search engine»")

title Диаграмма контейнеров (Level 2) — UniversityMicroservices

Person(user, "Пользователь", "Аналитик кафедры")

System_Boundary(sys, "UniversityMicroservices") {

    Container(gateway, "API Gateway", "[Python 3.14 / FastAPI / :8000]", "JWT-аутентификация, проксирование в лабораторные сервисы. Единственный контейнер, опубликованный наружу", $tags="gateway")

    Container(lab1, "Lab1 Service", "[Python 3.14 / FastAPI]", "Отчёт о 10 студентах с минимальным процентом посещения. Четыре шага: ES -> Neo4j -> PostgreSQL -> Redis. Порт наружу не публикуется", $tags="service")

    Container(generator, "Data Generator", "[Python 3.14 / скрипт]", "Собирает один Dataset в памяти и наполняет все пять хранилищ общими UUID. Отрабатывает один раз при старте", $tags="job")

    ContainerDb(pg, "PostgreSQL", "[postgres:16-alpine / :5433]", "Источник истины, 12 таблиц, ACID. attendance партиционирована по week_start_date, 44 недельные партиции", $tags="db_pg")

    ContainerDb(redis, "Redis", "[redis:7-alpine / :6380]", "Витрина ключ-значение без TTL: student:{зачётка} HASH с карточкой, student:id:{uuid} вторичный индекс, students SET", $tags="db_redis")

    ContainerDb(mongo, "MongoDB", "[mongo:7 / :27018]", "Документы-композиции: groups (группа + студенты + курсы), courses (курс + лекции), university (иерархия вуза)", $tags="db_mongo")

    ContainerDb(neo4j, "Neo4j", "[neo4j:5-community / bolt :7688]", "Связи группа-студент-курс: Specialty -> Group -> Student, Specialty -> Course, Student -> Course. Расписания и посещаемости в графе нет", $tags="db_neo4j")

    ContainerDb(es, "Elasticsearch", "[elasticsearch:9.5.1 / :9201]", "Полнотекст, анализатор russian. Индексы lectures (аннотация + тексты материалов) и courses (описания)", $tags="db_es")
}

Rel(user, gateway, "POST /auth/login, POST /api/lab1/report", "HTTPS + JWT")
Rel(gateway, lab1, "POST /report, без токена — сеть compose закрыта", "HTTP")

Rel(lab1, es,    "1. Термин или фраза -> id лекций и курсов", "elasticsearch[async]")
Rel(lab1, neo4j, "2. Курсы -> пары (студент, курс)", "neo4j async, Bolt")
Rel(lab1, pg,    "3. Проценты посещения, pruning партиций", "psycopg async")
Rel(lab1, redis, "4. Карточки студентов по номеру зачётки", "redis.asyncio")

Rel(generator, pg,    "DDL, партиции, триггеры, загрузка", "psycopg")
Rel(generator, redis, "Карточки студентов", "redis-py")
Rel(generator, mongo, "Три коллекции", "pymongo")
Rel(generator, neo4j, "Узлы и связи", "neo4j")
Rel(generator, es,    "Маппинги и документы", "elasticsearch")

Rel_U(lab1, pg, "Откат: карточка, если её нет в Redis", "psycopg async")

@enduml
