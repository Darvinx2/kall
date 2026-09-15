from fastapi import FastAPI

from gateway.app.api.router import router as health_router
from gateway.app.config import SERVICE_VERSION

__all__ = ("create_app",)


def create_app() -> FastAPI:
    app = FastAPI(
        title="UniversityMicroservices",
        version=SERVICE_VERSION,
    )
    app.include_router(health_router)
    return app
