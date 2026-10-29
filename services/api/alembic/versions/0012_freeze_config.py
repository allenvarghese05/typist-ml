"""freeze config: set frozen_at on all 33 seeded keys and install immutability triggers (T3.5).

Revision ID: 0012_freeze_config
Revises: 0011_calibrate_density
Create Date: 2026-10-29 00:00:00.000000

Data-and-trigger migration. Sets frozen_at = '2026-10-29 00:00:00' for all 33 seeded keys in
experiment_config (design doc §8.1, §16; ADR D04, D20; T3.5 owner answers 1-4). Installs two
BEFORE triggers on experiment_config (trg_experiment_config_frozen_update and
trg_experiment_config_frozen_delete) that abort any UPDATE or DELETE of a row whose frozen_at is
NOT NULL with RAISE(ABORT, 'experiment_config keys are frozen'), surfacing in Python as
sqlite3.IntegrityError. Downgrade drops the two triggers first, then resets frozen_at = NULL.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012_freeze_config"
down_revision: str | Sequence[str] | None = "0011_calibrate_density"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FROZEN_AT_TIMESTAMP = "2026-10-29 00:00:00"

_config_table = sa.table(
    "experiment_config",
    sa.column("key", sa.String()),
    sa.column("value", sa.Text()),
    sa.column("frozen_at", sa.DateTime()),
)

_CREATE_UPDATE_TRIGGER = (
    "CREATE TRIGGER trg_experiment_config_frozen_update "
    "BEFORE UPDATE ON experiment_config "
    "WHEN OLD.frozen_at IS NOT NULL "
    "BEGIN SELECT RAISE(ABORT, 'experiment_config keys are frozen'); END"
)

_CREATE_DELETE_TRIGGER = (
    "CREATE TRIGGER trg_experiment_config_frozen_delete "
    "BEFORE DELETE ON experiment_config "
    "WHEN OLD.frozen_at IS NOT NULL "
    "BEGIN SELECT RAISE(ABORT, 'experiment_config keys are frozen'); END"
)


def upgrade() -> None:
    """Freeze all seeded keys and install UPDATE and DELETE immutability triggers."""
    op.execute(f"UPDATE experiment_config SET frozen_at = '{FROZEN_AT_TIMESTAMP}'")
    op.execute(_CREATE_UPDATE_TRIGGER)
    op.execute(_CREATE_DELETE_TRIGGER)


def downgrade() -> None:
    """Drop the triggers first, then unfreeze all keys."""
    op.execute("DROP TRIGGER IF EXISTS trg_experiment_config_frozen_update")
    op.execute("DROP TRIGGER IF EXISTS trg_experiment_config_frozen_delete")
    op.execute("UPDATE experiment_config SET frozen_at = NULL")
