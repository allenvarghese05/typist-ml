"""Migration 0002 seeds the six baseline keys and leaves 0001's keys untouched (T1.8 owner 2)."""

import sqlite3
from contextlib import closing
from pathlib import Path

from alembic import command
from sqlalchemy import Engine

from typist.migrations import alembic_config

BASELINE_KEYS = {
    "tracked_bigram_count",
    "baseline_min_occurrences",
    "baseline_parts",
    "baseline_part_chars",
    "corpus_seed",
    "corpus_word_count",
}
INITIAL_KEYS = {"practice_days", "block_chars", "d_min", "d_max", "arms_enabled"}


def _config(db_path: Path) -> dict[str, str]:
    with closing(sqlite3.connect(db_path)) as connection:
        return dict(connection.execute("SELECT key, value FROM experiment_config").fetchall())


def test_migration_0002_seeds_the_six_baseline_keys(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    rows = _config(isolated_settings)
    assert set(rows) >= BASELINE_KEYS
    assert set(rows) >= INITIAL_KEYS
    assert rows["tracked_bigram_count"] == "150"
    assert rows["baseline_min_occurrences"] == "15"
    assert rows["baseline_parts"] == "2"
    assert rows["baseline_part_chars"] == "2700"
    assert rows["corpus_seed"] == "20261019"
    assert rows["corpus_word_count"] == "20000"


def test_downgrade_0002_removes_only_the_baseline_keys(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    migrated_engine.dispose()
    command.downgrade(alembic_config(), "0001_initial_schema")
    remaining = set(_config(isolated_settings))
    assert remaining == INITIAL_KEYS
    assert remaining.isdisjoint(BASELINE_KEYS)
