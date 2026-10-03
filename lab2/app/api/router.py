"""HTTP-контракт лабы №2: одна ручка отчёта и healthcheck."""

from fastapi import APIRouter, Request

from lab2.app.api.schemas import (
    CourseInfo, HealthResponse, LectureInfo, ReportItemResponse,
    ReportRequest, ReportResponse,
)
from lab2.app.config import SERVICE_NAME, SERVICE_VERSION
from lab2.app.report import build_report

__all__ = ("router",)

router = APIRouter()


@router.get("/healthcheck", tags=["Healthcheck"])
async def healthcheck() -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME, version=SERVICE_VERSION)


@router.post("/report", tags=["Лабораторная работа №2"])
async def report(request: Request, body: ReportRequest) -> ReportResponse:
    """Объём аудитории для занятий с заданными требованиями к тех. средствам."""
    data = await build_report(
        elastic=request.app.state.elastic,
        pg_pool=request.app.state.pg_pool,
        mongo_db=request.app.state.mongo_db,
        technical_requirement=body.technical_requirement,
        semester=body.semester,
        enrollment_year=body.enrollment_year,
        limit=body.limit,
    )
    return ReportResponse(
        technical_requirement=data["technical_requirement"],
        semester=data["semester"],
        enrollment_year=data["enrollment_year"],
        required_capacity=data["required_capacity"],
        items=[
            ReportItemResponse(
                course=CourseInfo.model_validate(item["course"]),
                lecture=LectureInfo.model_validate(item["lecture"]),
                listeners=item["listeners"],
            )
            for item in data["items"]
        ],
    )
