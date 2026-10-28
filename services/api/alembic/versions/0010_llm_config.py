"""llm config: model_id, model_revision, prompt_version, sampler settings (T3.2).

Revision ID: 0010_llm_config
Revises: 0009_markov_config
Create Date: 2026-10-28 00:00:00.000000

Data-only migration. Inserts the 6 LLM generator keys into experiment_config (design doc 13.5;
T3.2 owner answer 3). Stored as json.dumps text. Downgrade deletes only these keys.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_llm_config"
down_revision: str | Sequence[str] | None = "0009_markov_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LLM_CONFIG_DEFAULTS: dict[str, object] = {
    "llm_model_id": "mlx-community/Llama-3.2-1B-Instruct-4bit",
    "llm_model_revision": "08231374eeacb049a0eade7922910865b8fce912",
    "llm_prompt_version": "v1",
    "llm_temperature": 0.8,
    "llm_top_p": 0.9,
    "llm_max_tokens": 160,
}

_config_table = sa.table(
    "experiment_config",
    sa.column("key", sa.String()),
    sa.column("value", sa.Text()),
    sa.column("frozen_at", sa.DateTime()),
)


def upgrade() -> None:
    """Insert the 6 LLM configuration keys (unfrozen)."""
    op.bulk_insert(
        _config_table,
        [
            {"key": key, "value": json.dumps(value), "frozen_at": None}
            for key, value in LLM_CONFIG_DEFAULTS.items()
        ],
    )


def downgrade() -> None:
    """Delete only the 6 LLM configuration keys."""
    op.execute(
        _config_table.delete().where(
            _config_table.c.key.in_(list(LLM_CONFIG_DEFAULTS.keys()))
        )
    )
