"""Request and response schemas for session endpoints (design doc sections 9.2, 10.1, 14; D18; T1.9, T2.6).

Table models are never returned from the API (17.1). BlockPlan and SessionPlan omit `arm`,
`passage_id`, and `block_order` so a blinded participant never sees which arm a practice block
belongs to (D18, section 3.3).
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SessionStartRequest(BaseModel):
    """Optional request body for POST /api/v1/participants/{participant_id}/sessions."""

    phase: str | None = None
    client_info: dict[str, Any] = Field(default_factory=dict)


class BlockPlan(BaseModel):
    """One block inside a SessionPlan (design doc section 9.2 Figure 5, section 14; D18).

    `label` is the 1-based blinded label ('Block 1'..'Block 4'). `arm` is deliberately omitted.
    """

    block_id: str
    block_index: int
    label: str
    target_text: str
    started_at: datetime | None = None
    ended_at: datetime | None = None


class SessionPlan(BaseModel):
    """Response schema for POST /participants/{pid}/sessions and GET /sessions/{sid} (section 14; D18)."""

    session_id: str
    participant_id: str
    phase: str
    day_index: int
    status: str
    blocks: list[BlockPlan]


class SessionSummary(BaseModel):
    """What POST /sessions/{session_id}/complete returns: the computed session stats.

    wpm and accuracy are None when undefined (owner answer 5). bigram_count is the number of
    bigram_stats rows written for the session; blocks is the number of blocks in the session.
    """

    session_id: str
    wpm: float | None
    accuracy: float | None
    bigram_count: int
    blocks: int
