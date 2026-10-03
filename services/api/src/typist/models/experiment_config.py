"""experiment_config table (design doc section 8.1): global experiment parameters, one per key.

Revision 0001 seeds practice_days, block_chars, d_min, d_max and arms_enabled (T1.1 owner answer
16). Other keys (assignment_seed, model_id, prompt_version, sampler) are added by the tasks that
own them. frozen_at is set when a key is frozen; a frozen key never changes (CLAUDE.md), which
T3.5 enforces. The table is global: per-participant values come from combining a global value
with participant_id in code (T1.1 owner answer 17).
"""

from datetime import datetime
from typing import Any, ClassVar

from sqlmodel import Field, SQLModel

from typist.models.base import JSONText


class ExperimentConfig(SQLModel, table=True):
    """One experiment parameter; value is JSON (number, string, list or object) stored as TEXT."""

    # ClassVar[Any]: see "Table names" in typist/models/__init__.py.
    __tablename__: ClassVar[Any] = "experiment_config"

    key: str = Field(primary_key=True)
    value: Any = Field(sa_type=JSONText, nullable=False)
    frozen_at: datetime | None = None
