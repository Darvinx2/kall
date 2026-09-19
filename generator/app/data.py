"""Генерация датасета в памяти.

Один датасет — источник для всех пяти хранилищ. Идентификаторы присваиваются
здесь, в Python, поэтому одна и та же лекция имеет один и тот же UUID
в PostgreSQL, Redis, MongoDB, Neo4j и Elasticsearch.

Генерация детерминирована: при одном и том же SEED данные повторяются, иначе
отчёт о тестировании разъедется с тем, что покажет система.
"""

import random
from datetime import date, time, timedelta
from uuid import UUID, uuid4

from faker import Faker

from generator.app.models import (
    Attendance,
    Course,
    Dataset,
    Department,
    DepartmentSpecialty,
    Group,
    Institute,
    Lecture,
    Schedule,
    Specialty,
    Student,
    StudentCourse,
    University,
)

__all__ = (
    "ACADEMIC_WEEKS",
    "ACADEMIC_YEAR_START",
    "SEARCH_TERM",
    "SPECIAL_DISCIPLINE_TAG",
    "generate",
)

# ======================== НАСТРОЙКИ ГЕНЕРАЦИИ ========================

SEED = 20260915

# Учебный год: 1 сентября 2025 — понедельник.
ACADEMIC_YEAR_START = date(2025, 9, 1)
ACADEMIC_WEEKS = 44

# Семестр — 18 недель; между ними зимние каникулы.
SEMESTER_WEEKS = {1: range(0, 18), 2: range(22, 40)}

# Объёмы
DEPARTMENTS = 2
SPECIALTIES = 3
GROUPS_PER_SPECIALTY = 2
STUDENTS_PER_GROUP = (20, 25)
MANDATORY_COURSES_PER_SPECIALTY = 3
ELECTIVE_COURSES_PER_SPECIALTY = 2
LECTURES_PER_COURSE = 16
ELECTIVES_CHOSEN_BY_STUDENT = (1, 2)

# --- Лаба №1: термин, который ищут в аннотациях лекций ---
SEARCH_TERM = "нейронные сети"
SEARCH_TERM_SHARE = 1 / 6

# --- Лаба №2: требования к техническим средствам ---
COMPUTER_TYPES = (
    "проектор",
    "интерактивная доска",
    "компьютерный класс",
    "без оборудования",
)

# --- Лаба №3: тег специальной дисциплины кафедры ---
SPECIAL_DISCIPLINE_TAG = "специальная дисциплина кафедры"
SPECIAL_DISCIPLINE_SHARE = 0.4
COMMON_TAGS = ("базовый курс", "практикум", "теория", "проектная работа")

# --- Посещаемость ---
# У каждого студента своя дисциплинированность. Без разброса топ-10
# по минимальному проценту посещения не имел бы смысла.
DILIGENCE_NORMAL = (0.78, 0.97)
DILIGENCE_POOR = (0.25, 0.55)
POOR_STUDENTS_SHARE = 0.15

# Расписание
TIME_SLOTS = (
    (time(9, 0), time(10, 30)),
    (time(10, 40), time(12, 10)),
    (time(12, 40), time(14, 10)),
    (time(14, 20), time(15, 50)),
)
CLASSROOMS = ("А-201", "А-305", "Б-114", "Б-402", "В-121", "В-233")

# Третий элемент — аббревиатура для имён групп. Первый сегмент кода
# для этого не годится: у 09.03.04 и 09.03.03 он одинаковый, и группы
# получали бы совпадающие имена.
SPECIALTY_NAMES = (
    ("Программная инженерия", "09.03.04", "ПИ"),
    ("Прикладная информатика", "09.03.03", "ПИН"),
    ("Информационная безопасность", "10.03.01", "ИБ"),
)

COURSE_TOPICS = (
    "Базы данных",
    "Проектирование архитектуры ПО",
    "Машинное обучение",
    "Распределённые системы",
    "Алгоритмы и структуры данных",
    "Компьютерные сети",
    "Методы оптимизации",
    "Защита информации",
    "Облачные вычисления",
    "Анализ больших данных",
)

LECTURE_TOPICS = (
    "Введение в предмет",
    "Модели и абстракции",
    "Реляционная алгебра",
    "Индексы и планы запросов",
    "Транзакции и изоляция",
    "Партиционирование и шардирование",
    "Кэширование",
    "Очереди сообщений",
    "Графовые модели данных",
    "Полнотекстовый поиск",
    "Метрики и наблюдаемость",
    "Отказоустойчивость",
    "Нагрузочное тестирование",
    "Безопасность данных",
    "Миграции и версионирование",
    "Итоговый обзор курса",
)


# =========================== ГЕНЕРАЦИЯ ===========================


def generate(seed: int = SEED) -> Dataset:
    rnd = random.Random(seed)
    fake = Faker("ru_RU")
    Faker.seed(seed)

    data = Dataset()

    # --- Университет, институт, кафедры ---
    university = University(
        id=uuid4(),
        name="Российский технологический университет",
        short_name="РТУ",
        address=fake.address().replace("\n", ", "),
        website="https://example.edu",
        founded_year=1947,
    )
    data.universities.append(university)

    institute = Institute(
        id=uuid4(),
        university_id=university.id,
        name="Институт информационных технологий",
        short_name="ИИТ",
        dean=fake.name(),
    )
    data.institutes.append(institute)

    for i in range(DEPARTMENTS):
        data.departments.append(
            Department(
                id=uuid4(),
                institute_id=institute.id,
                name=f"Кафедра {'программной инженерии' if i == 0 else 'систем обработки данных'}",
                short_name=f"К{i + 1}",
                head=fake.name(),
                room=rnd.choice(CLASSROOMS),
            )
        )

    # --- Специальности ---
    for name, code, _abbr in SPECIALTY_NAMES[:SPECIALTIES]:
        specialty = Specialty(
            id=uuid4(),
            name=name,
            code=code,
            degree_level="бакалавриат",
            duration_years=4,
        )
        data.specialties.append(specialty)
        # Основная кафедра плюс вторая как вспомогательная — связь M:N.
        for index, department in enumerate(data.departments):
            data.department_specialties.append(
                DepartmentSpecialty(
                    id=uuid4(),
                    department_id=department.id,
                    specialty_id=specialty.id,
                    is_primary=index == 0,
                )
            )

    # --- Курсы и лекции ---
    topics = list(COURSE_TOPICS)
    rnd.shuffle(topics)
    topic_iter = iter(topics * 3)

    for specialty in data.specialties:
        total = MANDATORY_COURSES_PER_SPECIALTY + ELECTIVE_COURSES_PER_SPECIALTY
        for index in range(total):
            is_elective = index >= MANDATORY_COURSES_PER_SPECIALTY
            is_special = rnd.random() < SPECIAL_DISCIPLINE_SHARE
            semester = 1 if index % 2 == 0 else 2
            lecture_hours = LECTURES_PER_COURSE * 2

            course = Course(
                id=uuid4(),
                specialty_id=specialty.id,
                name=next(topic_iter),
                description=fake.paragraph(nb_sentences=4),
                semester=semester,
                total_hours=lecture_hours + 32 + 16,
                lecture_hours=lecture_hours,
                practice_hours=32,
                lab_hours=16,
                is_elective=is_elective,
                is_special_discipline=is_special,
            )
            data.courses.append(course)

            course_tags = [rnd.choice(COMMON_TAGS)]
            if is_special:
                course_tags.append(SPECIAL_DISCIPLINE_TAG)

            for number in range(LECTURES_PER_COURSE):
                computer_type = rnd.choice(COMPUTER_TYPES)

                annotation = fake.paragraph(nb_sentences=3)
                if rnd.random() < SEARCH_TERM_SHARE:
                    # Термин вставляется явно — лаба №1 обязана его найти.
                    annotation = (
                        f"Рассматриваются {SEARCH_TERM} и их применение "
                        f"в прикладных задачах. {annotation}"
                    )
                if computer_type != "без оборудования":
                    # Требование к тех. средствам дублируется в текст:
                    # лаба №2 ищет его полнотекстовым запросом.
                    annotation = f"{annotation} Для проведения требуется {computer_type}."

                data.lectures.append(
                    Lecture(
                        id=uuid4(),
                        course_id=course.id,
                        title=LECTURE_TOPICS[number % len(LECTURE_TOPICS)],
                        annotation=annotation,
                        lecture_type="лекция",
                        computer_type=computer_type,
                        tags=list(course_tags),
                        order_number=number + 1,
                        duration_minutes=90,
                    )
                )

    # --- Группы и студенты ---
    abbr_by_code = {code: abbr for _name, code, abbr in SPECIALTY_NAMES}
    card_counter = 0
    for specialty in data.specialties:
        prefix = abbr_by_code[specialty.code]
        for index in range(GROUPS_PER_SPECIALTY):
            group = Group(
                id=uuid4(),
                specialty_id=specialty.id,
                name=f"{prefix}-{21 + index}",
                enrollment_year=2021 + index,
                curator=fake.name(),
            )
            data.groups.append(group)

            for _ in range(rnd.randint(*STUDENTS_PER_GROUP)):
                poor = rnd.random() < POOR_STUDENTS_SHARE
                low, high = DILIGENCE_POOR if poor else DILIGENCE_NORMAL

                # Пол выбирается один раз, ФИО берётся согласованно: иначе
                # Faker выдаёт «Гущин Роман Матвеевна», а отчёт лабы №1
                # показывает полное имя студента.
                if rnd.random() < 0.5:
                    last_name, first_name, patronymic = (
                        fake.last_name_male(),
                        fake.first_name_male(),
                        fake.middle_name_male(),
                    )
                else:
                    last_name, first_name, patronymic = (
                        fake.last_name_female(),
                        fake.first_name_female(),
                        fake.middle_name_female(),
                    )

                # Номер зачётки — сквозная нумерация, а не случайное число:
                # в PostgreSQL на этом поле UNIQUE, и случайные номера
                # сталкивались бы примерно в каждом четвёртом прогоне.
                card_counter += 1

                data.students.append(
                    Student(
                        id=uuid4(),
                        group_id=group.id,
                        first_name=first_name,
                        last_name=last_name,
                        patronymic=patronymic,
                        email=fake.email(),
                        phone=fake.phone_number()[:20],
                        student_card_number=f"{group.enrollment_year}{card_counter:05d}",
                        enrollment_date=date(group.enrollment_year, 9, 1),
                        status="active",
                        diligence=rnd.uniform(low, high),
                    )
                )

    # --- Запись на курсы ---
    courses_by_specialty: dict[UUID, list[Course]] = {}
    for course in data.courses:
        courses_by_specialty.setdefault(course.specialty_id, []).append(course)

    group_by_id = {group.id: group for group in data.groups}
    student_course_ids: dict[UUID, set[UUID]] = {}

    for student in data.students:
        specialty_id = group_by_id[student.group_id].specialty_id
        specialty_courses = courses_by_specialty[specialty_id]

        mandatory = [course for course in specialty_courses if not course.is_elective]
        electives = [course for course in specialty_courses if course.is_elective]
        chosen = rnd.sample(
            electives,
            k=min(rnd.randint(*ELECTIVES_CHOSEN_BY_STUDENT), len(electives)),
        )

        selected = set()
        for course in (*mandatory, *chosen):
            data.student_courses.append(
                StudentCourse(
                    id=uuid4(),
                    student_id=student.id,
                    course_id=course.id,
                    is_elective=course.is_elective,
                    enrolled_at=date(student.enrollment_date.year, 9, 1),
                )
            )
            selected.add(course.id)
        student_course_ids[student.id] = selected

    # --- Расписание ---
    lectures_by_course: dict[UUID, list[Lecture]] = {}
    for lecture in data.lectures:
        lectures_by_course.setdefault(lecture.course_id, []).append(lecture)

    for group in data.groups:
        for course in courses_by_specialty[group.specialty_id]:
            weeks = list(SEMESTER_WEEKS[course.semester])
            for lecture in lectures_by_course[course.id]:
                week_index = weeks[(lecture.order_number - 1) % len(weeks)]
                week_start = ACADEMIC_YEAR_START + timedelta(weeks=week_index)
                weekday = rnd.randint(0, 4)
                start, end = rnd.choice(TIME_SLOTS)
                data.schedule.append(
                    Schedule(
                        id=uuid4(),
                        lecture_id=lecture.id,
                        group_id=group.id,
                        scheduled_date=week_start + timedelta(days=weekday),
                        week_start_date=week_start,
                        start_time=start,
                        end_time=end,
                        classroom=rnd.choice(CLASSROOMS),
                        teacher_name=fake.name(),
                        status="held",
                    )
                )

    # --- Посещаемость ---
    students_by_group: dict[UUID, list[Student]] = {}
    for student in data.students:
        students_by_group.setdefault(student.group_id, []).append(student)

    lecture_by_id = {lecture.id: lecture for lecture in data.lectures}

    for item in data.schedule:
        course_id = lecture_by_id[item.lecture_id].course_id
        for student in students_by_group[item.group_id]:
            # Отметка ставится только тем, кто записан на курс: выборные
            # слушают не все, и именно это делает лабы №2 и №3 осмысленными.
            if course_id not in student_course_ids[student.id]:
                continue
            present = rnd.random() < student.diligence
            data.attendance.append(
                Attendance(
                    id=uuid4(),
                    week_start_date=item.week_start_date,
                    schedule_id=item.id,
                    student_id=student.id,
                    is_present=present,
                    note=None if present else rnd.choice(("болезнь", "по заявлению", None)),
                )
            )

    return data
