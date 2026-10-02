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
    LectureMaterial,
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
COURSES_PER_SPECIALTY = 5

# Состав курса по заданию: «лекционные курсы и практические занятия».
# Одно занятие — 2 академических часа, отсюда и часы курса.
LECTURES_PER_COURSE = 16
PRACTICES_PER_COURSE = 8
LABS_PER_COURSE = 4
LESSON_PLAN = (
    ("лекция", LECTURES_PER_COURSE),
    ("практика", PRACTICES_PER_COURSE),
    ("лабораторная", LABS_PER_COURSE),
)
ACADEMIC_HOURS_PER_LESSON = 2

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

# --- Материалы к занятиям ---
# Их content_text склеивается в поле индекса Elasticsearch, поэтому термин
# лабы №1 должен встречаться и здесь, а не только в аннотации.
MATERIALS_PER_LECTURE = (1, 3)
MATERIAL_TYPES = (
    ("конспект", "pdf"),
    ("презентация", "pptx"),
    ("видеозапись", "mp4"),
    ("исходный код", "zip"),
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


def _build_materials(
    lecture: Lecture, rnd: random.Random, fake: Faker
) -> list[LectureMaterial]:
    """1-3 материала на занятие.

    Текст материала — основной источник полнотекста для Elasticsearch:
    аннотация короткая, а задание требует искать термин в содержании
    занятия. Поэтому термин попадает и сюда, с той же вероятностью.
    """
    materials = []
    for index in range(rnd.randint(*MATERIALS_PER_LECTURE)):
        content_type, extension = rnd.choice(MATERIAL_TYPES)
        content_text = " ".join(fake.paragraph(nb_sentences=5) for _ in range(3))
        if rnd.random() < SEARCH_TERM_SHARE:
            content_text = f"В материале подробно разбираются {SEARCH_TERM}. {content_text}"

        material_id = uuid4()
        materials.append(
            LectureMaterial(
                id=material_id,
                lecture_id=lecture.id,
                content_type=content_type,
                title=f"{content_type.capitalize()}: {lecture.title}",
                content_text=content_text,
                file_url=f"https://files.university.local/{material_id}.{extension}",
                # JSONB: у разных типов материалов разный набор атрибутов —
                # ради этого колонка документная, а не набор полей.
                metadata={
                    "order": index + 1,
                    "size_kb": rnd.randint(200, 25_000),
                    "pages": rnd.randint(5, 60) if extension in ("pdf", "pptx") else None,
                    "duration_sec": rnd.randint(600, 5400) if extension == "mp4" else None,
                },
            )
        )
    return materials


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
        for index in range(COURSES_PER_SPECIALTY):
            # Признака спец. дисциплины в схеме нет: по заданию она
            # определяется тегом на лекции, поэтому флаг нужен только здесь,
            # чтобы решить, вешать тег или нет.
            is_special = rnd.random() < SPECIAL_DISCIPLINE_SHARE
            semester = 1 if index % 2 == 0 else 2
            lecture_hours = LECTURES_PER_COURSE * ACADEMIC_HOURS_PER_LESSON
            practice_hours = PRACTICES_PER_COURSE * ACADEMIC_HOURS_PER_LESSON
            lab_hours = LABS_PER_COURSE * ACADEMIC_HOURS_PER_LESSON

            course = Course(
                id=uuid4(),
                specialty_id=specialty.id,
                name=next(topic_iter),
                description=fake.paragraph(nb_sentences=4),
                semester=semester,
                total_hours=lecture_hours + practice_hours + lab_hours,
                lecture_hours=lecture_hours,
                practice_hours=practice_hours,
                lab_hours=lab_hours,
            )
            data.courses.append(course)

            course_tags = [rnd.choice(COMMON_TAGS)]
            if is_special:
                course_tags.append(SPECIAL_DISCIPLINE_TAG)

            order_number = 0
            for lesson_type, lessons_count in LESSON_PLAN:
                for number in range(lessons_count):
                    order_number += 1
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

                    lecture = Lecture(
                        id=uuid4(),
                        course_id=course.id,
                        title=LECTURE_TOPICS[number % len(LECTURE_TOPICS)],
                        annotation=annotation,
                        lecture_type=lesson_type,
                        computer_type=computer_type,
                        tags=list(course_tags),
                        order_number=order_number,
                        duration_minutes=90,
                    )
                    data.lectures.append(lecture)
                    data.lecture_materials.extend(_build_materials(lecture, rnd, fake))

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
                card_number = f"{group.enrollment_year}{card_counter:05d}"

                data.students.append(
                    Student(
                        id=uuid4(),
                        group_id=group.id,
                        first_name=first_name,
                        last_name=last_name,
                        patronymic=patronymic,
                        # Почта строится из номера зачётки, а не fake.email():
                        # на email теперь UNIQUE, а случайные адреса faker
                        # повторяются тем чаще, чем больше студентов.
                        email=f"{card_number}@edu.mirea.ru",
                        phone=fake.phone_number()[:20],
                        student_card_number=card_number,
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

        selected = set()
        for course in specialty_courses:
            data.student_courses.append(
                StudentCourse(
                    id=uuid4(),
                    student_id=student.id,
                    course_id=course.id,
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
            # Отметка ставится только записанным на курс.
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
                    # Отметку ставит тот, кто вёл занятие.
                    marked_by=item.teacher_name,
                    note=None if present else rnd.choice(("болезнь", "по заявлению", None)),
                )
            )

    return data
