"""SQLite engine: pragmas on every connection, parent directory creation, the database check."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from typist.db import (
    check_database,
    create_db_engine,
    get_session,
    unfreeze_config_for_testing,
    utc_now,
)


def test_pragmas_are_set_on_every_connection(tmp_path: Path) -> None:
    engine = create_db_engine(tmp_path / "pragmas.db")
    try:
        with engine.connect() as first, engine.connect() as second:
            assert first.connection.dbapi_connection is not second.connection.dbapi_connection
            for connection in (first, second):
                assert connection.execute(text("PRAGMA journal_mode")).scalar_one() == "wal"
                assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
                assert connection.execute(text("PRAGMA synchronous")).scalar_one() == 1
    finally:
        engine.dispose()


def test_foreign_keys_are_enforced(tmp_path: Path) -> None:
    engine = create_db_engine(tmp_path / "fk.db")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
            connection.execute(
                text(
                    "CREATE TABLE child (id INTEGER PRIMARY KEY, "
                    "parent_id INTEGER NOT NULL REFERENCES parent (id))"
                )
            )
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(text("INSERT INTO child (id, parent_id) VALUES (1, 42)"))
    finally:
        engine.dispose()


def test_create_db_engine_creates_missing_parent_directories(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "deeper" / "typist.db"
    engine = create_db_engine(db_path)
    try:
        assert db_path.parent.is_dir()
        assert not db_path.exists()
        assert check_database(engine)
        assert db_path.is_file()
    finally:
        engine.dispose()


def test_check_database_is_true_for_a_new_file(tmp_path: Path) -> None:
    engine = create_db_engine(tmp_path / "new.db")
    try:
        assert check_database(engine) is True
    finally:
        engine.dispose()


def test_check_database_is_false_when_the_path_is_a_directory(tmp_path: Path) -> None:
    directory = tmp_path / "not-a-file"
    directory.mkdir()
    engine = create_db_engine(directory)
    try:
        assert check_database(engine) is False
    finally:
        engine.dispose()


def test_get_session_yields_a_working_session(tmp_path: Path) -> None:
    engine = create_db_engine(tmp_path / "session.db")
    try:
        sessions = get_session(engine)
        session = next(sessions)
        assert session.connection().execute(text("SELECT 1")).scalar_one() == 1
        sessions.close()
    finally:
        engine.dispose()


def test_utc_now_is_timezone_aware_utc() -> None:
    before = datetime.now(UTC)
    now = utc_now()
    after = datetime.now(UTC)
    assert now.tzinfo is UTC
    assert before <= now <= after


def test_unfreeze_config_for_testing_drops_triggers_and_resets_frozen_at(tmp_path: Path) -> None:
    engine = create_db_engine(tmp_path / "test_unfreeze.db")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE experiment_config (key TEXT PRIMARY KEY, value TEXT, frozen_at TEXT)"
                )
            )
            connection.execute(
                text(
                    "CREATE TRIGGER trg_experiment_config_frozen_update "
                    "BEFORE UPDATE ON experiment_config "
                    "WHEN OLD.frozen_at IS NOT NULL "
                    "BEGIN SELECT RAISE(ABORT, 'experiment_config keys are frozen'); END"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO experiment_config (key, value, frozen_at) "
                    "VALUES ('k1', '\"v1\"', '2026-10-29 00:00:00')"
                )
            )

        # Unfreezing via Engine drops trigger and clears frozen_at
        unfreeze_config_for_testing(engine)
        with engine.begin() as connection:
            row = connection.execute(
                text("SELECT frozen_at FROM experiment_config WHERE key = 'k1'")
            ).fetchone()
            assert row is not None
            assert row[0] is None
            # Updating now succeeds without trigger error
            connection.execute(
                text("UPDATE experiment_config SET value = '\"v2\"' WHERE key = 'k1'")
            )
            val = connection.execute(
                text("SELECT value FROM experiment_config WHERE key = 'k1'")
            ).scalar_one()
            assert val == '"v2"'

        # Re-freeze and test unfreezing via Session
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE experiment_config SET frozen_at = '2026-10-29 00:00:00' WHERE key = 'k1'"
                )
            )
        with Session(engine) as session:
            unfreeze_config_for_testing(session)
            row_sess = session.execute(
                text("SELECT frozen_at FROM experiment_config WHERE key = 'k1'")
            ).fetchone()
            assert row_sess is not None
            assert row_sess[0] is None
    finally:
        engine.dispose()
