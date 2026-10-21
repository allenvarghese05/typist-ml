"""baseline config: six experiment_config keys for the corpus build and the form A composer (T1.8)

Revision ID: 0002_baseline_config
Revises: 0001_initial_schema
Create Date: 2026-10-19 00:00:00.000000

Data-only migration. It inserts the six keys the corpus build and the baseline composer read
(T1.8 owner answer 2), all unfrozen, and never touches the keys 0001 seeded. Values are stored
as json.dumps text because experiment_config.value is TEXT and read back through
typist.models.base.JSONText (T1.1 Revision 3). Downgrade deletes only these six keys, leaving
0001's five in place.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_baseline_config"
down_revision: str | Sequence[str] | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# New keys and their defaults (T1.8 owner answer 2; baseline_part_chars set to 2700 by the T1.8
# plan's "## Orchestrator answers" O1/O1a: one part per baseline session (owner option A), and the
# coverage-efficient composer reaches every top-150 bigram's 15 combined with margin +5 at 2700).
BASELINE_CONFIG_DEFAULTS: dict[str, object] = {
    "tracked_bigram_count": 150,
    "baseline_min_occurrences": 15,
    "baseline_parts": 2,
    "baseline_part_chars": 2700,
    "corpus_seed": 20261019,
    "corpus_word_count": 20000,
}

_config_table = sa.table(
    "experiment_config",
    sa.column("key", sa.String()),
    sa.column("value", sa.Text()),
    sa.column("frozen_at", sa.DateTime()),
)


def upgrade() -> None:
    """Insert the six baseline keys, all unfrozen, without touching 0001's keys."""
    op.bulk_insert(
        _config_table,
        [
            {"key": key, "value": json.dumps(value), "frozen_at": None}
            for key, value in BASELINE_CONFIG_DEFAULTS.items()
        ],
    )


def downgrade() -> None:
    """Delete only the six baseline keys; 0001's keys are left in place."""
    op.execute(
        _config_table.delete().where(_config_table.c.key.in_(list(BASELINE_CONFIG_DEFAULTS.keys())))
    )
