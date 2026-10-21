"""generation_jobs and generation_attempts tables (design doc section 8.1; D11, section 10.2, 13.5).

generation_jobs is the batch worker's queue (one job = produce N drills for one arm); status is
pending/running/done/failed. generation_attempts is the per-call audit log (up to 5 LLM attempts per
accepted drill, section 13.5): one row per model call, kept for the rejection rate and the write-up.

generation_attempts.id is an INTEGER rowid (section 8.1 prints "attempts.id ... INTEGER"): it is the
third high-volume audit table (one row per model call, many per drill), the same rationale section 8
gives for keystroke_events and bigram_stats using integer ids. drill_id is NULL until an attempt is
accepted (section 8.1 "drill_id set when accepted"); gen_ms/gen_tokens/tokens_per_sec/peak_memory_mb
are LLM-only and NULL for other arms; reject_reasons is a JSON list, [] when accepted.
"""

from datetime import datetime
from typing import Any, ClassVar, Final

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from typist.models.base import JSONText, new_id, sql_in
from typist.models.drills import DRILL_ARMS

JOB_STATUSES: Final[tuple[str, ...]] = ("pending", "running", "done", "failed")


class GenerationJob(SQLModel, table=True):
    """One drill-generation job (section 8.1 columns).

    arm IN DRILL_ARMS, status IN JOB_STATUSES, requested >= 1, retries >= 0 (retries server-defaults
    to 0). participant_id FK -> participants (owner answer 4: jobs are a per-participant table).
    created_at is DB-filled (CURRENT_TIMESTAMP); started_at/finished_at are NULL until the worker
    claims/finishes the job; error is NULL unless the job failed.
    """

    # ClassVar[Any]: see "Table names" in typist/models/__init__.py.
    __tablename__: ClassVar[Any] = "generation_jobs"
    __table_args__ = (
        sa.CheckConstraint(sql_in("arm", DRILL_ARMS), name="arm"),
        sa.CheckConstraint(sql_in("status", JOB_STATUSES), name="status"),
        sa.CheckConstraint("requested >= 1", name="requested"),
        sa.CheckConstraint("retries >= 0", name="retries"),
        sa.Index("ix_generation_jobs_status_created_at", "status", "created_at"),
    )

    id: str = Field(default_factory=new_id, primary_key=True)
    participant_id: str = Field(foreign_key="participants.id")
    arm: str
    requested: int
    status: str
    retries: int = Field(default=0, sa_column_kwargs={"server_default": sa.text("0")})
    error: str | None = None
    created_at: datetime | None = Field(
        default=None,
        nullable=False,
        sa_column_kwargs={"server_default": sa.text("CURRENT_TIMESTAMP")},
    )
    started_at: datetime | None = None
    finished_at: datetime | None = None


class GenerationAttempt(SQLModel, table=True):
    """One model call for a job (section 8.1 columns); id is the SQLite rowid (INTEGER, no AUTOINCREMENT).

    job_id FK -> generation_jobs (NOT NULL); drill_id nullable FK -> drills (set when accepted). density
    and accepted are always present; reject_reasons is a JSON list ([] when accepted). The four LLM-only
    timing/memory columns are nullable (NULL for non-LLM arms). accepted is a plain Boolean (no CHECK,
    matching keystroke_events.after_pause). An (job_id) index serves the worker's per-job lookups (8.2).
    """

    # ClassVar[Any]: see "Table names" in typist/models/__init__.py.
    __tablename__: ClassVar[Any] = "generation_attempts"
    __table_args__ = (sa.Index("ix_generation_attempts_job_id", "job_id"),)

    id: int | None = Field(default=None, primary_key=True)
    job_id: str = Field(foreign_key="generation_jobs.id")
    drill_id: str | None = Field(default=None, foreign_key="drills.id")
    raw_output: str
    clean_text: str
    density: float
    accepted: bool
    reject_reasons: list[str] = Field(sa_type=JSONText)
    gen_ms: float | None = None
    gen_tokens: int | None = None
    tokens_per_sec: float | None = None
    peak_memory_mb: float | None = None
