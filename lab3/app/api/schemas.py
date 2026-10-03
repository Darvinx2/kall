"""Контракт HTTP API лабы №3."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

__all__ = (
    "HealthResponse", "ReportRequest", "GroupInfo", "StudentInfo",
    "CourseHours", "ReportItemResponse", "ReportResponse",
)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_name: Annotated[str, Field(min_length=2, max_length=50)]

    @field_validator("group_name")
    @classmethod
    def strip_group(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("название группы не может состоять из одних пробелов")
        return stripped


class GroupInfo(BaseModel):
    name: str
    enrollment_year: int
    curator: str
    students_count: int
    specialty_name: str
    specialty_code: str


class StudentInfo(BaseModel):
    card_number: str
    last_name: str
    first_name: str
    patronymic: str
    email: str
    phone: str
    status: str
    enrollment_date: str

    @computed_field
    @property
    def full_name(self) -> str:
        return f"{self.last_name} {self.first_name} {self.patronymic}".strip()


class CourseHours(BaseModel):
    id: str
    name: str
    semester: int
    course_lecture_hours: int
    planned_hours: int
    attended_hours: int


class ReportItemResponse(BaseModel):
    student: StudentInfo
    courses: list[CourseHours]
    total_planned_hours: int
    total_attended_hours: int
    attendance_percent: float


class ReportResponse(BaseModel):
    group: GroupInfo
    special_discipline_tag: str
    academic_hours_per_lesson: int
    items: list[ReportItemResponse]
