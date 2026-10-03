"""Точка входа lab2. Клиенты к трём хранилищам создаются в lifespan."""

from contextlib import asynccontextmanager

from elasticsearch import AsyncElasticsearch
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
from psycopg_pool import AsyncConnectionPool

from lab2.app.api.router import router
from lab2.app.config import SERVICE_VERSION, get_settings

__all__ = ("create_app",)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    pool = AsyncConnectionPool(settings.postgres_dsn, min_size=1, max_size=5, open=False)
    await pool.open()
    elastic = AsyncElasticsearch(settings.elastic_url)
    mongo_client = AsyncIOMotorClient(settings.mongo_url)
    app.state.pg_pool = pool
    app.state.elastic = elastic
    app.state.mongo_client = mongo_client
    app.state.mongo_db = mongo_client[settings.mongo_db]
    try:
        yield
    finally:
        mongo_client.close()
        await elastic.close()
        await pool.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Лабораторная работа №2",
        description="Объём аудитории по курсу семестра и требованиям к тех. средствам.",
        version=SERVICE_VERSION,
        lifespan=lifespan,
    )
    app.include_router(router)
    return app
