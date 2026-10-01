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