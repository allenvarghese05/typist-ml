"""Response and request schemas for admin endpoints (design doc 14; T2.8, T2.9)."""

from datetime import datetime

from pydantic import BaseModel, Field


class AssignmentResponse(BaseModel):
    """Response returned by POST /api/v1/admin/participants/{participant_id}/assign."""

    participant_id: str
    status: str
    frozen_bigrams: int
    mapping: dict[str, str]
    form_b_composed: bool


class ArmPoolStatus(BaseModel):
    """Drill pool counts and readiness for one arm."""

    arm: str
    ready_count: int
    target_count: int
    queued_count: int
    used_count: int
    deficit: int
    is_ready: bool


class PoolResponse(BaseModel):
    """Ready drill pool status per arm for a participant."""

    participant_id: str
    alias: str
    arms: list[ArmPoolStatus]


class ReplenishRequest(BaseModel):
    """Payload to trigger drill pool replenishment for a participant."""

    participant_id: str


class JobResponse(BaseModel):
    """Details of a background drill generation job."""

    id: str
    participant_id: str
    arm: str
    requested: int
    status: str
    retries: int
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobCreate(BaseModel):
    """Payload to enqueue a generation job manually."""

    participant_id: str
    arm: str | None = None
    requested: int = Field(default=1, ge=1)


class CheckDetail(BaseModel):
    """Result of a single boolean check with occurrence count and explanation list."""

    passed: bool
    count: int
    details: list[str]


class DwellCheckDetail(BaseModel):
    """Result of the dwell time anomalies check."""

    passed: bool
    negative_count: int
    over_1000ms_count: int
    details: list[str]


class MissingKeyupsDetail(BaseModel):
    """Result of the missing keyup events check."""

    passed: bool
    total_events: int
    missing_count: int
    missing_share: float
    details: list[str]


class DataChecksResult(BaseModel):
    """The 5 daily data quality checks (design doc 12.6)."""

    seq_gaps: CheckDetail
    dwell_anomalies: DwellCheckDetail
    short_blocks: CheckDetail
    missing_keyups: MissingKeyupsDetail
    in_progress_sessions: CheckDetail


class SessionTrendEntry(BaseModel):
    """Session performance metrics and per-set error rates on practice text (Owner decision #5)."""

    session_id: str
    phase: str
    day_index: int
    started_at: datetime
    wpm: float | None = None
    accuracy: float | None = None
    per_set_error_rate: dict[str, float | None]
    per_set_attempts: dict[str, int]
    per_set_errors: dict[str, int]


class ChecksResponse(BaseModel):
    """Complete data-quality report and session trend table for one participant."""

    participant_id: str
    alias: str
    status: str
    passed: bool
    checks: DataChecksResult
    trend: list[SessionTrendEntry]
