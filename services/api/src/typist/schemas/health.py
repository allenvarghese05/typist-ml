"""Response schema for GET /api/v1/health (design doc section 14)."""

from typing import Literal

from pydantic import BaseModel

HealthState = Literal["ok", "error"]


class HealthResponse(BaseModel):
    """Body of GET /api/v1/health.

    status is "ok" only if every check passed. T2.5 adds the worker heartbeat as its own field,
    and that field never changes status (the worker does not run on Linux).
    """

    status: HealthState
    db: HealthState
