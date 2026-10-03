"""Проксирование в lab-сервисы.

Задание требует «набор API методов для вызова… лабораторной работы с
указанными входными параметрами». Маршрут явный и типизированный — не
wildcard-прокси, — поэтому параметры видны в OpenAPI и проверяются здесь же,
до похода в lab1. Сама лаба во внутренней сети compose и токен не проверяет:
единственная точка проверки — этот маршрут за CurrentUser.
"""

from datetime import date
from typing import Annotated, Any, Self

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gateway.app.api.auth import CurrentUser
from gateway.app.config import SettingsDep

__all__ = ("router",)

router = APIRouter(prefix="/api", tags=["Лабораторные работы"])


class Lab1ReportRequest(BaseModel):
    """Повторяет валидацию lab1/app/api/router.py:ReportRequest.

    Дублирование намеренное: gateway — внешняя граница системы и обязан
    проверять вход сам, а не полагаться на 422 от внутреннего сервиса.
    """

    model_config = ConfigDict(extra="forbid")

    term: Annotated[str, Field(min_length=2, max_length=200)]
    period_from: date
    period_to: date
    limit: Annotated[int, Field(ge=1, le=100)] = 10

    @field_validator("term")
    @classmethod
    def strip_term(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("термин не может состоять из одних пробелов")
        return stripped

    @model_validator(mode="after")
    def check_period(self) -> Self:
        if self.period_from > self.period_to:
            raise ValueError("period_from не может быть позже period_to")
        return self


class Lab2ReportRequest(BaseModel):
    """Повторяет валидацию lab2/app/api/schemas.py:ReportRequest."""

    model_config = ConfigDict(extra="forbid")

    technical_requirement: Annotated[str, Field(min_length=2, max_length=200)]
    semester: Annotated[int, Field(ge=1, le=2)]
    enrollment_year: Annotated[int, Field(ge=2000, le=2100)]
    limit: Annotated[int, Field(ge=1, le=100)] = 20

    @field_validator("technical_requirement")
    @classmethod
    def strip_requirement(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("требование не может состоять из одних пробелов")
        return stripped


class Lab3ReportRequest(BaseModel):
    """Повторяет валидацию lab3/app/api/schemas.py:ReportRequest."""

    model_config = ConfigDict(extra="forbid")

    group_name: Annotated[str, Field(min_length=2, max_length=50)]

    @field_validator("group_name")
    @classmethod
    def strip_group(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("название группы не может состоять из одних пробелов")
        return stripped


async def _proxy(request: Request, url: str, body: BaseModel, service: str) -> Any:
    """Один и тот же поход в лабу: маршруты отличаются только адресом."""
    client: httpx.AsyncClient = request.app.state.http_client
    try:
        response = await client.post(url, json=body.model_dump(mode="json"))
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{service} недоступна: {exc}",
        ) from exc
    return response.json()


@router.post("/lab1/report")
async def lab1_report(
    body: Lab1ReportRequest,
    request: Request,
    settings: SettingsDep,
    _: CurrentUser,
) -> Any:
    """Отчёт лабы №1: студенты с минимальным % посещения по термину."""
    return await _proxy(request, f"{settings.lab1_url}/report", body, "lab1")


@router.post("/lab2/report")
async def lab2_report(
    body: Lab2ReportRequest,
    request: Request,
    settings: SettingsDep,
    _: CurrentUser,
) -> Any:
    """Отчёт лабы №2: объём аудитории по требованиям к тех. средствам."""
    return await _proxy(request, f"{settings.lab2_url}/report", body, "lab2")


@router.post("/lab3/report")
async def lab3_report(
    body: Lab3ReportRequest,
    request: Request,
    settings: SettingsDep,
    _: CurrentUser,
) -> Any:
    """Отчёт лабы №3: часы по спец. дисциплинам кафедры для группы."""
    return await _proxy(request, f"{settings.lab3_url}/report", body, "lab3")
