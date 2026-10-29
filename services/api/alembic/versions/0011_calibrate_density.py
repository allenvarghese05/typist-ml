"""calibrate density: update d_min to 0.10 and d_max to 0.40 (T3.4).

Revision ID: 0011_calibrate_density
Revises: 0010_llm_config
Create Date: 2026-10-29 00:00:00.000000

Data-only migration. Updates d_min from 0.15 to 0.10 and d_max to 0.40 in experiment_config
(design doc 13.1, 16; ADR D30; T3.4 owner answer 3). Stored as json.dumps text. Downgrade
reverts d_min to 0.15 and d_max to 0.40.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_calibrate_density"
down_revision: str | Sequence[str] | None = "0010_llm_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CALIBRATED_DENSITY_BOUNDS: dict[str, float] = {
    "d_min": 0.10,
    "d_max": 0.40,
}

INITIAL_DENSITY_BOUNDS: dict[str, float] = {
    "d_min": 0.15,
    "d_max": 0.40,
}

_config_table = sa.table(
    "experiment_config",
    sa.column("key", sa.String()),
    sa.column("value", sa.Text()),
    sa.column("frozen_at", sa.DateTime()),
)


def upgrade() -> None:
    """Update d_min to 0.10 and d_max to 0.40 (unfrozen)."""
    for key, value in CALIBRATED_DENSITY_BOUNDS.items():
        op.execute(
            _config_table.update().where(_config_table.c.key == key).values(value=json.dumps(value))
        )


def downgrade() -> None:
    """Revert d_min to 0.15 and d_max to 0.40."""
    for key, value in INITIAL_DENSITY_BOUNDS.items():
        op.execute(
            _config_table.update().where(_config_table.c.key == key).values(value=json.dumps(value))
        )
