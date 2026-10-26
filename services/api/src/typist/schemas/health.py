"""Response schema for GET /api/v1/health (design doc section 14; T0.3, T2.5)."""

from typing import Literal

from pydantic import BaseModel

HealthState = Literal["ok", "error"]


class HealthResponse(BaseModel):
    """Body of GET /api/v1/health.

    status is "ok" only if every check passed. worker_heartbeat_age_s reports the age in seconds of
    the worker's last heartbeat file (or None when no heartbeat file exists or db is "error"), and
    never changes status (the worker does not run on Linux; T0.3 owner answer 3, T2.5 owner answer 1).
    """

    status: HealthState
    db: HealthState
    worker_heartbeat_age_s: float | None = None
