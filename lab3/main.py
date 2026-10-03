"""Точка входа lab3. Клиенты к четырём хранилищам создаются в lifespan."""

from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
from neo4j import AsyncGraphDatabase
from psycopg_pool import AsyncConnectionPool

from lab3.app.api.router import router
from lab3.app.config import SERVICE_VERSION, get_settings

__all__ = ("create_app",)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    pool = AsyncConnectionPool(settings.postgres_dsn, min_size=1, max_size=5, open=False)
    await pool.open()
    neo4j_driver = AsyncGraphDatabase.driver(
        settings.neo4j_url,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
    )
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    mongo_client = AsyncIOMotorClient(settings.mongo_url)
    app.state.pg_pool = pool
    app.state.neo4j = neo4j_driver
    app.state.redis = redis_client
    app.state.mongo_client = mongo_client
    app.state.mongo_db = mongo_client[settings.mongo_db]
    try:
        yield
    finally:
        mongo_client.close()
        await redis_client.aclose()
        await neo4j_driver.close()
        await pool.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Лабораторная работа №3",
        description="Часы по спец. дисциплинам кафедры для студентов группы.",
        version=SERVICE_VERSION,
        lifespan=lifespan,
    )
    app.include_router(router)
    return app
