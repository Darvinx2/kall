@startuml C4_Context
!include <C4/C4_Context>

LAYOUT_WITH_LEGEND()

title Диаграмма контекста (Level 1) — UniversityMicroservices

Person(user, "Пользователь", "Аналитик кафедры, вызывает отчёты через HTTP API с JWT-токеном")

System(system, "UniversityMicroservices", "API Gateway с JWT-аутентификацией и набором лабораторных сервисов, каждый — отдельный HTTP-сервис поверх пяти хранилищ данных")

Rel(user, system, "POST /auth/login, POST /api/lab1/report", "HTTPS + JWT")
Rel(system, user, "JSON-отчёт", "HTTPS")

@enduml