"""MongoDB: документы-композиции.

Раскладка по task.md: «Для MongoDB – документ с данными и составом группы».

    groups      документ группы со вложенным составом студентов и курсов
    courses     документ курса со вложенными лекциями
    university  иерархия вуза одним документом: институты, кафедры,
                специальности

Смысл именно в композиции: «полная информация о группе» (лаба №3) и «полная
информация о курсе» (лаба №2) читаются одним findOne, без сборки из пяти
таблиц. За это платим дублированием — те же данные лежат и в PostgreSQL.

Третья коллекция закрывает обратный вопрос — «что входит в вуз»: цепочка
university → institute → department → specialty это четыре JOIN в PostgreSQL
и один findOne здесь. Связь кафедра-специальность у нас M:N, поэтому
специальность вкладывается в каждую свою кафедру вместе с признаком
is_primary (выпускающая она или нет).

Идентификаторы хранятся строками, а не BSON-UUID. Причина практическая:
pymongo требует для UUID отдельной настройки uuidRepresentation, и значения
перестают совпадать побайтово с тем, что лежит в Redis и Elasticsearch.
Строка одинаково читается всеми пятью хранилищами.
"""

from pymongo import ASCENDING, MongoClient
from pymongo.database import Database

from generator.app.config import get_settings
from generator.app.models import Dataset

__all__ = ("connect", "load", "drop", "GROUPS", "COURSES", "UNIVERSITY")

GROUPS = "groups"
COURSES = "courses"
UNIVERSITY = "university"


def connect(url: str | None = None) -> MongoClient:
    settings = get_settings()
    return MongoClient(url or settings.mongo_url)


def database(client: MongoClient) -> Database:
    return client[get_settings().mongo_db]


def _hierarchy_docs(data: Dataset) -> list[dict]:
    """Вуз одним документом на каждый университет.

    Специальности берутся из department_specialties: одна и та же
    специальность может обслуживаться несколькими кафедрами, поэтому
    попадает в каждую из них.
    """
    specialties = {s.id: s for s in data.specialties}

    specialties_by_department: dict[str, list[dict]] = {}
    for link in data.department_specialties:
        specialty = specialties[link.specialty_id]
        specialties_by_department.setdefault(str(link.department_id), []).append(
            {
                "id": str(specialty.id),
                "name": specialty.name,
                "code": specialty.code,
                "degree_level": specialty.degree_level,
                "duration_years": specialty.duration_years,
                "is_primary": link.is_primary,
            }
        )

    departments_by_institute: dict[str, list[dict]] = {}
    for department in data.departments:
        departments_by_institute.setdefault(str(department.institute_id), []).append(
            {
                "id": str(department.id),
                "name": department.name,
                "short_name": department.short_name,
                "head": department.head,
                "room": department.room,
                "specialties": specialties_by_department.get(str(department.id), []),
            }
        )

    institutes_by_university: dict[str, list[dict]] = {}
    for institute in data.institutes:
        institutes_by_university.setdefault(str(institute.university_id), []).append(
            {
                "id": str(institute.id),
                "name": institute.name,
                "short_name": institute.short_name,
                "dean": institute.dean,
                "departments": departments_by_institute.get(str(institute.id), []),
            }
        )

    return [
        {
            "_id": str(university.id),
            "name": university.name,
            "short_name": university.short_name,
            "address": university.address,
            "website": university.website,
            "founded_year": university.founded_year,
            "institutes": institutes_by_university.get(str(university.id), []),
        }
        for university in data.universities
    ]


def load(client: MongoClient, data: Dataset) -> None:
    db = database(client)

    specialties = {s.id: s for s in data.specialties}

    students_by_group: dict[str, list[dict]] = {}
    for student in data.students:
        students_by_group.setdefault(str(student.group_id), []).append(
            {
                "id": str(student.id),
                "card_number": student.student_card_number,
                "last_name": student.last_name,
                "first_name": student.first_name,
                "patronymic": student.patronymic,
                "full_name": f"{student.last_name} {student.first_name} {student.patronymic}".strip(),
                "email": student.email,
                "phone": student.phone,
                "status": student.status,
                "enrollment_date": student.enrollment_date.isoformat(),
            }
        )

    courses_by_specialty: dict[str, list[dict]] = {}
    for course in data.courses:
        courses_by_specialty.setdefault(str(course.specialty_id), []).append(
            {
                "id": str(course.id),
                "name": course.name,
                "semester": course.semester,
                "lecture_hours": course.lecture_hours,
            }
        )

    lectures_by_course: dict[str, list[dict]] = {}
    for lecture in sorted(data.lectures, key=lambda x: x.order_number):
        lectures_by_course.setdefault(str(lecture.course_id), []).append(
            {
                "id": str(lecture.id),
                "title": lecture.title,
                "order_number": lecture.order_number,
                "computer_type": lecture.computer_type,
                "tags": lecture.tags,
                "duration_minutes": lecture.duration_minutes,
            }
        )

    def specialty_doc(specialty_id) -> dict:
        specialty = specialties[specialty_id]
        return {
            "id": str(specialty.id),
            "name": specialty.name,
            "code": specialty.code,
            "degree_level": specialty.degree_level,
            "duration_years": specialty.duration_years,
        }

    group_docs = [
        {
            "_id": str(group.id),
            "name": group.name,
            "enrollment_year": group.enrollment_year,
            "curator": group.curator,
            "specialty": specialty_doc(group.specialty_id),
            "students": students_by_group.get(str(group.id), []),
            "students_count": len(students_by_group.get(str(group.id), [])),
            "courses": courses_by_specialty.get(str(group.specialty_id), []),
        }
        for group in data.groups
    ]

    course_docs = [
        {
            "_id": str(course.id),
            "name": course.name,
            "description": course.description,
            "semester": course.semester,
            "hours": {
                "total": course.total_hours,
                "lecture": course.lecture_hours,
                "practice": course.practice_hours,
                "lab": course.lab_hours,
            },
            "specialty": specialty_doc(course.specialty_id),
            "lectures": lectures_by_course.get(str(course.id), []),
            "lectures_count": len(lectures_by_course.get(str(course.id), [])),
        }
        for course in data.courses
    ]

    db[GROUPS].insert_many(group_docs)
    db[COURSES].insert_many(course_docs)
    db[UNIVERSITY].insert_many(_hierarchy_docs(data))

    # Индексы под запросы лаб: по имени группы (лаба №3),
    # по семестру и признаку спец-дисциплины (лабы №2 и №3).
    db[GROUPS].create_index([("name", ASCENDING)], unique=True)
    db[GROUPS].create_index([("specialty.code", ASCENDING)])
    db[GROUPS].create_index([("students.card_number", ASCENDING)])
    db[COURSES].create_index([("semester", ASCENDING)])
    db[COURSES].create_index([("specialty.code", ASCENDING)])
    # Поиск по вложенным уровням: Mongo индексирует путь внутрь массивов.
    db[UNIVERSITY].create_index([("institutes.departments.short_name", ASCENDING)])
    db[UNIVERSITY].create_index([("institutes.departments.specialties.code", ASCENDING)])


def drop(client: MongoClient) -> None:
    """Удаляет коллекции целиком — вместе с индексами и документами."""
    db = database(client)
    for name in (GROUPS, COURSES, UNIVERSITY):
        db.drop_collection(name)
