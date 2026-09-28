"""SQLite engine: pragmas on every connection, parent directory creation, the database check."""

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from typist.db import check_database, create_db_engine, get_session


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
