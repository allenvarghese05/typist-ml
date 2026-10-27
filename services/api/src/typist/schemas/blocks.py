"""Request and response schemas for session block endpoints (design doc 14; D18)."""

from datetime import datetime

from pydantic import BaseModel


class BlockResponse(BaseModel):
    """Blinded block representation returned by POST /blocks/{bid}/start and /complete."""

    id: str
    session_id: str
    block_index: int
    label: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
