"""Migration 0007 seeds control_word_pool; its downgrade removes it, leaving 0001-0006 intact (T2.4)."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from alembic import command
from sqlalchemy import Engine

from typist.migrations import alembic_config

NEW_KEYS = {
    "control_word_pool": 5000,
}


def _config(db_path: Path) -> dict[str, object]:
    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute("SELECT key, value FROM experiment_config").fetchall()
    return {key: json.loads(value) for key, value in rows}


def test_0007_seeds_the_control_word_pool_key(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    config = _config(isolated_settings)
    for key, value in NEW_KEYS.items():
        assert config[key] == value


def test_downgrade_0007_removes_only_the_control_word_pool_key(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    migrated_engine.dispose()
    command.downgrade(alembic_config(), "0006_validator_config")
    config = _config(isolated_settings)
    assert all(key not in config for key in NEW_KEYS)
    # Earlier keys survive.
    assert config["drill_min_length_chars"] == 270
    assert config["d_min"] == 0.15
    assert config["assignment_seed"] == 20261021
