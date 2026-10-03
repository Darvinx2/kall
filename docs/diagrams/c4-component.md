@startuml C4_Components
!include <C4/C4_Component>

  LAYOUT_WITH_LEGEND()

  AddElementTag("entry",        $bgColor="#90caf9", $fontColor="#000000", $legendText="«entrypoint»")
  AddElementTag("router",       $bgColor="#42a5f5", $fontColor="#000000", $legendText="«router»")
  AddElementTag("middleware",   $bgColor="#4a148c", $fontColor="#ffffff", $legendText="«middleware»")
  AddElementTag("contract",     $bgColor="#7986cb", $fontColor="#ffffff", $legendText="«contract» (DTO)")
  AddElementTag("controller",   $bgColor="#1565c0", $fontColor="#ffffff", $legendText="«controller»")
  AddElementTag("orchestrator", $bgColor="#0d47a1", $fontColor="#ffffff", $legendText="«orchestrator»")
  AddElementTag("repository",   $bgColor="#1976d2", $fontColor="#ffffff", $legendText="«repository»")
  AddElementTag("config",       $bgColor="#455a64", $fontColor="#ffffff", $legendText="«config»")
  AddElementTag("ext_container",$bgColor="#546e7a", $fontColor="#ffffff", $legendText="внешний контейнер")

  title C4 Level 3 — Component Diagram\nUniversityMicroservices — компоненты Gateway и Lab1\n(Lab2 и Lab3 построены по той же схеме: роутер -> оркестратор -> репозитории хранилищ)

  Person(user, "Пользователь", "Аналитик кафедры")

  System_Boundary(gateway_container, "Контейнер: API Gateway") {

      Component(gw_main, "Application Factory", "[FastAPI(lifespan) / main.py]", "Регистрирует оба роутера.\nlifespan создаёт один httpx.AsyncClient\nна процесс и закрывает при остановке", $tags="entry")

      Component(gw_router, "Auth Router", "[APIRouter / api/router.py]", "GET /healthcheck,\nPOST /auth/login (form-data),\nGET /auth/me", $tags="router")

      Component(gw_labs, "Labs Router", "[APIRouter / api/labs.py]", "POST /api/lab1/report.\nСвоя копия валидации входа:\ngateway — внешняя граница системы", $tags="router")

      Component(gw_auth, "Auth Service", "[PyJWT + pwdlib(argon2) / api/auth.py]", "Хеши паролей, выпуск и разбор JWT,\nget_current_user -> 401,\nrequire_roles -> 403", $tags="middleware")

      Component(gw_schemas, "Auth Contract", "[Pydantic / api/schemas.py]", "Role, TokenResponse,\nUserPublic, HealthResponse", $tags="contract")

      Component(gw_config, "Settings", "[pydantic-settings / config.py]", "JWT_SECRET (SecretStr), LAB1_URL,\nHTTP_TIMEOUT_SECONDS.\nget_settings() с @lru_cache", $tags="config")
  }

  System_Boundary(lab1_container, "Контейнер: Lab1 Service") {

      Component(main, "Application Factory", "[FastAPI(lifespan) / main.py]", "Создаёт по одному клиенту на процесс:\nпул psycopg, AsyncElasticsearch,\nдрайвер Neo4j, redis.asyncio", $tags="entry")

      Component(router, "HTTP API Router", "[APIRouter / api/router.py]", "GET /healthcheck, POST /report.\nДостаёт клиенты из app.state", $tags="router")

      Component(schemas, "Request/Response Contract", "[Pydantic / api/schemas.py]", "ReportRequest: extra=forbid,\nterm 2-200 симв., period_from<=period_to,\nlimit 1-100 (по умолчанию 10)", $tags="contract")

      Component(report_endpoint, "Report Endpoint", "[POST /report]", "Контроллер отчёта:\n10 студентов с минимальным\nпроцентом посещения лекций", $tags="controller")

      Component(pipeline, "Report Orchestrator", "[build_report() / report.py]", "Координирует 4 шага по хранилищам,\nсобирает items и matched_courses", $tags="orchestrator")

      Component(es_repo, "Elasticsearch Repository", "[AsyncElasticsearch]", "Шаг 1: multi_match type=phrase\nпо title^3, annotation^2, content_text\n+ filter lecture_type = «лекция»", $tags="repository")

      Component(neo_repo, "Neo4j Repository", "[ELIGIBLE_PAIRS_CYPHER]", "Шаг 2: MATCH (Student)-[:ENROLLED]->(Course)\n-> пары (студент, курс)", $tags="repository")

      Component(pg_repo, "PostgreSQL Repository", "[ATTENDANCE_SQL]", "Шаг 3: count(*) FILTER (WHERE is_present),\npruning по week_start_date,\nточные границы по scheduled_date", $tags="repository")

      Component(redis_repo, "Redis Repository", "[_load_cards()]", "Шаг 4: MGET student:id:{uuid}\n-> пайплайн HGETALL student:{зачётка}.\nБез TTL: витрина, а не кэш", $tags="repository")

      Component(config, "Settings", "[pydantic-settings / config.py]", "Хосты и порты четырёх хранилищ,\nget_settings() с @lru_cache", $tags="config")
  }

  Container_Ext(es_db,    "Elasticsearch", "[elasticsearch:9.5.1]", "Индекс lectures,\nанализатор russian", $tags="ext_container")
  Container_Ext(neo_db,   "Neo4j",         "[neo4j:5-community]",   "Связи группа-студент-курс", $tags="ext_container")
  Container_Ext(pg_db,    "PostgreSQL",    "[postgres:16-alpine]",  "Источник истины,\nпартиционированная attendance", $tags="ext_container")
  Container_Ext(redis_db, "Redis",         "[redis:7-alpine]",      "Карточки студентов,\nключ — номер зачётки", $tags="ext_container")

  ' --- Вход и аутентификация ---
  Rel_D(user, gw_router, "POST /auth/login, GET /auth/me", "[HTTPS]")
  Rel_D(user, gw_labs, "POST /api/lab1/report + JWT", "[HTTPS]")
  Rel_R(gw_main, gw_config, "get_settings()")
  Rel_D(gw_main, gw_router, "include_router()")
  Rel_R(gw_router, gw_auth, "authenticate_user(),\ncreate_access_token()")
  Rel_R(gw_auth, gw_schemas, "to_public() -> UserPublic")
  Rel_D(gw_labs, gw_auth, "CurrentUser = Depends(get_current_user)\nнет токена -> 401", "[FastAPI Depends]")

  ' --- Граница контейнеров ---
  Rel_D(gw_labs, router, "POST /report (JSON, без токена)\nRequestError -> 503", "[HTTP, http://lab1:8000]")

  ' --- Внутри лабы ---
  Rel_D(main, router, "include_router(),\nклиенты через app.state")
  Rel_R(main, config, "get_settings()")
  Rel_R(router, schemas, "Валидация тела,\nсериализация ответа")
  Rel_D(router, report_endpoint, "Маршрутизация")
  Rel_D(report_endpoint, pipeline, "build_report(elastic, neo4j_driver,\npg_pool, redis_client, ...)")

  Rel_D(pipeline, es_repo,    "1. Термин или фраза")
  Rel_D(pipeline, neo_repo,   "2. Курсы -> студенты")
  Rel_D(pipeline, pg_repo,    "3. Проценты посещения")
  Rel_D(pipeline, redis_repo, "4. Карточки студентов")
  Rel_L(redis_repo, pg_repo,  "Откат при промахе витрины")

  ' --- Репозитории к хранилищам ---
  Rel_D(es_repo,    es_db,    "POST /lectures/_search", "[HTTPS]")
  Rel_D(neo_repo,   neo_db,   "Cypher MATCH",           "[Bolt]")
  Rel_D(pg_repo,    pg_db,    "SELECT ... GROUP BY",    "[PostgreSQL wire]")
  Rel_D(redis_repo, redis_db, "MGET / HGETALL",         "[RESP]")

  ' --- Выравнивание: репозитории и хранилища в один ряд, без пересечений ---
  Lay_R(es_repo, neo_repo)
  Lay_R(neo_repo, pg_repo)
  Lay_R(pg_repo, redis_repo)
  Lay_R(es_db, neo_db)
  Lay_R(neo_db, pg_db)
  Lay_R(pg_db, redis_db)

@enduml
