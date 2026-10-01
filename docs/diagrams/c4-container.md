@startuml
!include <C4/C4_Container>

  LAYOUT_WITH_LEGEND()

  AddElementTag("gateway",    $bgColor="#1a237e", $fontColor="#ffffff", $legendText="«API gateway»")
  AddElementTag("service",    $bgColor="#1565c0", $fontColor="#ffffff", $legendText="«microservice»")
  AddElementTag("db_pg",      $bgColor="#0d47a1", $fontColor="#ffffff", $legendText="«relational DB»")
  AddElementTag("db_redis",   $bgColor="#7f0000", $fontColor="#ffffff", $legendText="«key-value store»")
  AddElementTag("db_neo4j",   $bgColor="#1565c0", $fontColor="#ffffff", $legendText="«graph DB»")
  AddElementTag("db_es",      $bgColor="#f57f17", $fontColor="#000000", $legendText="«search engine»")

  title C4 Level 2 — Container Diagram\nPolyglot University System — внутренняя структура

  Person(user, "Пользователь", "Студент / Преподаватель /\nАдминистратор")

  System_Boundary(sys, "Polyglot University System") {

      Container(gateway, "API Gateway", "[Python / FastAPI / :8000]", "JWT-аутентификация,\nмаршрутизация,\nпроксирование запросов", $tags="gateway")

      Container(lab1, "Lab1 Service", "[Python / FastAPI / :8001]", "Отчёт о посещаемости.\nPipeline через 4\nхранилища: ES→Neo4j→PG→Redis", $tags="service")

      ContainerDb(neo4j, "Neo4j", "[Neo4j 5 / :10001]", "Граф учебного процесса.\nСвязи: студент — группа —\nрасписание — лекция.", $tags="db_neo4j")

      ContainerDb(es, "ElasticSearch", "[ElasticSearch 8 / :12000]", "Полнотекстовый поиск по\nматериалам лекций. BM25,\nrussian_custom анализатор.", $tags="db_es")

      ContainerDb(pg, "PostgreSQL", "[PostgreSQL 15 / :5435]", "Источник истины. ACID.\nПартиционированная\nattendance.", $tags="db_pg")

      ContainerDb(redis, "Redis", "[Redis 7 / :6379]", "Кэш данных студентов. Дубль\nиз PostgreSQL. TTL 7200 с.", $tags="db_redis")
  }

  Rel(user,    gateway, "Все HTTP-запросы (JWT)", "[HTTPS]")
  Rel(gateway, lab1,    "Прокси /lab1/*",          "[HTTP]")

  Rel(lab1, es,    "Полнотекстовый поиск термина",             "[elasticsearch async]")
  Rel(lab1, neo4j, "Обход графа студент–расписание",           "[neo4j-async]")
  Rel(lab1, pg,    "Подсчёт посещаемости (partition pruning)", "[asyncpg]")
  Rel(lab1, redis, "Кэш данных студентов",                     "[redis-py async]")
@enduml