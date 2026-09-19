from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from gateway.app.api.labs import router as labs_router
from gateway.app.api.router import router as health_router
from gateway.app.config import SERVICE_VERSION, get_settings

__all__ = ("create_app",)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # Один клиент на весь процесс: httpx сам держит пул соединений,
    # создавать его на каждый запрос — плодить лишние TCP-хендшейки.
    app.state.http_client = httpx.AsyncClient(timeout=settings.http_timeout_seconds)
    try:
        yield
    finally:
        await app.state.http_client.aclose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="UniversityMicroservices",
        version=SERVICE_VERSION,
        lifespan=lifespan,
    )
    app.include_router(health_router)
    app.include_router(labs_router)
    return app
