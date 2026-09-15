from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

__all__ = ("Role", "TokenResponse", "UserPublic", "HealthResponse")


class Role(StrEnum):
    """Роли пользователей API Gateway"""

    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


class TokenResponse(BaseModel):
    """Ответ на выдачу access-токена"""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class UserPublic(BaseModel):
    """Публичное представление пользователя"""

    username: str
    full_name: str
    roles: list[Role]


class HealthResponse(BaseModel):
    """Проверка доступности сервиса"""

    status: str
    service: str
    version: str
