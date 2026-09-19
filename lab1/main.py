"""Точка входа lab1.

Пулы соединений к четырём хранилищам создаются в lifespan — один раз на
приложение — и складываются в app.state. Ручка в api/router.py читает
их оттуда напрямую через request.app.state.
"""

from contextlib import asynccontextmanager

from elasticsearch import AsyncElasticsearch
from fastapi import FastAPI
from neo4j import AsyncGraphDatabase
from psycopg_pool import AsyncConnectionPool
from redis.asyncio import Redis

from lab1.app.api.router import router
from lab1.app.config import SERVICE_VERSION, get_settings

__all__ = ("create_app",)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    pool = AsyncConnectionPool(settings.postgres_dsn, min_size=1, max_size=5, open=False)
    await pool.open()

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    elastic = AsyncElasticsearch(settings.elastic_url)
    neo4j_driver = AsyncGraphDatabase.driver(
        settings.neo4j_url,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
    )

    app.state.pg_pool = pool
    app.state.redis = redis
    app.state.elastic = elastic
    app.state.neo4j = neo4j_driver
    try:
        yield
    finally:
        await neo4j_driver.close()
        await elastic.close()
        await redis.aclose()
        await pool.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Лабораторная работа №1",
        description=(
            "Отчёт о студентах с минимальным процентом посещения лекций, "
            "содержащих заданный термин, за период обучения."
        ),
        version=SERVICE_VERSION,
        lifespan=lifespan,
    )
    app.include_router(router)
    return app
