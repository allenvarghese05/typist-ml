"""retest config: three experiment_config keys for the form B retest composer (T2.7).

Revision ID: 0008_retest_config
Revises: 0007_generator_config
Create Date: 2026-10-26 00:00:00.000000

Data-only migration. Inserts the three keys read by the retest (form B) composer (T2.7 owner answer
2): retest_min_occurrences (40, design doc 3.2/3.5/16), retest_parts (2, two retest sessions on days
12 and 13), and retest_part_chars (2700, matching baseline_part_chars for ~10-minute sessions). All
three are inserted unfrozen without touching keys seeded by 0001/0002/0005/0006/0007. Downgrade
deletes only these three keys.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.

revision: str = "0008_retest_config"
down_revision: str | Sequence[str] | None = "0007_generator_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RETEST_CONFIG_DEFAULTS: dict[str, object] = {
    "retest_min_occurrences": 40,
    "retest_parts": 2,
    "retest_part_chars": 2700,
}

_config_table = sa.table(
    "experiment_config",
    sa.column("key", sa.String()),
    sa.column("value", sa.Text()),
    sa.column("frozen_at", sa.DateTime()),
)


def upgrade() -> None:
    """Insert the three retest composer keys (unfrozen)."""
    op.bulk_insert(
        _config_table,
        [
            {"key": key, "value": json.dumps(value), "frozen_at": None}
            for key, value in RETEST_CONFIG_DEFAULTS.items()
        ],
    )


def downgrade() -> None:
    """Delete only the three retest composer keys."""
    op.execute(
        _config_table.delete().where(_config_table.c.key.in_(list(RETEST_CONFIG_DEFAULTS.keys())))
    )
