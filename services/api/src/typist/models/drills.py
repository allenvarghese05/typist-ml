"""drills table (design doc section 8.1, 8.2; D03, D11, D16): one generated practice text per row.

Holds the drill text and its fairness metrics (target_density, mean_word_len, real_word_ratio, D16)
plus the reproducibility fields (generator_version, model_id, prompt_version, seed, D10/D09). arm is
one of D03's four generated arms (DRILL_ARMS -- no 'test', unlike session_blocks' BLOCK_ARMS). status
is ready/used/retired (D11). target_bigrams is a JSON list, [] for control (section 8.1 "Empty for
control"; JSONText cannot store a JSON null). used_in_block_id links a used drill back to its block
(section 7); NULL while ready/retired. model_id and prompt_version are LLM-only, so NULL for other
arms. created_at is filled by the database (CURRENT_TIMESTAMP) when the app leaves it None.

DRILL_ARMS is defined here and imported by bigram_assignment.py and generation.py (all three columns
share D03's four arms); this module imports only base, so there is no import cycle.
"""

from datetime import datetime
from typing import Any, ClassVar, Final

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from typist.models.base import JSONText, new_id, sql_in

DRILL_ARMS: Final[tuple[str, ...]] = ("control", "heuristic", "markov", "llm")
DRILL_STATUSES: Final[tuple[str, ...]] = ("ready", "used", "retired")


class Drill(SQLModel, table=True):
    """One generated drill (section 8.1 columns).

    arm IN DRILL_ARMS and status IN DRILL_STATUSES are the only CHECKs (the fairness metrics have no
    range constraint in section 8.1). participant_id FK -> participants; used_in_block_id nullable FK
    -> session_blocks. seed is INTEGER; generator_version/model_id/prompt_version are TEXT (model_id
    and prompt_version LLM-only, hence nullable).
    """

    # ClassVar[Any]: see "Table names" in typist/models/__init__.py.
    __tablename__: ClassVar[Any] = "drills"
    __table_args__ = (
        sa.CheckConstraint(sql_in("arm", DRILL_ARMS), name="arm"),
        sa.CheckConstraint(sql_in("status", DRILL_STATUSES), name="status"),
        sa.Index("ix_drills_participant_id_arm_status", "participant_id", "arm", "status"),
    )

    id: str = Field(default_factory=new_id, primary_key=True)
    participant_id: str = Field(foreign_key="participants.id")
    arm: str
    target_bigrams: list[str] = Field(sa_type=JSONText)
    text: str
    target_density: float
    mean_word_len: float
    real_word_ratio: float
    generator_version: str
    model_id: str | None = None
    prompt_version: str | None = None
    seed: int
    status: str
    used_in_block_id: str | None = Field(default=None, foreign_key="session_blocks.id")
    created_at: datetime | None = Field(
        default=None,
        nullable=False,
        sa_column_kwargs={"server_default": sa.text("CURRENT_TIMESTAMP")},
    )
