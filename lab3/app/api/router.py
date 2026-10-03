"""HTTP-контракт лабы №3: одна ручка отчёта и healthcheck."""

from fastapi import APIRouter, Request

from lab3.app.api.schemas import (
    CourseHours, GroupInfo, HealthResponse, ReportItemResponse,
    ReportRequest, ReportResponse, StudentInfo,
)
from lab3.app.config import SERVICE_NAME, SERVICE_VERSION
from lab3.app.report import build_report

__all__ = ("router",)

router = APIRouter()


@router.get("/healthcheck", tags=["Healthcheck"])
async def healthcheck() -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME, version=SERVICE_VERSION)


@router.post("/report", tags=["Лабораторная работа №3"])
async def report(request: Request, body: ReportRequest) -> ReportResponse:
    """Запланированные и прослушанные часы по спец. дисциплинам кафедры."""
    data = await build_report(
        neo4j_driver=request.app.state.neo4j,
        pg_pool=request.app.state.pg_pool,
        redis_client=request.app.state.redis,
        mongo_db=request.app.state.mongo_db,
        group_name=body.group_name,
    )
    return ReportResponse(
        group=GroupInfo.model_validate(data["group"]),
        special_discipline_tag=data["special_discipline_tag"],
        academic_hours_per_lesson=data["academic_hours_per_lesson"],
        items=[
            ReportItemResponse(
                student=StudentInfo.model_validate(item["student"]),
                courses=[CourseHours.model_validate(c) for c in item["courses"]],
                total_planned_hours=item["total_planned_hours"],
                total_attended_hours=item["total_attended_hours"],
                attendance_percent=item["attendance_percent"],
            )
            for item in data["items"]
        ],
    )
