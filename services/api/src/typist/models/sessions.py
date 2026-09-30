"""sessions and session_blocks tables (design doc section 8.1); a block belongs to one session.

`Session` here is a typing session (one sitting of baseline, practice or retest), not the ORM
session. Modules that need both import this class as
`from typist.models import Session as TypingSession`.
"""

from datetime import datetime
from typing import Any, ClassVar, Final

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from typist.models.base import new_id, sql_in

SESSION_PHASES: Final[tuple[str, ...]] = ("baseline", "practice", "retest")
SESSION_STATUSES: Final[tuple[str, ...]] = ("in_progress", "completed", "abandoned")
BLOCK_ARMS: Final[tuple[str, ...]] = ("test", "control", "heuristic", "markov", "llm")


class Session(SQLModel, table=True):
    """One session of one participant (states in section 9.3).

    day_index is 1-based within the phase. A retried abandoned session gets the next day_index,
    never the abandoned one's (T1.1 owner answer 11), so (participant_id, phase, day_index) is
    indexed (section 8.2) but not unique. block_order is NULL for baseline and retest sessions (no
    Latin square); wpm, accuracy and ended_at stay NULL until the session completes. client_info
    is set at creation.
    """

    # ClassVar[Any]: see "Table names" in typist/models/__init__.py.
    __tablename__: ClassVar[Any] = "sessions"
    __table_args__ = (
        sa.CheckConstraint(sql_in("phase", SESSION_PHASES), name="phase"),
        sa.CheckConstraint(sql_in("status", SESSION_STATUSES), name="status"),
        sa.CheckConstraint("day_index >= 1", name="day_index"),
        sa.Index(
            "ix_sessions_participant_id_phase_day_index", "participant_id", "phase", "day_index"
        ),
    )

    id: str = Field(default_factory=new_id, primary_key=True)
    participant_id: str = Field(foreign_key="participants.id")
    phase: str
    day_index: int
    block_order: str | None = None
    status: str = "in_progress"
    wpm: float | None = None
    accuracy: float | None = None
    client_info: dict[str, Any] = Field(sa_type=sa.JSON)
    started_at: datetime
    ended_at: datetime | None = None


class SessionBlock(SQLModel, table=True):
    """One block of a session.

    Practice sessions have four blocks, block_index 0 to 3, one per arm. Test sessions (baseline,
    retest) have one block per passage, arm "test", block_index equal to the passage's part, with
    no upper bound; the database only checks block_index >= 0 (T1.1 owner answer 12). passage_id
    is set for test blocks only; practice drills link back through drills.used_in_block_id
    (T2.1). target_text is set at creation; started_at and ended_at stay NULL until the block
    starts and ends.
    """

    # ClassVar[Any]: see "Table names" in typist/models/__init__.py.
    __tablename__: ClassVar[Any] = "session_blocks"
    __table_args__ = (
        sa.UniqueConstraint("session_id", "block_index"),
        sa.CheckConstraint(sql_in("arm", BLOCK_ARMS), name="arm"),
        sa.CheckConstraint("block_index >= 0", name="block_index"),
    )

    id: str = Field(default_factory=new_id, primary_key=True)
    session_id: str = Field(foreign_key="sessions.id")
    block_index: int
    arm: str
    passage_id: str | None = Field(default=None, foreign_key="text_passages.id")
    target_text: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
