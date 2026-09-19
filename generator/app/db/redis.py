"""Redis: карточки студентов с ключом в виде номера зачётной книжки.

Раскладка по task.md: «Для Redis – только список студентов с ключом в виде
номера зачетной книжки».

    student:{номер зачётки}    HASH   полная карточка студента
    student:id:{uuid}          STRING вторичный индекс: uuid -> номер зачётки
    students                   SET    список всех номеров зачёток

Вторичный индекс нужен вот зачем: аналитический запрос в PostgreSQL возвращает
student_id (UUID), а первичный ключ здесь — номер зачётки, как требует задание.
Без индекса пришлось бы join-ить таблицу student в PostgreSQL, и Redis стал бы
не нужен. С индексом лаба №1 получает из PostgreSQL только идентификаторы
и проценты, а карточки добирает отсюда за O(1).

Клиент синхронный: генератор — одноразовый скрипт, асинхронность ему ничего
не даёт. В lab-сервисах будет redis.asyncio.
"""

import redis

from generator.app.config import get_settings
from generator.app.models import Dataset

__all__ = ("connect", "load", "drop", "KEY_PREFIXES")

STUDENT_KEY = "student:{card}"
STUDENT_BY_ID_KEY = "student:id:{student_id}"
STUDENTS_SET = "students"

KEY_PREFIXES = ("student:*", STUDENTS_SET)


def connect(url: str | None = None) -> redis.Redis:
    """Клиент с decode_responses=True.

    Без этого флага Redis отдаёт bytes, и каждое чтение обрастает .decode().
    """
    return redis.Redis.from_url(url or get_settings().redis_url, decode_responses=True)


def load(client: redis.Redis, data: Dataset) -> None:
    """Заливает карточки студентов.

    Все команды идут одним pipeline: иначе на 137 студентов получилось бы
    ~400 отдельных round-trip до сервера. Pipeline отправляет их пакетом.
    """
    groups = {group.id: group for group in data.groups}
    specialties = {specialty.id: specialty for specialty in data.specialties}

    pipe = client.pipeline(transaction=False)

    for student in data.students:
        group = groups[student.group_id]
        specialty = specialties[group.specialty_id]

        key = STUDENT_KEY.format(card=student.student_card_number)
        # В HASH нельзя положить None — только str/int/float/bytes.
        pipe.hset(
            key,
            mapping={
                "id": str(student.id),
                "card_number": student.student_card_number,
                "last_name": student.last_name,
                "first_name": student.first_name,
                "patronymic": student.patronymic or "",
                "full_name": f"{student.last_name} {student.first_name} {student.patronymic}".strip(),
                "email": student.email,
                "phone": student.phone,
                "status": student.status,
                "enrollment_date": student.enrollment_date.isoformat(),
                "group_id": str(group.id),
                "group_name": group.name,
                "specialty_id": str(specialty.id),
                "specialty_name": specialty.name,
                "specialty_code": specialty.code,
            },
        )
        pipe.set(
            STUDENT_BY_ID_KEY.format(student_id=student.id),
            student.student_card_number,
        )
        pipe.sadd(STUDENTS_SET, student.student_card_number)

    pipe.execute()


def drop(client: redis.Redis) -> None:
    """Удаляет только наши ключи.

    Обход через scan_iter, а не KEYS: KEYS блокирует сервер на всё время
    перебора пространства ключей. На учебном объёме разницы не видно,
    на реальном это остановка сервиса.
    """
    pipe = client.pipeline(transaction=False)
    count = 0
    for key in client.scan_iter(match="student:*", count=500):
        pipe.delete(key)
        count += 1
    pipe.delete(STUDENTS_SET)
    pipe.execute()
