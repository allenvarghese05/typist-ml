"""Request and response schemas for participant endpoints (design doc 4.2, 9.3, 14; D18)."""

from datetime import datetime

from pydantic import BaseModel, model_validator


class ParticipantCreate(BaseModel):
    """Payload for POST /api/v1/participants."""

    alias: str
    is_builder: bool = False
    is_blinded: bool = True
    keyboard_label: str | None = None

    @model_validator(mode="after")
    def check_builder_not_blinded(self) -> "ParticipantCreate":
        if self.is_builder:
            self.is_blinded = False
        return self


class ParticipantConsent(BaseModel):
    """Optional payload for POST /api/v1/participants/{participant_id}/consent."""

    keyboard_label: str | None = None


class ParticipantResponse(BaseModel):
    """Public participant response schema; never exposes table models (17.1)."""

    id: str
    alias: str
    is_builder: bool
    is_blinded: bool
    status: str
    keyboard_label: str | None = None
    consent_at: datetime | None = None
    created_at: datetime


class ParticipantDeletionResponse(BaseModel):
    """Summary of deleted rows from DELETE /api/v1/participants/{participant_id}."""

    participant_id: str
    bigram_assignment: int
    drills: int
    generation_jobs: int
    generation_attempts: int
    bigram_stats: int
    keystroke_events: int
    session_blocks: int
    sessions: int
    text_passages: int
    participants: int
