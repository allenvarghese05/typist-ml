"""Migration 0003 creates bigram_stats (unique, index, checks) and its downgrade drops it (T1.9)."""

import sqlite3
from contextlib import closing
from pathlib import Path

from alembic import command
from sqlalchemy import Engine

from typist.migrations import alembic_config


def _tables(db_path: Path) -> set[str]:
    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    return {row[0] for row in rows}


def _schema_sql(db_path: Path) -> str:
    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL").fetchall()
    return "\n".join(row[0] for row in rows)


def test_0003_creates_bigram_stats_with_unique_index_and_checks(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    assert "bigram_stats" in _tables(isolated_settings)
    sql = _schema_sql(isolated_settings)
    assert "uq_bigram_stats_session_id_bigram" in sql
    assert "ix_bigram_stats_participant_id_bigram" in sql
    assert "CONSTRAINT ck_bigram_stats_bigram CHECK (length(bigram) = 2)" in sql
    assert "CONSTRAINT ck_bigram_stats_attempts CHECK (attempts >= 0)" in sql
    assert "CONSTRAINT ck_bigram_stats_errors CHECK (errors >= 0)" in sql
    assert "CONSTRAINT ck_bigram_stats_iki_n CHECK (iki_n >= 0)" in sql


def test_downgrade_0003_drops_only_bigram_stats(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    migrated_engine.dispose()
    command.downgrade(alembic_config(), "0002_baseline_config")
    tables = _tables(isolated_settings)
    assert "bigram_stats" not in tables
    assert {"sessions", "participants", "keystroke_events"} <= tables
