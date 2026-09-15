from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from gateway.app.api.auth import (
    USERS,
    CurrentUser,
    authenticate_user,
    create_access_token,
    require_roles,
)
from gateway.app.api.schemas import HealthResponse, Role, TokenResponse, UserPublic
from gateway.app.config import SERVICE_NAME, SERVICE_VERSION, SettingsDep

__all__ = ("router",)

router = APIRouter()

LoginForm = Annotated[OAuth2PasswordRequestForm, Depends()]
AdminOnly = Annotated[UserPublic, Depends(require_roles(Role.ADMIN))]


@router.get("/healthcheck", tags=["Healthcheck"])
async def healthcheck() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=SERVICE_NAME,
        version=SERVICE_VERSION,
    )


@router.post("/auth/login", tags=["Auth"])
def login(form_data: LoginForm, settings: SettingsDep) -> TokenResponse:
    """Выдаёт access-токен по паре логин/пароль.

    Объявлена как `def`, а не `async def`: проверка пароля Argon2 занимает
    ~40 мс чистого процессорного времени и заблокировала бы событийный цикл.
    FastAPI выполняет синхронные обработчики в пуле потоков.
    """
    user = authenticate_user(form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenResponse(
        access_token=create_access_token(user, settings),
        expires_in=settings.jwt_access_ttl_minutes * 60,
    )


@router.get("/auth/me", tags=["Auth"])
async def read_me(user: CurrentUser) -> UserPublic:
    """Текущий пользователь. Требует только валидного токена."""
    return user
