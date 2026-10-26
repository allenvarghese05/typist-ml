"""GET /health: liveness, database check, and worker heartbeat age (design doc section 14; T2.5)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import Engine

from typist.config import Settings
from typist.db import check_database, get_engine
from typist.schemas.health import HealthResponse
from typist.worker import read_heartbeat_age_s

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
)
def get_health(
    request: Request,
    engine: Annotated[Engine, Depends(get_engine)],
    response: Response,
) -> HealthResponse:
    """200 {"status": "ok", "db": "ok", "worker_heartbeat_age_s": ...} if SELECT 1 runs, else 503."""
    if check_database(engine):
        settings: Settings = request.app.state.settings
        heartbeat_age = read_heartbeat_age_s(settings.db_path)
        return HealthResponse(
            status="ok",
            db="ok",
            worker_heartbeat_age_s=heartbeat_age,
        )
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="error", db="error", worker_heartbeat_age_s=None)
