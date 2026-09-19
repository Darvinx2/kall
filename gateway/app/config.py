from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ("Settings", "get_settings", "SettingsDep", "SERVICE_NAME", "SERVICE_VERSION")

BASE_DIR = Path(__file__).resolve().parents[2]

SERVICE_NAME = "gateway"
SERVICE_VERSION = "0.1.0"


class Settings(BaseSettings):
    jwt_secret: SecretStr
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_minutes: int = 60
    jwt_issuer: str = "university-gateway"
    jwt_audience: str = "university-labs"

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        # .env общий на четыре сервиса, и каждому нужно своё подмножество.
        # С forbid (дефолт BaseSettings) gateway падал бы на настройках
        # баз данных, которые нужны генератору и лабам.
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Провайдер настроек для Depends: читает .env один раз на процесс."""
    return Settings()


SettingsDep = Annotated[Settings, Depends(get_settings)]
