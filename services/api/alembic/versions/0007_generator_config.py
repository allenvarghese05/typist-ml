"""generator config: the control_word_pool experiment_config key (T2.4).

Revision ID: 0007_generator_config
Revises: 0006_validator_config
Create Date: 2026-10-22 00:00:00.000000

Data-only migration. It inserts the single generator key control_word_pool (owner answer 1): the
control generator draws from the pool_size most frequent a-z words, which is index.words[:5000]
because words.json is rank-ordered (13.2 "5,000 most frequent"). It is unfrozen and never touches
keys seeded by 0001/0002/0005/0006. The value is stored as json.dumps text because
experiment_config.value is TEXT, read back through typist.models.base.JSONText. T2.5 reads this key
when it builds a control DrillSpec's pool; T2.4's generators take pool_size directly. Downgrade
deletes only this key.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.

revision: str = "0007_generator_config"
down_revision: str | Sequence[str] | None = "0006_validator_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# New key and default (T2.4 owner answer 1). 5000 is 13.2's "5,000 most frequent words"; the
# sqrt weighting, temperature 0.5, top-50 and the 2-use cap stay algorithm constants in code.
GENERATOR_CONFIG_DEFAULTS: dict[str, object] = {
    "control_word_pool": 5000,
}

_config_table = sa.table(
    "experiment_config",
    sa.column("key", sa.String()),
    sa.column("value", sa.Text()),
    sa.column("frozen_at", sa.DateTime()),
)


def upgrade() -> None:
    """Insert the control_word_pool key (unfrozen)."""
    op.bulk_insert(
        _config_table,
        [
            {"key": key, "value": json.dumps(value), "frozen_at": None}
            for key, value in GENERATOR_CONFIG_DEFAULTS.items()
        ],
    )


def downgrade() -> None:
    """Delete only the control_word_pool key."""
    op.execute(
        _config_table.delete().where(
            _config_table.c.key.in_(list(GENERATOR_CONFIG_DEFAULTS.keys()))
        )
    )
