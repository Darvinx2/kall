"""Контракт HTTP API лабы №2."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = (
    "HealthResponse", "ReportRequest", "CourseInfo", "LectureInfo",
    "ReportItemResponse", "ReportResponse",
)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class ReportRequest(BaseModel):
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


class CourseInfo(BaseModel):
    id: str
    name: str
    description: str
    semester: int
    total_hours: int
    lecture_hours: int
    practice_hours: int
    lab_hours: int
    specialty_name: str
    specialty_code: str


class LectureInfo(BaseModel):
    id: str
    title: str
    lecture_type: str
    order_number: int
    duration_minutes: int
    computer_type: str


class ReportItemResponse(BaseModel):
    course: CourseInfo
    lecture: LectureInfo
    listeners: int


class ReportResponse(BaseModel):
    technical_requirement: str
    semester: int
    enrollment_year: int
    required_capacity: int
    items: list[ReportItemResponse]
