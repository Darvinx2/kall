"""Контракт HTTP API лабы №1: модели запроса и ответа."""

from datetime import date
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

__all__ = (
    "HealthResponse",
    "ReportRequest",
    "StudentInfo",
    "ReportItemResponse",
    "ReportPeriod",
    "ReportResponse",
)


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
    matched_courses: list[str]
    items: list[ReportItemResponse]
