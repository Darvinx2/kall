# Конспект проекта: как всё устроено

Шпаргалка для защиты. Каждый факт сверен с кодом на момент написания —
если код изменится, конспект нужно будет перепроверить.

## 1. Общая картина

```
Клиент
  │  HTTPS + JWT
  ▼
┌─────────────┐   единственный контейнер, открытый наружу (:8000)
│   gateway   │   аутентификация, валидация, проксирование
└──────┬──────┘
       │  HTTP, только внутри сети compose (порт наружу не публикуется)
       ▼
┌─────────────┐
│    lab1     │   не проверяет JWT сам — доверяет тому, что запрос
└──┬─┬─┬─┬────┘   физически не может прийти ни от кого, кроме gateway
   │ │ │ │
   ES│ │ Redis
     Neo4j│
       PostgreSQL
```

Пять хранилищ и `generator` (одноразовый скрипт, наполняет все пять данными)
живут в той же docker-сети, но `lab1` их видит по внутренним портам, а не по
тем, что опубликованы на хост для отладки.

## 2. Где что лежит

```
gateway/
  main.py              создание приложения, lifespan (httpx.AsyncClient)
  app/config.py         Settings: JWT_SECRET, LAB1_URL, ...
  app/api/
    auth.py             USERS, хеширование паролей (Argon2), выпуск/проверка JWT,
                         get_current_user (401), require_roles (403)
    router.py            /healthcheck, /auth/login, /auth/me
    labs.py               /api/lab1/report — валидация + проксирование в lab1
    schemas.py           Role, TokenResponse, UserPublic, HealthResponse

lab1/
  main.py               lifespan: пулы к PostgreSQL/Redis/Elasticsearch/Neo4j
  app/config.py          Settings: адреса четырёх хранилищ (JWT здесь нет)
  app/report.py          build_report() — вся оркестрация, одна асинхронная функция
  app/api/router.py       /healthcheck, /report — Pydantic-схемы запроса/ответа прямо тут

generator/
  main.py               CLI: generate | drop
  app/config.py          адреса всех пяти хранилищ
  app/models.py          dataclass-сущности + Dataset (форма данных, без логики)
  app/data.py             generate() — строит Dataset в памяти, детерминированно (SEED)
  app/generator.py        run(): вызывает load_* по очереди для всех пяти хранилищ
  app/db/
    postgres.py, redis.py, mongo.py, neo4j.py, elastic.py
                          по одному файлу на хранилище: connect / load / drop
```

## 3. Полный путь запроса `POST /api/lab1/report`

Шаг за шагом, с указанием, какой файл/функция отвечает.

### 3.1. Клиент → gateway

```
POST http://localhost:8000/api/lab1/report
Authorization: Bearer <JWT>
{"term": "...", "period_from": "...", "period_to": "...", "limit": 10}
```

`gateway/app/api/labs.py` — FastAPI сначала валидирует тело запроса моделью
`Lab1ReportRequest`: длина термина 2–200 символов, `term.strip()` не пустой,
`period_from <= period_to`, `limit` от 1 до 100. Если что-то не так — `422`,
и до lab1 запрос не доходит вообще.

### 3.2. Аутентификация

Параметр `_: CurrentUser` в сигнатуре ручки — это `Depends(get_current_user)`
(`gateway/app/api/auth.py`). Цепочка:

1. `OAuth2PasswordBearer`/`HTTPBearer` достаёт токен из заголовка `Authorization`.
2. `decode_access_token()` проверяет подпись (HS256, секрет из `.env`),
   срок действия (`exp`), издателя (`iss`) и аудиторию (`aud`) через `jwt.decode(...)`.
3. Нет токена или он битый/просрочен → `401` с заголовком `WWW-Authenticate: Bearer`.
4. Токен валиден → достаём пользователя из `USERS` по `sub` (claim в токене),
   возвращаем `UserPublic`.

Ролей на этой ручке не требуется — любой аутентифицированный может её вызвать
(в отличие от `/auth/users`, которая только для `admin`).

### 3.3. Проксирование в lab1

Всё ещё в `labs.py`. `request.app.state.http_client` — это единственный на
весь процесс `httpx.AsyncClient`, созданный в `lifespan` (`gateway/main.py`)
при старте приложения и переиспользуемый между запросами (не создаётся заново
на каждый вызов — держит пул TCP-соединений).

```python
response = await client.post(f"{settings.lab1_url}/report", json=body.model_dump(mode="json"))
```

`settings.lab1_url` в контейнере равен `http://lab1:8000` — это **имя
сервиса** из `docker-compose.yaml`, Docker резолвит его через встроенный DNS
в IP-адрес контейнера `uni-lab1` внутри сети `university_default`. Порт `8000`
здесь — внутренний порт контейнера lab1, не путать с `8001`, который никуда
не опубликован (у lab1 такого порта на хосте вообще нет).

Если `lab1` недоступна (сеть/контейнер упал) — `httpx.RequestError` ловится
и превращается в `HTTPException(503)` с текстом причины. Если lab1 ответила
(даже с ошибкой) — `response.json()` возвращается клиенту как есть, gateway
его не переформатирует.

### 3.4. Внутри lab1

`lab1` порт наружу не публикует → снаружи docker-сети до неё физически не
достучаться → она не проверяет JWT вообще, в `lab1/app/api/router.py` ручка
`/report` не имеет зависимости на аутентификацию. Это решение обосновывается
именно топологией сети, а не «доверием» само по себе.

Ручка валидирует тело своей же моделью `ReportRequest` (та же валидация, что
на gateway — задублирована намеренно: lab1 не полагается на то, что перед ней
всегда стоит именно gateway) и вызывает `build_report()` из `report.py`.

### 3.5. `build_report()` — четыре хранилища подряд

Один `async`-вызов, без классов и абстракций, просто последовательность:

**Шаг 1 — Elasticsearch.**
```python
await elastic.search(index="lectures", query={"match_phrase": {"annotation": term}}, ...)
```
`match_phrase`, а не `match` — задание про «термин ИЛИ ФРАЗУ», и `match_phrase`
не даст ложных срабатываний, если слова встретились порознь. Индекс `lectures`
использует анализатор `russian`, поэтому «нейронных сетей» находит «нейронные
сети» — падежи и число не имеют значения. Из ответа берём `lecture_id[]` и
`course_id[]` (оба поля лежат в документе лекции).

Если пусто — сразу отдаём пустой отчёт, дальше в Neo4j/PostgreSQL не ходим.

**Шаг 2 — Neo4j.**
```cypher
MATCH (st:Student)-[:ENROLLED]->(c:Course)
WHERE c.id IN $course_ids
RETURN st.id AS student_id, c.id AS course_id
```
Возвращает **пары** `(student_id, course_id)`, не плоский список студентов.
Это критично: среди совпавших курсов есть выборные, и если бы мы просто
собрали множество `{student_id}`, студент, записанный на один из совпавших
курсов, получил бы в отчёт занятия и **другого** совпавшего курса, который
не выбирал. Проверено на данных: без пар в популяцию по пяти выборным
курсам попадает 131 студент, реально записаны только 124.

**Шаг 3 — PostgreSQL.**
```sql
WITH eligible AS (
    SELECT * FROM unnest($student_ids::uuid[], $course_ids::uuid[]) AS e(student_id, course_id)
)
SELECT st.id, count(*) AS planned, sum(coalesce(a.is_present::int,0)) AS attended
FROM schedule sch
JOIN lecture l ON l.id = sch.lecture_id
JOIN student st ON st.group_id = sch.group_id
JOIN eligible e ON e.student_id = st.id AND e.course_id = l.course_id
LEFT JOIN attendance a ON a.schedule_id = sch.id AND a.student_id = st.id
     AND a.week_start_date BETWEEN $week_from AND $week_to
WHERE sch.lecture_id = ANY($lecture_ids::uuid[])
  AND sch.week_start_date BETWEEN $week_from AND $week_to
GROUP BY st.id
ORDER BY attended::numeric / planned ASC
LIMIT $limit
```
`unnest(arr1, arr2)` разворачивает два параллельных массива построчно
(zip) — так пары из Neo4j попадают в SQL без потери связи между student_id
и course_id. Join именно по паре `(e.student_id, e.course_id) = (st.id, l.course_id)`,
а не по двум независимым `ANY(...)` — иначе вернулся бы тот же баг, что
чинили в Neo4j-шаге, только на уровне SQL.

`LEFT JOIN attendance` — знаменатель считается по `schedule` (сколько занятий
реально было), а не по `attendance` (сколько отметок есть): если отметки нет,
это пропуск, а не повод исключить занятие из отчёта.

Фильтр `week_start_date BETWEEN ...` идёт по **ключу партиционирования**
таблицы `attendance` (44 недельные партиции на учебный год) — Postgres
читает только нужные недели, а не всю таблицу целиком (partition pruning).

**Шаг 4 — Redis.**
```
GET student:id:{uuid}       → номер зачётки
HGETALL student:{зачётка}   → карточка студента
```
Два прохода `pipeline` (не поштучные запросы) — сначала все `GET`, потом все
`HGETALL`. Первичный ключ в Redis — номер зачётки (так по заданию), но у
PostgreSQL на руках только `student_id` (UUID), поэтому нужен вторичный
индекс `student:id:{uuid} → зачётка`, иначе Redis тут был бы не нужен вовсе.

### 3.6. Ответ — назад по той же цепочке

`build_report()` возвращает `dict` → `lab1/app/api/router.py` собирает
`ReportResponse` (Pydantic, с `computed_field` для `full_name`) → отдаёт
JSON → gateway получает его как `response.json()` и пробрасывает клиенту
без изменений → клиент видит финальный отчёт.

## 4. Как контейнеры находят друг друга

Все сервисы в одной сети compose (`university_default`, создаётся
автоматически по имени проекта). Docker поднимает встроенный DNS-резолвер:
имя сервиса из `docker-compose.yaml` (`postgres`, `redis`, `lab1`, ...)
резолвится в IP контейнера **только для тех, кто в той же сети** — с хоста
эти имена не резолвятся вообще, только `localhost:<опубликованный порт>`.

| Сервис | Порт внутри сети | Порт на хосте | Кто видит |
|---|---|---|---|
| gateway | 8000 | **8000** | все — единственная точка входа |
| lab1 | 8000 | — (не опубликован) | только сервисы в сети compose |
| postgres | 5432 | 5433 | сеть + хост (для дебага) |
| redis | 6379 | 6380 | сеть + хост |
| mongo | 27017 | 27018 | сеть + хост |
| neo4j | 7687 (bolt) | 7688 | сеть + хост |
| elasticsearch | 9200 | 9201 | сеть + хост |

Порты на хосте у баз сдвинуты специально: 5432 и 6379 заняты другим проектом
на машине разработчика — это чисто локальная деталь окружения, к архитектуре
отношения не имеет.

`depends_on: { condition: service_healthy }` — gateway не стартует, пока
`lab1` не прошла `HEALTHCHECK`; `lab1` не стартует, пока не здоровы все
четыре её хранилища. Без этого лабы падали бы при первом же запросе сразу
после `docker compose up`, пока базы ещё поднимаются.

## 5. Пять хранилищ — что где и почему

| Хранилище | Что хранит | Зачем именно оно |
|---|---|---|
| **PostgreSQL** | source of truth: 13 таблиц, `attendance` партиционирована по неделе (44 партиции) | единственное место с фактом посещения (`is_present`); партиционирование даёт partition pruning по периоду отчёта |
| **Redis** | карточки студентов, ключ — номер зачётки; вторичный индекс `id → зачётка` | доступ к профилю за O(1) без `JOIN` к `student/student_group/specialty` на каждой строке отчёта |
| **MongoDB** | документы групп и курсов с вложенным составом | «полная информация о группе/курсе» одним `findOne`, без сборки из нескольких таблиц (под лабы №2/№3) |
| **Neo4j** | граф `Specialty–Group–Student–Course`, связь `ENROLLED {is_elective}` | обход связей с учётом курсов по выбору — то, что в реляционной модели потребовало бы многоходовых `JOIN` |
| **Elasticsearch** | индекс `lectures`, анализатор `russian` | полнотекстовый поиск по словоформам; `ILIKE` в PostgreSQL не находит «нейронных сетей» по запросу «нейронные сети» |

`generator` — единственный, кто пишет во все пять. Он не сервис, а
одноразовая задача (`profiles: ["seed"]` в compose) — строит `Dataset` в
памяти Python (`generate()`, детерминированно по `SEED`) и раскладывает его
по хранилищам по очереди, PostgreSQL первым.
