"""Настройки подключения к пяти хранилищам.

Значения по умолчанию указывают на порты, опубликованные на хост. Они разведены
со стандартными, потому что 5432 и 6379 на машине заняты другим проектом.
Внутри сети compose переменные окружения переопределят их на имена сервисов.
"""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ("Settings", "get_settings")

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # ---------- PostgreSQL ----------
    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_db: str = "university"
    postgres_user: str = "university"
    postgres_password: SecretStr = SecretStr("university")

    # ---------- Redis ----------
    redis_host: str = "localhost"
    redis_port: int = 6380
    redis_db: int = 0

    # ---------- MongoDB ----------
    mongo_host: str = "localhost"
    mongo_port: int = 27018
    mongo_db: str = "university"
    mongo_user: str = "university"
    mongo_password: SecretStr = SecretStr("university")

    # ---------- Neo4j ----------
    neo4j_host: str = "localhost"
    neo4j_bolt_port: int = 7688
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("university")

    # ---------- Elasticsearch ----------
    elastic_host: str = "localhost"
    elastic_port: int = 9201
    elastic_scheme: str = "http"

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
    def mongo_url(self) -> str:
        return (
            f"mongodb://{self.mongo_user}:"
            f"{self.mongo_password.get_secret_value()}@"
            f"{self.mongo_host}:{self.mongo_port}/"
        )

    @property
    def neo4j_url(self) -> str:
        return f"bolt://{self.neo4j_host}:{self.neo4j_bolt_port}"

    @property
    def elastic_url(self) -> str:
        return f"{self.elastic_scheme}://{self.elastic_host}:{self.elastic_port}"


def get_settings() -> Settings:
    return Settings()
