"""Аутентификация: хранилище пользователей, пароли, выпуск JWT."""

from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from pydantic import BaseModel

from gateway.app.api.schemas import Role, UserPublic
from gateway.app.config import Settings, SettingsDep

__all__ = (
    "StoredUser",
    "USERS",
    "hash_password",
    "verify_password",
    "authenticate_user",
    "create_access_token",
    "decode_access_token",
    "get_current_user",
    "CurrentUser",
    "require_roles",
)

_password_hash = PasswordHash.recommended()


def verify_password(password: str, password_hash: str) -> bool:
    """Проверяет пароль против хеша"""
    try:
        return _password_hash.verify(password, password_hash)
    except Exception:
        return False


DUMMY_HASH = _password_hash.hash("dummy")


class StoredUser(BaseModel):
    """Пользователь, как он хранится на сервере. Содержит хеш пароля —
    наружу отдавать нельзя, для этого есть UserPublic."""
    username: str
    full_name: str
    password_hash: str
    roles: list[Role]

    def to_public(self) -> UserPublic:
        """Проекция наружу: всё, кроме хеша пароля."""
        return UserPublic(
            username=self.username,
            full_name=self.full_name,
            roles=self.roles,
        )


USERS: dict[str, StoredUser] = {
    "admin": StoredUser(
        username="admin",
        full_name="Администратор системы",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$mlqJvq+ia7oURQFqS1VIAg$39G8IxRkdoMmLHG398axC6xMXN4Bm/lMQr3SPPszzB4",
        roles=[Role.ADMIN, Role.USER],
    ),
    "analyst": StoredUser(
        username="analyst",
        full_name="Аналитик кафедры",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$0aGNGkYdYhHGYuf9Sx659A$o7tYWUC+q2lM+ctwce+WFwr3890S7+k6P1l6VC0lFNU",
        roles=[Role.USER],
    ),
}


def hash_password(password: str) -> str:
    """Хеширует пароль. Соль и параметры Argon2 лежат внутри строки хеша."""
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Проверяет пароль против хеша.

    Никогда не бросает исключений: битый или чужой формат хеша — это False,
    иначе в потоке логина получился бы 500 вместо 401.
    """
    try:
        return _password_hash.verify(password, password_hash)
    except Exception:
        return False


def authenticate_user(username: str, password: str) -> StoredUser | None:
    """Возвращает пользователя при верной паре логин/пароль, иначе None"""
    user = USERS.get(username)
    if user is None:
        verify_password(password, DUMMY_HASH)
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_access_token(user: StoredUser, settings: Settings) -> str:
    """Выпускает подписанный access-токен."""
    now = datetime.now(tz=UTC)
    payload = {
        "sub": user.username,
        "roles": [role.value for role in user.roles],
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_ttl_minutes),
        "jti": str(uuid4()),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str, settings: Settings) -> StoredUser | None:
    """Разбирает access-токен и возвращает пользователя, либо None.

    Подпись, срок действия, издатель и аудитория проверяются самой PyJWT —
    достаточно передать ей algorithms, issuer и audience. Любая проблема с
    токеном приходит исключением из семейства PyJWTError, поэтому наружу
    отдаём None и превращаем это в 401 уровнем выше.
    """
    try:
        payload = jwt.decode(
            token,
            key=settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError:
        return None

    return USERS.get(payload["sub"])


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    settings: SettingsDep,
) -> UserPublic:
    """Аутентификация: превращает Bearer-токен в пользователя."""
    user = decode_access_token(token, settings)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный или истёкший токен",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user.to_public()


CurrentUser = Annotated[UserPublic, Depends(get_current_user)]


def require_roles(
    *roles: Role,
) -> Callable[[UserPublic], Coroutine[Any, Any, UserPublic]]:
    """Авторизация: фабрика зависимостей, проверяющих роли.

    Возвращает 403, а не 401: пользователь опознан, но прав не хватает.
    Достаточно любой из перечисленных ролей.
    """
    required = frozenset(roles)

    async def dependency(user: CurrentUser) -> UserPublic:
        if required.isdisjoint(user.roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав для выполнения операции",
            )
        return user

    return dependency
