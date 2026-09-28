"""GET /health: liveness plus a database check (design doc section 14)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import Engine

from typist.db import check_database, get_engine
from typist.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
)
def get_health(
    engine: Annotated[Engine, Depends(get_engine)], response: Response
) -> HealthResponse:
    """200 {"status": "ok", "db": "ok"} if `SELECT 1` runs, else 503 with both set to "error"."""
    if check_database(engine):
        return HealthResponse(status="ok", db="ok")
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="error", db="error")
