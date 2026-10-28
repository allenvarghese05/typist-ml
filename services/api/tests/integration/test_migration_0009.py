"""Migration 0009 seeds the markov_beta key; its downgrade removes only it (T3.1)."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from alembic import command
from sqlalchemy import Engine

from typist.migrations import alembic_config

NEW_KEYS: dict[str, object] = {
    "markov_beta": 10.0,
}


def _config(db_path: Path) -> dict[str, object]:
    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute("SELECT key, value FROM experiment_config").fetchall()
    return {key: json.loads(value) for key, value in rows}


def test_0009_seeds_the_markov_config_key(isolated_settings: Path, migrated_engine: Engine) -> None:
    config = _config(isolated_settings)
    for key, value in NEW_KEYS.items():
        assert config[key] == value
    with closing(sqlite3.connect(isolated_settings)) as connection:
        row = connection.execute(
            "SELECT frozen_at FROM experiment_config WHERE key = 'markov_beta'"
        ).fetchone()
        assert row is not None
        assert row[0] is None


def test_downgrade_0009_removes_only_the_markov_config_key(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    migrated_engine.dispose()
    command.downgrade(alembic_config(), "0008_retest_config")
    config = _config(isolated_settings)
    assert all(key not in config for key in NEW_KEYS)
    assert config["control_word_pool"] == 5000
    assert config["baseline_min_occurrences"] == 15
    assert config["assignment_seed"] == 20261021
    assert config["retest_min_occurrences"] == 40
