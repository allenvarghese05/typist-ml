"""Migration 0008 seeds the three retest composer keys; its downgrade removes only them (T2.7)."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from alembic import command
from sqlalchemy import Engine

from typist.migrations import alembic_config

NEW_KEYS: dict[str, object] = {
    "retest_min_occurrences": 40,
    "retest_parts": 2,
    "retest_part_chars": 2700,
}


def _config(db_path: Path) -> dict[str, object]:
    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute("SELECT key, value FROM experiment_config").fetchall()
    return {key: json.loads(value) for key, value in rows}


def test_0008_seeds_the_retest_config_keys(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    config = _config(isolated_settings)
    for key, value in NEW_KEYS.items():
        assert config[key] == value


def test_downgrade_0008_removes_only_the_retest_config_keys(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    migrated_engine.dispose()
    command.downgrade(alembic_config(), "0007_generator_config")
    config = _config(isolated_settings)
    assert all(key not in config for key in NEW_KEYS)
    assert config["control_word_pool"] == 5000
    assert config["baseline_min_occurrences"] == 15
    assert config["assignment_seed"] == 20261021
