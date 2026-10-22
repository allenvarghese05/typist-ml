"""Migration 0006 seeds the six validator config keys; its downgrade removes them, leaving
0001-0005 intact (T2.3)."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from alembic import command
from sqlalchemy import Engine

from typist.migrations import alembic_config

NEW_KEYS = {
    "drill_length_chars": 300,
    "drill_min_length_chars": 270,
    "drill_min_coverage": 3,
    "drill_max_word_repeats": 3,
    "drill_max_bigram_run": 3,
    "drill_min_real_word_ratio": 0.8,
}


def _config(db_path: Path) -> dict[str, object]:
    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute("SELECT key, value FROM experiment_config").fetchall()
    return {key: json.loads(value) for key, value in rows}


def test_0006_seeds_the_six_validator_keys(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    config = _config(isolated_settings)
    for key, value in NEW_KEYS.items():
        assert config[key] == value


def test_downgrade_0006_removes_only_the_six_keys(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    migrated_engine.dispose()
    command.downgrade(alembic_config(), "0005_assignment_config")
    config = _config(isolated_settings)
    assert all(key not in config for key in NEW_KEYS)
    # Earlier keys survive.
    assert config["practice_days"] == 10
    assert config["d_min"] == 0.15
    assert config["assignment_seed"] == 20261021
