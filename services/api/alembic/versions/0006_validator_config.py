"""validator config: the six drill-validator experiment_config keys (T2.3).

Revision ID: 0006_validator_config
Revises: 0005_assignment_config
Create Date: 2026-10-22 00:00:00.000000

Data-only migration. It inserts the six validator keys the DrillValidator and GenerationService
read (T2.3 owner answer 5), all unfrozen, and never touches keys seeded by 0001/0002/0005. Values
are stored as json.dumps text because experiment_config.value is TEXT, read back through
typist.models.base.JSONText. d_min/d_max already exist (0001) and are not re-seeded. Downgrade
deletes only these six keys.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.

revision: str = "0006_validator_config"
down_revision: str | Sequence[str] | None = "0005_assignment_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# New keys and defaults (T2.3 owner answer 5). drill_length_chars/drill_min_length_chars are the
# 13.1 "300 ... reject if under 270"; the limits are 13.1's coverage/repetition "3" and the LLM
# real-word-ratio gate "0.8". d_min/d_max stay in 0001 (the validator reads them off the DrillSpec).
VALIDATOR_CONFIG_DEFAULTS: dict[str, object] = {
    "drill_length_chars": 300,
    "drill_min_length_chars": 270,
    "drill_min_coverage": 3,
    "drill_max_word_repeats": 3,
    "drill_max_bigram_run": 3,
    "drill_min_real_word_ratio": 0.8,
}

_config_table = sa.table(
    "experiment_config",
    sa.column("key", sa.String()),
    sa.column("value", sa.Text()),
    sa.column("frozen_at", sa.DateTime()),
)


def upgrade() -> None:
    """Insert the six validator keys (unfrozen)."""
    op.bulk_insert(
        _config_table,
        [
            {"key": key, "value": json.dumps(value), "frozen_at": None}
            for key, value in VALIDATOR_CONFIG_DEFAULTS.items()
        ],
    )


def downgrade() -> None:
    """Delete only the six validator keys."""
    op.execute(
        _config_table.delete().where(
            _config_table.c.key.in_(list(VALIDATOR_CONFIG_DEFAULTS.keys()))
        )
    )
