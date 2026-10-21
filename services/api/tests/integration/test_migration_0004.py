"""Migration 0004 creates the four M2 tables (constraints, indexes) and its downgrade drops only
them, leaving 0001-0003's tables (T2.1)."""

import sqlite3
from contextlib import closing
from pathlib import Path

from alembic import command
from sqlalchemy import Engine

from typist.migrations import alembic_config

NEW_TABLES = {"bigram_assignment", "drills", "generation_jobs", "generation_attempts"}


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


def test_0004_creates_the_four_m2_tables_with_constraints_and_indexes(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    assert _tables(isolated_settings) >= NEW_TABLES
    sql = _schema_sql(isolated_settings)
    assert "CONSTRAINT pk_bigram_assignment PRIMARY KEY (participant_id, bigram)" in sql
    assert "ix_drills_participant_id_arm_status" in sql
    assert "ix_generation_jobs_status_created_at" in sql
    assert "ix_generation_attempts_job_id" in sql
    assert (
        "CONSTRAINT ck_bigram_assignment_set_label CHECK (set_label IN ('A', 'B', 'C', 'D'))"
    ) in sql
    assert "CONSTRAINT ck_drills_status CHECK (status IN ('ready', 'used', 'retired'))" in sql
    assert (
        "CONSTRAINT ck_generation_jobs_status CHECK "
        "(status IN ('pending', 'running', 'done', 'failed'))"
    ) in sql
    assert "CONSTRAINT ck_generation_jobs_requested CHECK (requested >= 1)" in sql


def test_downgrade_0004_drops_only_the_four_m2_tables(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    migrated_engine.dispose()
    command.downgrade(alembic_config(), "0003_bigram_stats")
    tables = _tables(isolated_settings)
    assert tables.isdisjoint(NEW_TABLES)
    assert {
        "bigram_stats",
        "sessions",
        "session_blocks",
        "participants",
        "keystroke_events",
    } <= tables
