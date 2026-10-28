"""markov config: the markov_beta experiment_config key (T3.1).

Revision ID: 0009_markov_config
Revises: 0008_retest_config
Create Date: 2026-10-28 00:00:00.000000

Data-only migration. Inserts markov_beta into experiment_config (design doc 13.4 steps 2 and 4;
T3.1 owner answer 6). Section 13.4 default is 4.0; M3 beta tuning on representative sets selects
10.0 to guarantee median target density lands inside [d_min, d_max] = [0.15, 0.40]. Stored as
json.dumps text. Downgrade deletes only this key.
"""

from collections.abc import Sequence
import json

from alembic import op
import sqlalchemy as sa

revision: str = "0009_markov_config"
down_revision: str | Sequence[str] | None = "0008_retest_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MARKOV_CONFIG_DEFAULTS: dict[str, object] = {
    "markov_beta": 10.0,
}

_config_table = sa.table(
    "experiment_config",
    sa.column("key", sa.String()),
    sa.column("value", sa.Text()),
    sa.column("frozen_at", sa.DateTime()),
)


def upgrade() -> None:
    """Insert the markov_beta key (unfrozen)."""
    op.bulk_insert(
        _config_table,
        [
            {"key": key, "value": json.dumps(value), "frozen_at": None}
            for key, value in MARKOV_CONFIG_DEFAULTS.items()
        ],
    )


def downgrade() -> None:
    """Delete only the markov_beta key."""
    op.execute(
        _config_table.delete().where(
            _config_table.c.key.in_(list(MARKOV_CONFIG_DEFAULTS.keys()))
        )
    )
