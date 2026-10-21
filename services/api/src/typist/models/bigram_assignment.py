"""bigram_assignment table (design doc section 8.1, 3.4; D01, D04): the frozen within-person map.

One row per (participant_id, bigram): the weak bigram's set (A-D), the arm mapped to that set, and
the baseline snapshot (rank, weakness score, attempts, errors) taken at freeze time. (participant_id,
bigram) is the composite primary key -- the first composite PK in the schema. Rows become immutable
after frozen_at (D04); T2.1 only creates the table, T2.2 (assignment.py) writes and freezes it, so
there is no immutability trigger here. frozen_at is NULL until T2.2 freezes a row.
"""

from datetime import datetime
from typing import Any, ClassVar, Final

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from typist.models.base import sql_in
from typist.models.drills import DRILL_ARMS

SET_LABELS: Final[tuple[str, ...]] = ("A", "B", "C", "D")


class BigramAssignment(SQLModel, table=True):
    """One (participant_id, bigram) assignment row (section 8.1 columns, section 3.4 snapshot).

    Composite PK (participant_id, bigram); participant_id is also a FK to participants.id. set_label
    is A/B/C/D, arm is one of D03's four generated arms (DRILL_ARMS, no 'test'). length(bigram) = 2
    enforces the two-letter key (D13). baseline_rank >= 1 and the two baseline counts >= 0.
    """

    # ClassVar[Any]: see "Table names" in typist/models/__init__.py.
    __tablename__: ClassVar[Any] = "bigram_assignment"
    __table_args__ = (
        sa.CheckConstraint(sql_in("set_label", SET_LABELS), name="set_label"),
        sa.CheckConstraint(sql_in("arm", DRILL_ARMS), name="arm"),
        sa.CheckConstraint("length(bigram) = 2", name="bigram"),
        sa.CheckConstraint("baseline_rank >= 1", name="baseline_rank"),
        sa.CheckConstraint("baseline_attempts >= 0", name="baseline_attempts"),
        sa.CheckConstraint("baseline_errors >= 0", name="baseline_errors"),
    )

    participant_id: str = Field(foreign_key="participants.id", primary_key=True)
    bigram: str = Field(primary_key=True)
    set_label: str
    arm: str
    baseline_rank: int
    weakness_score: float
    baseline_attempts: int
    baseline_errors: int
    frozen_at: datetime | None = None
