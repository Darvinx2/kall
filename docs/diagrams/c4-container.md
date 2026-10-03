@startuml C4_Container
!include <C4/C4_Container>

  LAYOUT_WITH_LEGEND()
  LAYOUT_TOP_DOWN()

  AddElementTag("gateway",  $bgColor="#1a237e", $fontColor="#ffffff", $legendText="«api gateway»")
  AddElementTag("service",  $bgColor="#1565c0", $fontColor="#ffffff", $legendText="«microservice»")
  AddElementTag("job",      $bgColor="#37474f", $fontColor="#ffffff", $legendText="«batch job»")
  AddElementTag("db_es",    $bgColor="#f57f17", $fontColor="#000000", $legendText="«search engine»")
  AddElementTag("db_neo4j", $bgColor="#4a148c", $fontColor="#ffffff", $legendText="«graph DB»")
  AddElementTag("db_pg",    $bgColor="#0d47a1", $fontColor="#ffffff", $legendText="«relational DB»")
  AddElementTag("db_redis", $bgColor="#7f0000", $fontColor="#ffffff", $legendText="«key-value store»")
  AddElementTag("db_mongo", $bgColor="#1b5e20", $fontColor="#ffffff", $legendText="«document DB»")

  title Диаграмма контейнеров (Level 2) — UniversityMicroservices

  ' ========================= ЯРУС 1: пользователь =========================
  Person(user, "Пользователь", "Аналитик кафедры")

  System_Boundary(sys, "UniversityMicroservices") {

      ' ======================= ЯРУС 2: точка входа =======================
      Container(gateway, "API Gateway", "[Python 3.14 / FastAPI / :8000]", "JWT-аутентификация и проксирование в лабораторные сервисы. Единственный контейнер, опубликованный наружу", $tags="gateway")

      ' ===================== ЯРУС 3: сервисы и задачи =====================
      Container(lab1, "Lab1 Service", "[Python 3.14 / FastAPI]", "Отчёт о 10 студентах с минимальным процентом посещения. Четыре шага: ES -> Neo4j -> PostgreSQL -> Redis. Порт наружу не публикуется", $tags="service")

      Container(generator, "Data Generator", "[Python 3.14 / разовая задача]", "Собирает один Dataset в памяти и наполняет все пять хранилищ общими UUID. Профиль compose seed, отрабатывает один раз", $tags="job")

      ' ======================= ЯРУС 4: хранилища =======================
      ContainerDb(es, "Elasticsearch", "[elasticsearch:9.5.1 / :9201]", "Полнотекст, анализатор russian. Индексы lectures и courses", $tags="db_es")

      ContainerDb(neo4j, "Neo4j", "[neo4j:5-community / bolt :7688]", "Связи группа-студент-курс. Расписания и посещаемости в графе нет", $tags="db_neo4j")

      ContainerDb(pg, "PostgreSQL", "[postgres:16-alpine / :5433]", "Источник истины, 12 таблиц, ACID. attendance партиционирована по неделям", $tags="db_pg")

      ContainerDb(redis, "Redis", "[redis:7-alpine / :6380]", "Витрина ключ-значение без TTL. Ключ — номер зачётной книжки", $tags="db_redis")

      ContainerDb(mongo, "MongoDB", "[mongo:7 / :27018]", "Документы-композиции: groups, courses, university", $tags="db_mongo")
  }

  ' ====================== СВЯЗИ: строго сверху вниз ======================
  Rel_D(user, gateway, "POST /auth/login, POST /api/lab1/report", "HTTPS + JWT")
  Rel_D(gateway, lab1, "POST /report, без токена — сеть compose закрыта", "HTTP")

  Rel_D(lab1, es,    "1. Термин -> id лекций и курсов", "elasticsearch[async]")
  Rel_D(lab1, neo4j, "2. Курсы -> пары (студент, курс)", "neo4j async, Bolt")
  Rel_D(lab1, pg,    "3. Проценты, pruning партиций", "psycopg async")
  Rel_D(lab1, redis, "4. Карточки студентов", "redis.asyncio")

  Rel_D(generator, mongo, "Три коллекции", "pymongo")
  Rel_D(generator, redis, "Карточки студентов", "redis-py")
  Rel_D(generator, pg,    "DDL, партиции, триггеры, данные", "psycopg")
  Rel_D(generator, neo4j, "Узлы и связи", "neo4j")
  Rel_D(generator, es,    "Маппинги и документы", "elasticsearch")

  ' ===================== РАСКЛАДКА: ярусы и порядок =====================
  ' Вертикаль: пользователь -> gateway -> lab1 -> ряд хранилищ.
  Lay_D(user, gateway)
  Lay_D(gateway, lab1)
  Lay_D(lab1, pg)

  ' Генератор — сбоку от lab1, на том же ярусе: он не в пути запроса.
  Lay_R(lab1, generator)

  ' Хранилища одним рядом слева направо, в порядке шагов лабы.
  ' MongoDB последней: её читает только генератор, поэтому её стрелка
  ' не пересекает стрелки lab1.
  Lay_R(es, neo4j)
  Lay_R(neo4j, pg)
  Lay_R(pg, redis)
  Lay_R(redis, mongo)

@enduml
