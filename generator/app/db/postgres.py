"""Схема PostgreSQL: создание, удаление, партиционирование.

DDL живёт в Python, а не в .sql, чтобы границы недельных партиций считались
из тех же констант, что и даты расписания, — схема и данные не разъезжаются.
"""

from datetime import timedelta

import psycopg
from psycopg import sql

from generator.app.config import get_settings
from generator.app.data import ACADEMIC_WEEKS, ACADEMIC_YEAR_START
from generator.app.models import Dataset

__all__ = ("connect", "create_tables", "drop_tables", "load")


# Порядок важен: сначала те, на кого ссылаются.
DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS university (
        id UUID PRIMARY KEY,
        name VARCHAR(500) NOT NULL,
        short_name VARCHAR(100),
        address TEXT,
        website VARCHAR(255),
        founded_year INT,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS institute (
        id UUID PRIMARY KEY,
        university_id UUID REFERENCES university(id) ON DELETE CASCADE,
        name VARCHAR(500) NOT NULL,
        short_name VARCHAR(100),
        dean VARCHAR(300),
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS department (
        id UUID PRIMARY KEY,
        institute_id UUID REFERENCES institute(id) ON DELETE CASCADE,
        name VARCHAR(500) NOT NULL,
        short_name VARCHAR(100),
        head VARCHAR(300),
        room VARCHAR(50),
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS specialty (
        id UUID PRIMARY KEY,
        name VARCHAR(500) NOT NULL,
        code VARCHAR(20) NOT NULL,
        degree_level VARCHAR(20),
        duration_years INT,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS department_specialties (
        id UUID PRIMARY KEY,
        department_id UUID REFERENCES department(id) ON DELETE CASCADE,
        specialty_id UUID REFERENCES specialty(id) ON DELETE CASCADE,
        is_primary BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lecture_course (
        id UUID PRIMARY KEY,
        specialty_id UUID REFERENCES specialty(id) ON DELETE CASCADE,
        name VARCHAR(500) NOT NULL,
        description TEXT,
        semester INT CHECK (semester IN (1, 2)),
        total_hours INT,
        lecture_hours INT,
        practice_hours INT,
        lab_hours INT,
        -- Курс по выбору: на нём держатся лабы №2 и №3.
        is_elective BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lecture (
        id UUID PRIMARY KEY,
        course_id UUID REFERENCES lecture_course(id) ON DELETE CASCADE,
        title VARCHAR(500) NOT NULL,
        -- В annotation лаба №1 ищет заданный термин.
        annotation TEXT,
        lecture_type VARCHAR(50),
        -- Требования к техническим средствам — лаба №2.
        computer_type VARCHAR(100),
        -- Теги, среди них тег специальной дисциплины кафедры — лаба №3.
        tags TEXT[],
        order_number INT,
        duration_minutes INT DEFAULT 90,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lecture_material (
        id UUID PRIMARY KEY,
        lecture_id UUID REFERENCES lecture(id) ON DELETE CASCADE,
        content_type VARCHAR(50),
        title VARCHAR(500),
        content_text TEXT,
        file_url VARCHAR(1000),
        metadata JSONB,
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS student_group (
        id UUID PRIMARY KEY,
        specialty_id UUID REFERENCES specialty(id) ON DELETE CASCADE,
        name VARCHAR(50) NOT NULL,
        enrollment_year INT,
        curator VARCHAR(300),
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS student (
        id UUID PRIMARY KEY,
        group_id UUID REFERENCES student_group(id) ON DELETE CASCADE,
        first_name VARCHAR(100) NOT NULL,
        last_name VARCHAR(100) NOT NULL,
        patronymic VARCHAR(100),
        email VARCHAR(255),
        phone VARCHAR(20),
        student_card_number VARCHAR(20) UNIQUE,
        enrollment_date DATE,
        status VARCHAR(20) DEFAULT 'active',
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS student_course (
        id UUID PRIMARY KEY,
        student_id UUID REFERENCES student(id) ON DELETE CASCADE,
        course_id UUID REFERENCES lecture_course(id) ON DELETE CASCADE,
        is_elective BOOLEAN NOT NULL DEFAULT FALSE,
        enrolled_at DATE,
        UNIQUE (student_id, course_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS schedule (
        id UUID PRIMARY KEY,
        lecture_id UUID REFERENCES lecture(id) ON DELETE CASCADE,
        group_id UUID REFERENCES student_group(id) ON DELETE CASCADE,
        scheduled_date DATE NOT NULL,
        week_start_date DATE NOT NULL,
        start_time TIME,
        end_time TIME,
        classroom VARCHAR(50),
        teacher_name VARCHAR(300),
        status VARCHAR(20) DEFAULT 'scheduled',
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS attendance (
        id UUID NOT NULL,
        week_start_date DATE NOT NULL,
        schedule_id UUID NOT NULL REFERENCES schedule(id) ON DELETE CASCADE,
        student_id UUID NOT NULL REFERENCES student(id) ON DELETE CASCADE,
        is_present BOOLEAN NOT NULL DEFAULT TRUE,
        marked_at TIMESTAMP DEFAULT NOW(),
        note VARCHAR(500),
        -- Ключ партиционирования обязан входить в первичный ключ:
        -- глобальных индексов в PostgreSQL нет, каждый живёт внутри партиции.
        PRIMARY KEY (id, week_start_date),
        UNIQUE (schedule_id, student_id, week_start_date)
    ) PARTITION BY RANGE (week_start_date)
    """,
)

INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_attendance_student_week ON attendance (student_id, week_start_date)",
    "CREATE INDEX IF NOT EXISTS idx_attendance_schedule ON attendance (schedule_id)",
    "CREATE INDEX IF NOT EXISTS idx_schedule_lecture_week ON schedule (lecture_id, week_start_date)",
    "CREATE INDEX IF NOT EXISTS idx_schedule_group ON schedule (group_id)",
    "CREATE INDEX IF NOT EXISTS idx_schedule_date ON schedule (scheduled_date)",
    "CREATE INDEX IF NOT EXISTS idx_student_group ON student (group_id)",
    "CREATE INDEX IF NOT EXISTS idx_student_course_student ON student_course (student_id)",
    "CREATE INDEX IF NOT EXISTS idx_student_course_course ON student_course (course_id)",
    "CREATE INDEX IF NOT EXISTS idx_lecture_course ON lecture (course_id)",
    # По массиву тегов работает только GIN — btree тут бесполезен.
    "CREATE INDEX IF NOT EXISTS idx_lecture_tags ON lecture USING GIN (tags)",
    "CREATE INDEX IF NOT EXISTS idx_lecture_course_semester_spec ON lecture_course (semester, specialty_id)",
    "CREATE INDEX IF NOT EXISTS idx_student_group_specialty ON student_group (specialty_id)",
)

# Для удаления — в обратном порядке; CASCADE снимает зависимости,
# а DROP родителя attendance уносит все её партиции.
TABLES: tuple[str, ...] = (
    "attendance",
    "schedule",
    "student_course",
    "student",
    "student_group",
    "lecture_material",
    "lecture",
    "lecture_course",
    "department_specialties",
    "specialty",
    "department",
    "institute",
    "university",
)


def connect(dsn: str | None = None) -> psycopg.Connection:
    """Соединение с включённым autocommit: DDL не нуждается в транзакции."""
    conn = psycopg.connect(dsn or get_settings().postgres_dsn)
    conn.autocommit = True
    return conn


def create_tables(conn: psycopg.Connection) -> None:
    """Создаёт таблицы, недельные партиции и индексы."""
    for statement in DDL:
        conn.execute(statement)
    _create_attendance_partitions(conn)
    for statement in INDEXES:
        conn.execute(statement)


def drop_tables(conn: psycopg.Connection) -> None:
    """Удаляет схему целиком — операция «удалить хранилище» из практики №2."""
    conn.execute(
        sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
            sql.SQL(", ").join(sql.Identifier(name) for name in TABLES)
        )
    )


def _create_attendance_partitions(conn: psycopg.Connection) -> None:
    """Недельные партиции на весь учебный год.

    Имя берётся из ISO-календаря: неделя, начинающаяся 29.12.2025, по ISO 8601
    относится к 2026 году, поэтому нужен именно isocalendar(), а не .year.
    """
    week_start = ACADEMIC_YEAR_START
    for _ in range(ACADEMIC_WEEKS):
        week_end = week_start + timedelta(days=7)
        iso = week_start.isocalendar()
        name = f"attendance_{iso.year}w{iso.week:02d}"

        # В DDL параметры-заглушки (%s) не работают — PostgreSQL не принимает
        # их в утилитных командах. sql.Literal подставляет значение
        # с корректным экранированием на стороне клиента.
        conn.execute(
            sql.SQL(
                "CREATE TABLE IF NOT EXISTS {name} PARTITION OF attendance "
                "FOR VALUES FROM ({start}) TO ({end})"
            ).format(
                name=sql.Identifier(name),
                start=sql.Literal(week_start),
                end=sql.Literal(week_end),
            )
        )
        week_start = week_end


def load(conn: psycopg.Connection, data: Dataset) -> None:
    """Заливает датасет. Порядок обязан уважать внешние ключи."""
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO university (id, name, short_name, address, website, founded_year)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            [
                (u.id, u.name, u.short_name, u.address, u.website, u.founded_year)
                for u in data.universities
            ],
        )
        cur.executemany(
            "INSERT INTO institute (id, university_id, name, short_name, dean)"
            " VALUES (%s, %s, %s, %s, %s)",
            [(i.id, i.university_id, i.name, i.short_name, i.dean) for i in data.institutes],
        )
        cur.executemany(
            "INSERT INTO department (id, institute_id, name, short_name, head, room)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            [
                (d.id, d.institute_id, d.name, d.short_name, d.head, d.room)
                for d in data.departments
            ],
        )
        cur.executemany(
            "INSERT INTO specialty (id, name, code, degree_level, duration_years)"
            " VALUES (%s, %s, %s, %s, %s)",
            [
                (s.id, s.name, s.code, s.degree_level, s.duration_years)
                for s in data.specialties
            ],
        )
        cur.executemany(
            "INSERT INTO department_specialties (id, department_id, specialty_id, is_primary)"
            " VALUES (%s, %s, %s, %s)",
            [
                (ds.id, ds.department_id, ds.specialty_id, ds.is_primary)
                for ds in data.department_specialties
            ],
        )
        cur.executemany(
            "INSERT INTO lecture_course (id, specialty_id, name, description, semester,"
            " total_hours, lecture_hours, practice_hours, lab_hours, is_elective)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                (
                    c.id, c.specialty_id, c.name, c.description, c.semester,
                    c.total_hours, c.lecture_hours, c.practice_hours, c.lab_hours,
                    c.is_elective,
                )
                for c in data.courses
            ],
        )
        cur.executemany(
            "INSERT INTO lecture (id, course_id, title, annotation, lecture_type,"
            " computer_type, tags, order_number, duration_minutes)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                (
                    lec.id, lec.course_id, lec.title, lec.annotation, lec.lecture_type,
                    lec.computer_type, lec.tags, lec.order_number, lec.duration_minutes,
                )
                for lec in data.lectures
            ],
        )
        cur.executemany(
            "INSERT INTO student_group (id, specialty_id, name, enrollment_year, curator)"
            " VALUES (%s, %s, %s, %s, %s)",
            [
                (g.id, g.specialty_id, g.name, g.enrollment_year, g.curator)
                for g in data.groups
            ],
        )
        cur.executemany(
            "INSERT INTO student (id, group_id, first_name, last_name, patronymic, email,"
            " phone, student_card_number, enrollment_date, status)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                (
                    s.id, s.group_id, s.first_name, s.last_name, s.patronymic, s.email,
                    s.phone, s.student_card_number, s.enrollment_date, s.status,
                )
                for s in data.students
            ],
        )
        cur.executemany(
            "INSERT INTO student_course (id, student_id, course_id, is_elective, enrolled_at)"
            " VALUES (%s, %s, %s, %s, %s)",
            [
                (sc.id, sc.student_id, sc.course_id, sc.is_elective, sc.enrolled_at)
                for sc in data.student_courses
            ],
        )
        cur.executemany(
            "INSERT INTO schedule (id, lecture_id, group_id, scheduled_date, week_start_date,"
            " start_time, end_time, classroom, teacher_name, status)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                (
                    sch.id, sch.lecture_id, sch.group_id, sch.scheduled_date,
                    sch.week_start_date, sch.start_time, sch.end_time, sch.classroom,
                    sch.teacher_name, sch.status,
                )
                for sch in data.schedule
            ],
        )

        # Посещаемость — десятки тысяч строк, поэтому COPY, а не INSERT.
        # COPY в партиционированную таблицу поддерживается с PostgreSQL 11:
        # строки маршрутизируются по ключу так же, как при обычной вставке.
        with cur.copy(
            "COPY attendance (id, week_start_date, schedule_id, student_id, is_present, note)"
            " FROM STDIN"
        ) as copy:
            for row in data.attendance:
                copy.write_row(
                    (row.id, row.week_start_date, row.schedule_id, row.student_id,
                     row.is_present, row.note)
                )
