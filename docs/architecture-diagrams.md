# Диаграммы архитектуры

Нотации: **C4** (Context, Container, Component) — PlantUML + библиотека
C4-PlantUML (`!include <C4/...>`), и **DFD** в нотации Йордана–Коуда
(Level 0, Level 1) — PlantUML `rectangle`.

Рендер: [plantuml.com/plantuml](https://www.plantuml.com/plantuml/uml/) или
локально `plantuml` с `-tsvg`. Диаграммы отражают то, что реально реализовано
и проверено в коде: gateway + лаба №1. Лабы №2 и №3 отмечены на диаграмме
контейнеров как запланированные — они лягут в ту же архитектуру, но ещё не
написаны.

---

## C4 — Level 1: Context

```plantuml
@startuml C4_Context
!include <C4/C4_Context>

LAYOUT_WITH_LEGEND()

title Диаграмма контекста (Level 1) — UniversityMicroservices

Person(user, "Пользователь", "Аналитик кафедры, вызывает отчёты через HTTP API с JWT-токеном")

System(system, "UniversityMicroservices", "API Gateway с JWT-аутентификацией и набором лабораторных сервисов, каждый — отдельный HTTP-сервис поверх пяти хранилищ данных")

Rel(user, system, "POST /auth/login, POST /api/lab1/report", "HTTPS + JWT")
Rel(system, user, "JSON-отчёт", "HTTPS")

@enduml
```

---

## C4 — Level 2: Container

```plantuml
@startuml C4_Containers
!include <C4/C4_Container>

LAYOUT_WITH_LEGEND()

title Диаграмма контейнеров (Level 2) — UniversityMicroservices

Person(user, "Пользователь", "Формирует отчёты через API")

System_Boundary(app, "UniversityMicroservices") {
    Container(gateway, "Gateway", "FastAPI, Python 3.14, :8000", "Единственная точка входа. JWT-аутентификация (HS256, пользователи в коде, пароли — Argon2), валидация входных параметров, проксирование в лабы через httpx.AsyncClient")
    Container(lab1, "lab1", "FastAPI, Python 3.14, внутренний :8000", "Отчёт: 10 студентов с минимальным % посещения лекций по термину за период. Порт наружу не публикуется — недоступна вне сети compose, поэтому сама JWT не проверяет: доверяет тому, что запрос пришёл только от gateway")
    Container(lab2, "lab2 (план)", "FastAPI", "Аудиторная нагрузка по курсу — не реализована")
    Container(lab3, "lab3 (план)", "FastAPI", "Часы по спец. дисциплинам для группы — не реализована")
    Container(generator, "generator", "Python, одноразовый запуск (profile: seed)", "Строит датасет в памяти и раскладывает его по пяти хранилищам. PostgreSQL — source of truth, остальные четыре — проекции")
}

System_Boundary(storages, "Хранилища данных") {
    ContainerDb(pg, "PostgreSQL", ":5432 (хост 5433)", "Источник истины. 13 таблиц, attendance партиционирована по неделе (44 партиции)")
    ContainerDb(redis, "Redis", ":6379 (хост 6380)", "Карточки студентов по номеру зачётной книжки: HASH + вторичный индекс id -> зачётка")
    ContainerDb(mongo, "MongoDB", ":27017 (хост 27018)", "Документы групп и курсов с вложенным составом — под лабы №2/№3")
    ContainerDb(neo4j, "Neo4j", ":7687 (хост 7688)", "Граф Specialty-Group-Student-Course, связь ENROLLED с учётом курсов по выбору")
    ContainerDb(es, "Elasticsearch", ":9200 (хост 9201)", "Индекс lectures, анализатор russian, полнотекстовый поиск по аннотациям")
}

Rel(user, gateway, "Запрос отчёта", "HTTPS + JWT")
Rel(gateway, lab1, "Проксирует, токен не пробрасывает", "HTTP, внутри сети compose")

Rel(lab1, es, "match_phrase по annotation", "REST")
Rel(lab1, neo4j, "ENROLLED: курсы -> пары (студент, курс)", "Cypher")
Rel(lab1, pg, "schedule + LEFT JOIN attendance, по парам", "SQL")
Rel(lab1, redis, "карточки топ-10 по зачётке", "pipeline")

Rel(generator, pg, "INSERT / COPY", "SQL")
Rel(generator, redis, "HSET pipeline")
Rel(generator, mongo, "insert_many")
Rel(generator, neo4j, "MERGE", "Cypher")
Rel(generator, es, "bulk index")

@enduml
```

---

## C4 — Level 3: Component

Разворачиваем gateway и lab1 — единственные два контейнера с реализованной
логикой.

Компоненты gateway (аутентификация и проксирование) и компоненты lab1
(оркестрация четырёх хранилищ) — двумя отдельными диаграммами, каждая
разворачивает свой контейнер по-файлово: один компонент = один файл с
одной ответственностью. Слоя Repository/адаптеров нет ни там, ни там —
оркестраторы (`labs.py`, `report.py`) обращаются к клиентам хранилищ
напрямую, без прослойки; так решили осознанно, для четырёх-пяти вызовов
подряд отдельный класс на каждое хранилище был бы лишней абстракцией.

### Gateway

```plantuml
@startuml C4_Components_Gateway
!include <C4/C4_Component>

LAYOUT_WITH_LEGEND()

AddElementTag("entry",   $bgColor="#90caf9", $fontColor="#000000", $legendText="«entrypoint»")
AddElementTag("router",  $bgColor="#42a5f5", $fontColor="#000000", $legendText="«router»")
AddElementTag("service", $bgColor="#1565c0", $fontColor="#ffffff", $legendText="«service»")
AddElementTag("contract",$bgColor="#7986cb", $fontColor="#ffffff", $legendText="«contract» (DTO)")
AddElementTag("config",  $bgColor="#455a64", $fontColor="#ffffff", $legendText="«config»")
AddElementTag("ext",     $bgColor="#546e7a", $fontColor="#ffffff", $legendText="внешний контейнер")

title Диаграмма компонентов (Level 3) — Gateway

Person(user, "Пользователь")

System_Boundary(gateway_container, "Контейнер: Gateway") {
    Component(main, "main.py", "FastAPI(lifespan=...)", "Собирает приложение, регистрирует оба роутера. lifespan создаёт ОДИН httpx.AsyncClient на весь процесс (app.state.http_client) и закрывает его при остановке", $tags="entry")

    Component(router, "api/router.py", "FastAPI APIRouter", "GET /healthcheck, POST /auth/login (form-data, не JSON), GET /auth/me", $tags="router")
    Component(labs, "api/labs.py", "FastAPI APIRouter", "Lab1ReportRequest — своя копия валидации lab1 (term 2-200 симв., period_from<=period_to). POST /api/lab1/report: 401 без токена, 422 при невалидном теле, 503 если lab1 недоступна", $tags="router")

    Component(auth, "api/auth.py", "PyJWT + pwdlib[argon2]", "USERS = {admin, analyst}, StoredUser с хешем пароля. hash_password/verify_password, create_access_token/decode_access_token, get_current_user (401), require_roles (403)", $tags="service")

    Component(schemas, "api/schemas.py", "Pydantic BaseModel", "Role (StrEnum), TokenResponse, UserPublic, HealthResponse — общий контракт, которым пользуются router.py и auth.py", $tags="contract")
    Component(config, "config.py", "pydantic-settings", "Settings: JWT_SECRET (SecretStr), JWT_ALGORITHM, LAB1_URL, HTTP_TIMEOUT_SECONDS. get_settings() с @lru_cache", $tags="config")
}

Container_Ext(lab1, "lab1", "[FastAPI]", "Внутри сети compose, порт наружу не опубликован, JWT не проверяет", $tags="ext")

Rel(user, router, "POST /auth/login (username, password)", "HTTPS, form-data")
Rel(user, router, "GET /auth/me + JWT", "HTTPS")
Rel(user, labs, "POST /api/lab1/report + JWT", "HTTPS")

Rel(main, router, "include_router()")
Rel(main, labs, "include_router()")
Rel(main, config, "get_settings() -> http_timeout_seconds")

Rel(router, auth, "authenticate_user(), create_access_token()\n-> TokenResponse")
Rel(router, schemas, "возвращает HealthResponse/TokenResponse/UserPublic")
Rel(auth, schemas, "StoredUser.to_public() -> UserPublic")
Rel(auth, config, "jwt_secret, jwt_algorithm, jwt_access_ttl_minutes")

Rel(labs, auth, "CurrentUser = Depends(get_current_user)\nнет/битый токен -> 401", "FastAPI Depends")
Rel(labs, config, "settings.lab1_url")
Rel(labs, main, "request.app.state.http_client\n(тот же клиент, что создан в lifespan)")
Rel(labs, lab1, "POST /report (JSON, без токена)\nRequestError -> 503", "HTTP, http://lab1:8000")

@enduml
```

### lab1

```plantuml
@startuml C4_Components_Lab1
!include <C4/C4_Component>

LAYOUT_WITH_LEGEND()

AddElementTag("entry",        $bgColor="#90caf9", $fontColor="#000000", $legendText="«entrypoint»")
AddElementTag("router",       $bgColor="#42a5f5", $fontColor="#000000", $legendText="«router»")
AddElementTag("orchestrator", $bgColor="#1565c0", $fontColor="#ffffff", $legendText="«orchestrator»")
AddElementTag("contract",     $bgColor="#7986cb", $fontColor="#ffffff", $legendText="«contract» (DTO)")
AddElementTag("config",       $bgColor="#455a64", $fontColor="#ffffff", $legendText="«config»")
AddElementTag("ext_container",$bgColor="#546e7a", $fontColor="#ffffff", $legendText="внешний контейнер")

title Диаграмма компонентов (Level 3) — lab1

Container_Ext(gateway, "Gateway", "[FastAPI]", "Проверил JWT сам, токен не пробрасывает", $tags="ext_container")

System_Boundary(lab1, "Контейнер: lab1") {
    Component(main, "main.py", "FastAPI(lifespan=...)", "lifespan создаёт 4 клиента на весь процесс: AsyncConnectionPool (PG), Redis.from_url, AsyncElasticsearch, AsyncGraphDatabase.driver — складывает в app.state, закрывает при остановке", $tags="entry")

    Component(router, "api/router.py", "FastAPI APIRouter", "GET /healthcheck, POST /report: принимает ReportRequest, вызывает build_report(), собирает ReportResponse из dict", $tags="router")
    Component(schemas, "api/schemas.py", "Pydantic BaseModel", "HealthResponse, ReportRequest (валидация term/period/limit), StudentInfo (computed_field full_name), ReportItemResponse, ReportPeriod, ReportResponse", $tags="contract")

    Component(orchestrator, "report.py: build_report()", "async, одна функция", "4 шага подряд по 4 хранилищам; ранний выход с пустым отчётом, если ES или Neo4j вернули ноль совпадений", $tags="orchestrator")

    Component(config, "config.py", "pydantic-settings", "Settings: адреса Postgres/Redis/Elasticsearch/Neo4j. JWT-полей нет — lab1 токен не проверяет", $tags="config")
}

ContainerDb(es, "Elasticsearch", "[индекс lectures]")
ContainerDb(neo4j, "Neo4j", "[Student-ENROLLED->Course]")
ContainerDb(pg, "PostgreSQL", "[schedule, attendance]")
ContainerDb(redis, "Redis", "[student:{card}]")

Rel(gateway, router, "POST /report (JSON, без токена)", "HTTP, внутри сети compose")

Rel(main, router, "include_router()")
Rel(main, config, "get_settings() -> DSN четырёх хранилищ")

Rel(router, schemas, "ReportRequest -> валидация -> ReportResponse")
Rel(router, orchestrator, "await build_report(elastic, neo4j_driver, pg_pool, redis, ...)")
Rel(orchestrator, main, "клиенты из request.app.state\n(созданы один раз в lifespan)")

Rel(orchestrator, es, "1. match_phrase(annotation)\n-> lecture_id[], course_id[]", "AsyncElasticsearch, HTTP")
Rel(orchestrator, neo4j, "2. MATCH (Student)-[:ENROLLED]->(Course)\nWHERE course.id IN course_ids\n-> пары (student_id, course_id)", "neo4j.AsyncDriver, Bolt")
Rel(orchestrator, pg, "3. schedule JOIN lecture JOIN student\nJOIN eligible(unnest пар)\nLEFT JOIN attendance\n(partition pruning по week_start_date)", "psycopg_pool.AsyncConnectionPool")
Rel(orchestrator, redis, "4. student:id:{uuid} -> зачётка\n-> HGETALL student:{зачётка}", "redis.asyncio, pipeline")

@enduml
```

---

## DFD — Level 0 (контекстная диаграмма)

```plantuml
@startuml DFD_Level0
skinparam rectangle {
    BorderColor #000000
    FontSize 14
}
skinparam rectangle<<rounded>> {
    BorderColor #000000
    BackgroundColor #FFFFFF
    FontSize 14
    BorderRadius 15
}
skinparam arrow {
    Color #000000
    FontSize 12
}

rectangle "Пользователь" as User
rectangle "UniversityMicroservices" as System

User -right-> System : JWT-токен, параметры отчёта
System -left-> User : JSON-отчёт

@enduml
```

---

## DFD — Level 1 (декомпозиция: путь запроса лабы №1)

Показывает ровно то, что делает `build_report()` — четыре хранилища подряд,
с реальными потоками данных между ними.

```plantuml
@startuml DFD_Level1
skinparam rectangle {
    BorderColor #000000
    FontSize 12
}
skinparam rectangle<<rounded>> {
    BorderColor #000000
    BackgroundColor #FFFFFF
    FontSize 12
    BorderRadius 15
}
skinparam rectangle<<datastore>> {
    BorderStyle dashed
    BackgroundColor #F9F9F9
    BorderColor #000000
}
skinparam arrow {
    Color #000000
}

rectangle "Пользователь" as User

rectangle "1.0\nАутентификация\nJWT (HS256), Argon2" as Auth <<rounded>>
rectangle "2.0\nВалидация и\nпроксирование\n(gateway -> lab1)" as Proxy <<rounded>>
rectangle "3.0\nПоиск лекций\nпо термину" as Search <<rounded>>
rectangle "4.0\nОтбор студентов\nс учётом выборных курсов" as Eligible <<rounded>>
rectangle "5.0\nРасчёт посещаемости\nза период" as Attendance <<rounded>>
rectangle "6.0\nКарточки\nстудентов" as Profiles <<rounded>>

rectangle "Elasticsearch\nlectures" as ES <<datastore>>
rectangle "Neo4j\nStudent-ENROLLED->Course" as Neo4j <<datastore>>
rectangle "PostgreSQL\nschedule, attendance" as PG <<datastore>>
rectangle "Redis\nstudent:{card}" as Redis <<datastore>>

User -right-> Auth : username, password
Auth -left-> User : access_token

User -down-> Proxy : JWT + term, period, limit
Proxy -down-> Search : term

Search -down-> ES : match_phrase(annotation)
ES -up-> Search : lecture_id[], course_id[]

Search -down-> Eligible : course_id[]
Eligible -down-> Neo4j : MATCH (st)-[:ENROLLED]->(c)\nWHERE c.id IN course_ids
Neo4j -up-> Eligible : пары (student_id, course_id)

Eligible -down-> Attendance : пары + lecture_id[] + период
Attendance -down-> PG : schedule JOIN eligible\nLEFT JOIN attendance
PG -up-> Attendance : student_id, planned, attended

Attendance -down-> Profiles : student_id[] топ-N
Profiles -down-> Redis : student:id:{uuid} -> зачётка -> HGETALL
Redis -up-> Profiles : карточки

Profiles -up-> Proxy : JSON-отчёт
Proxy -up-> User : JSON-отчёт

@enduml
```

### Обоснование потоков (для отчёта)

| Шаг | Хранилище | Почему именно оно |
|---|---|---|
| 3.0 | Elasticsearch | обратный индекс с анализатором `russian` находит термин в любой словоформе; в PostgreSQL тот же поиск был бы перебором по `ILIKE` без индекса |
| 4.0 | Neo4j | среди совпавших курсов есть выборные — обход `ENROLLED` даёт **пары** (студент, курс), а не плоский список: иначе студент, записанный на один совпавший курс, получил бы в отчёт занятия и другого совпавшего курса, который не выбирал (проверено на реальных данных: 131 студент без фильтра против 124 фактически записанных на пяти выборных курсах) |
| 5.0 | PostgreSQL | единственное хранилище, где есть факт посещения (`is_present`); `attendance` партиционирована по неделе — фильтр по `week_start_date` читает только недели периода, а не всю таблицу |
| 6.0 | Redis | карточка студента по номеру зачётной книжки за O(1); в PostgreSQL это был бы дополнительный `JOIN` к `student`, `student_group`, `specialty` на каждой строке отчёта |
