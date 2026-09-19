"""Настройки подключения к четырём хранилищам, которые использует лаба №1.

JWT здесь нет: токен проверяет только gateway. Лаба недоступна снаружи сети
compose (порт наружу не публикуется), поэтому повторная проверка не нужна —
единственный, кто вообще может сюда достучаться, это сам gateway.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ("Settings", "get_settings", "SERVICE_NAME", "SERVICE_VERSION")

BASE_DIR = Path(__file__).resolve().parents[2]

SERVICE_NAME = "lab1"
SERVICE_VERSION = "0.1.0"


class Settings(BaseSettings):
    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_db: str = "university"
    postgres_user: str = "university"
    postgres_password: SecretStr = SecretStr("university")

    redis_host: str = "localhost"
    redis_port: int = 6380
    redis_db: int = 0

    elastic_host: str = "localhost"
    elastic_port: int = 9201
    elastic_scheme: str = "http"

    neo4j_host: str = "localhost"
    neo4j_bolt_port: int = 7688
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("university")

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:"
            f"{self.postgres_password.get_secret_value()}@"
            f"{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def elastic_url(self) -> str:
        return f"{self.elastic_scheme}://{self.elastic_host}:{self.elastic_port}"

    @property
    def neo4j_url(self) -> str:
        return f"bolt://{self.neo4j_host}:{self.neo4j_bolt_port}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
