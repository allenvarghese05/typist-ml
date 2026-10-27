"""Response schemas for admin endpoints (design doc 14)."""

from pydantic import BaseModel


class AssignmentResponse(BaseModel):
    """Response returned by POST /api/v1/admin/participants/{participant_id}/assign."""

    participant_id: str
    status: str
    frozen_bigrams: int
    mapping: dict[str, str]
    form_b_composed: bool
