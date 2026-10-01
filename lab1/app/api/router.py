"""HTTP-контракт лабы №1: одна ручка отчёта и healthcheck."""

from fastapi import APIRouter, Request

from lab1.app.api.schemas import (
    HealthResponse,
    ReportItemResponse,
    ReportPeriod,
    ReportRequest,
    ReportResponse,
    StudentInfo,
)
from lab1.app.config import SERVICE_NAME, SERVICE_VERSION
from lab1.app.report import build_report

__all__ = ("router",)

router = APIRouter()


@router.get("/healthcheck", tags=["Healthcheck"])
async def healthcheck() -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME, version=SERVICE_VERSION)


@router.post("/report", tags=["Лабораторная работа №1"])
async def report(request: Request, body: ReportRequest) -> ReportResponse:
    """Студенты с минимальным процентом посещения лекций по заданному термину."""
    data = await build_report(
        elastic=request.app.state.elastic,
        neo4j_driver=request.app.state.neo4j,
        pg_pool=request.app.state.pg_pool,
        term=body.term,
        period_from=body.period_from,
        period_to=body.period_to,
        limit=body.limit,
    )
    return ReportResponse(
        term=data["term"],
        period=ReportPeriod(date_from=data["period_from"], date_to=data["period_to"]),
        matched_lectures_count=data["matched_lectures_count"],
        matched_courses=data["matched_courses"],
        items=[
            ReportItemResponse(
                student=StudentInfo.model_validate(item["student"]),
                attendance_percent=item["attendance_percent"],
                lectures_planned=item["lectures_planned"],
                lectures_attended=item["lectures_attended"],
            )
            for item in data["items"]
        ],
    )
