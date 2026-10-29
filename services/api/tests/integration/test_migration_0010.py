"""Migration 0010 seeds the 6 LLM generator keys; downgrade removes only them (T3.2)."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from alembic import command
from sqlalchemy import Engine

from typist.migrations import alembic_config

NEW_KEYS: dict[str, object] = {
    "llm_model_id": "mlx-community/Llama-3.2-1B-Instruct-4bit",
    "llm_model_revision": "08231374eeacb049a0eade7922910865b8fce912",
    "llm_prompt_version": "v1",
    "llm_temperature": 0.8,
    "llm_top_p": 0.9,
    "llm_max_tokens": 160,
}


def _config(db_path: Path) -> dict[str, object]:
    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute("SELECT key, value FROM experiment_config").fetchall()
    return {key: json.loads(value) for key, value in rows}


def test_0010_seeds_the_llm_config_keys(isolated_settings: Path, migrated_engine: Engine) -> None:
    config = _config(isolated_settings)
    for key, value in NEW_KEYS.items():
        assert config[key] == value
    with closing(sqlite3.connect(isolated_settings)) as connection:
        for key in NEW_KEYS:
            row = connection.execute(
                "SELECT frozen_at FROM experiment_config WHERE key = ?", (key,)
            ).fetchone()
            assert row is not None
            assert row[0] == "2026-10-29 00:00:00"


def test_downgrade_0010_removes_only_the_llm_config_keys(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    migrated_engine.dispose()
    command.downgrade(alembic_config(), "0009_markov_config")
    config = _config(isolated_settings)
    assert all(key not in config for key in NEW_KEYS)
    assert config["markov_beta"] == 10.0
    assert config["control_word_pool"] == 5000
    assert config["baseline_min_occurrences"] == 15
    assert config["assignment_seed"] == 20261021
    assert config["retest_min_occurrences"] == 40
