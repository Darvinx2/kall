"""Форма датасета: сущности предметной области и их контейнер.

Модели без логики — только структура. Все пять адаптеров хранилищ
(app/db/*.py) импортируют отсюда Dataset и ничего больше, поэтому форма
данных отделена от того, как она заполняется (это в data.py).
"""

from dataclasses import dataclass, field
from datetime import date, time
from uuid import UUID

__all__ = (
    "University",
    "Institute",
    "Department",
    "Specialty",
    "DepartmentSpecialty",
    "Course",
    "Lecture",
    "LectureMaterial",
    "Group",
    "Student",
    "StudentCourse",
    "Schedule",
    "Attendance",
    "Dataset",
)


@dataclass(slots=True)
class University:
    id: UUID
    name: str
    short_name: str
    address: str
    website: str
    founded_year: int


@dataclass(slots=True)
class Institute:
    id: UUID
    university_id: UUID
    name: str
    short_name: str
    dean: str


@dataclass(slots=True)
class Department:
    id: UUID
    institute_id: UUID
    name: str
    short_name: str
    head: str
    room: str


@dataclass(slots=True)
class Specialty:
    id: UUID
    name: str
    code: str
    degree_level: str
    duration_years: int


@dataclass(slots=True)
class DepartmentSpecialty:
    id: UUID
    department_id: UUID
    specialty_id: UUID
    is_primary: bool


@dataclass(slots=True)
class Course:
    id: UUID
    specialty_id: UUID
    name: str
    description: str
    semester: int
    total_hours: int
    lecture_hours: int
    practice_hours: int
    lab_hours: int


@dataclass(slots=True)
class Lecture:
    id: UUID
    course_id: UUID
    title: str
    annotation: str
    lecture_type: str
    computer_type: str
    tags: list[str]
    order_number: int
    duration_minutes: int


@dataclass(slots=True)
class LectureMaterial:
    id: UUID
    lecture_id: UUID
    content_type: str
    title: str
    content_text: str
    file_url: str
    metadata: dict


@dataclass(slots=True)
class Group:
    id: UUID
    specialty_id: UUID
    name: str
    enrollment_year: int
    curator: str


@dataclass(slots=True)
class Student:
    id: UUID
    group_id: UUID
    first_name: str
    last_name: str
    patronymic: str
    email: str
    phone: str
    student_card_number: str
    enrollment_date: date
    status: str
    diligence: float  # служебное поле, в БД не пишется


@dataclass(slots=True)
class StudentCourse:
    id: UUID
    student_id: UUID
    course_id: UUID
    enrolled_at: date


@dataclass(slots=True)
class Schedule:
    id: UUID
    lecture_id: UUID
    group_id: UUID
    scheduled_date: date
    week_start_date: date
    start_time: time
    end_time: time
    classroom: str
    teacher_name: str
    status: str


@dataclass(slots=True)
class Attendance:
    id: UUID
    week_start_date: date
    schedule_id: UUID
    student_id: UUID
    is_present: bool
    marked_by: str
    note: str | None


@dataclass(slots=True)
class Dataset:
    universities: list[University] = field(default_factory=list)
    institutes: list[Institute] = field(default_factory=list)
    departments: list[Department] = field(default_factory=list)
    specialties: list[Specialty] = field(default_factory=list)
    department_specialties: list[DepartmentSpecialty] = field(default_factory=list)
    courses: list[Course] = field(default_factory=list)
    lectures: list[Lecture] = field(default_factory=list)
    lecture_materials: list[LectureMaterial] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)
    students: list[Student] = field(default_factory=list)
    student_courses: list[StudentCourse] = field(default_factory=list)
    schedule: list[Schedule] = field(default_factory=list)
    attendance: list[Attendance] = field(default_factory=list)
