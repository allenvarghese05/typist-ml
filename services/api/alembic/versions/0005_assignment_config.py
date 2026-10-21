"""assignment config: five experiment_config keys plus the bigram_assignment freeze trigger (T2.2).

Revision ID: 0005_assignment_config
Revises: 0004_m2_tables
Create Date: 2026-10-21 00:00:00.000000

Data-and-trigger migration. It inserts the five assignment keys the ranking/split/shuffle read
(T2.2 owner answer 2), all unfrozen, and never touches keys 0001/0002 seeded. Values are stored
as json.dumps text because experiment_config.value is TEXT, read back through
typist.models.base.JSONText. It also creates a BEFORE UPDATE trigger on bigram_assignment that
aborts any UPDATE of a row whose frozen_at is already set (D04 "Frozen rows are never updated";
owner answer 7): SQLite RAISE(ABORT) surfaces as sqlite3.IntegrityError. Alembic's compare_metadata
does not track triggers, so this adds no schema drift (test_schema stays green). Downgrade drops
the trigger (before 0004 drops the table) and deletes only these five keys.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.

revision: str = "0005_assignment_config"
down_revision: str | Sequence[str] | None = "0004_m2_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# New keys and defaults (T2.2 owner answer 2). assignment_min_observations = 15 is the D28 ADR
# (owner answer 8); the others are 3.4's strength (20), per-set 4 and fallback 3; assignment_seed
# 20261021 is the frozen global seed combined with participant_id in code (owner answer 5).
ASSIGNMENT_CONFIG_DEFAULTS: dict[str, object] = {
    "assignment_seed": 20261021,
    "assignment_prior_strength": 20,
    "assignment_min_observations": 15,
    "assignment_per_set": 4,
    "assignment_per_set_fallback": 3,
}

_config_table = sa.table(
    "experiment_config",
    sa.column("key", sa.String()),
    sa.column("value", sa.Text()),
    sa.column("frozen_at", sa.DateTime()),
)

# The freeze trigger (owner answer 7). Single statement; op.execute runs it verbatim.
_CREATE_FREEZE_TRIGGER = (
    "CREATE TRIGGER trg_bigram_assignment_frozen "
    "BEFORE UPDATE ON bigram_assignment "
    "WHEN OLD.frozen_at IS NOT NULL "
    "BEGIN SELECT RAISE(ABORT, 'bigram_assignment rows are frozen'); END"
)


def upgrade() -> None:
    """Insert the five assignment keys (unfrozen) and create the freeze trigger."""
    op.bulk_insert(
        _config_table,
        [
            {"key": key, "value": json.dumps(value), "frozen_at": None}
            for key, value in ASSIGNMENT_CONFIG_DEFAULTS.items()
        ],
    )
    op.execute(_CREATE_FREEZE_TRIGGER)


def downgrade() -> None:
    """Drop the freeze trigger and delete only the five assignment keys."""
    op.execute("DROP TRIGGER IF EXISTS trg_bigram_assignment_frozen")
    op.execute(
        _config_table.delete().where(
            _config_table.c.key.in_(list(ASSIGNMENT_CONFIG_DEFAULTS.keys()))
        )
    )
