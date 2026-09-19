"""HTTP-контракт лабы №1: одна ручка отчёта и healthcheck.

Модели запроса/ответа лежат прямо здесь, не в отдельном schemas.py —
их три штуки, выносить в отдельный файл ради этого незачем.
"""

from datetime import date
from typing import Annotated, Self

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from lab1.app.config import SERVICE_NAME, SERVICE_VERSION
from lab1.app.report import build_report

__all__ = ("router",)

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class ReportRequest(BaseModel):
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


class StudentInfo(BaseModel):
    """Полная информация о студенте — состав полей из задания."""

    card_number: str = Field(alias="card_number")
    last_name: str
    first_name: str
    patronymic: str
    email: str
    phone: str
    status: str
    enrollment_date: str
    group_name: str
    specialty_name: str
    specialty_code: str

    model_config = ConfigDict(populate_by_name=True)

    @computed_field
    @property
    def full_name(self) -> str:
        return f"{self.last_name} {self.first_name} {self.patronymic}".strip()


class ReportItemResponse(BaseModel):
    student: StudentInfo
    attendance_percent: float
    lectures_planned: int
    lectures_attended: int


class ReportPeriod(BaseModel):
    date_from: date
    date_to: date


class ReportResponse(BaseModel):
    term: str
    period: ReportPeriod
    matched_lectures_count: int
    matched_courses: list[str]
    items: list[ReportItemResponse]


@router.get("/healthcheck", tags=["Healthcheck"])
async def healthcheck() -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME, version=SERVICE_VERSION)


@router.post("/report", tags=["Лабораторная работа №1"])
async def report(request: Request, body: ReportRequest) -> ReportResponse:
    """Студенты с минимальным процентом посещения лекций по заданному термину."""
    data = await build_report(
        elastic=request.app.state.elastic,
        pg_pool=request.app.state.pg_pool,
        redis=request.app.state.redis,
        term=body.term,
        period_from=body.period_from,
        period_to=body.period_to,
        limit=body.limit,
    )
    return ReportResponse(
        term=data["term"],
        period=ReportPeriod(date_from=data["period_from"], date_to=data["period_to"]),
        matched_lectures_count=data["matched_lectures_count"],
        matched_courses=data["matched_courses"],
        items=[
            ReportItemResponse(
                student=StudentInfo.model_validate(item["student"]),
                attendance_percent=item["attendance_percent"],
                lectures_planned=item["lectures_planned"],
                lectures_attended=item["lectures_attended"],
            )
            for item in data["items"]
        ],
    )
