"""Migration 0011 updates d_min to 0.10 and d_max to 0.40; downgrade reverts d_min to 0.15 (T3.4)."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from alembic import command
from sqlalchemy import Engine

from typist.migrations import alembic_config


def _config(db_path: Path) -> dict[str, object]:
    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute("SELECT key, value FROM experiment_config").fetchall()
    return {key: json.loads(value) for key, value in rows}


def test_0011_calibrates_density_bounds(isolated_settings: Path, migrated_engine: Engine) -> None:
    """At HEAD, d_min is 0.10 and d_max is 0.40; both are frozen by 0012."""
    config = _config(isolated_settings)
    assert config["d_min"] == 0.10
    assert config["d_max"] == 0.40
    with closing(sqlite3.connect(isolated_settings)) as connection:
        for key in ("d_min", "d_max"):
            row = connection.execute(
                "SELECT frozen_at FROM experiment_config WHERE key = ?", (key,)
            ).fetchone()
            assert row is not None
            assert row[0] == "2026-10-29 00:00:00"


def test_downgrade_0011_reverts_density_bounds(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    """Downgrade to 0010_llm_config reverts d_min to 0.15 and d_max to 0.40."""
    migrated_engine.dispose()
    command.downgrade(alembic_config(), "0010_llm_config")
    config = _config(isolated_settings)
    assert config["d_min"] == 0.15
    assert config["d_max"] == 0.40
    # Earlier keys survive unchanged
    assert config["llm_model_id"] == "mlx-community/Llama-3.2-1B-Instruct-4bit"
    assert config["markov_beta"] == 10.0
    assert config["control_word_pool"] == 5000
    assert config["practice_days"] == 10
    assert config["assignment_seed"] == 20261021
