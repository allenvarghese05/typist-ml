"""Database engine, session dependency and SQLite pragmas (design doc sections 5.2, 7 and 8)."""

import logging
import sqlite3
from collections.abc import Generator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

logger = logging.getLogger(__name__)

# Section 8. foreign_keys and synchronous reset on every new connection, so all three run on each.
SQLITE_PRAGMAS: tuple[str, ...] = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA foreign_keys=ON",
    "PRAGMA synchronous=NORMAL",
)


def _apply_sqlite_pragmas(dbapi_connection: sqlite3.Connection, _connection_record: object) -> None:
    """SQLAlchemy "connect" listener: run SQLITE_PRAGMAS on a new DBAPI connection."""
    cursor = dbapi_connection.cursor()
    try:
        for pragma in SQLITE_PRAGMAS:
            cursor.execute(pragma)
    finally:
        cursor.close()


def create_db_engine(db_path: Path) -> Engine:
    """Create an engine for the SQLite file at db_path.

    Creates the parent directory if it is missing (the file itself is created on first connect).
    Every pooled connection gets SQLITE_PRAGMAS. check_same_thread is off because FastAPI runs
    sync handlers in a thread pool. Does not open a connection.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _apply_sqlite_pragmas)
    return engine


def check_database(engine: Engine) -> bool:
    """Return True if a connection opens and `SELECT 1` runs; else log the error, return False.

    Needs no tables, so it works before any migration.
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except (SQLAlchemyError, sqlite3.Error):
        logger.warning("database check failed", exc_info=True)
        return False
    return True


def get_engine(request: Request) -> Engine:
    """FastAPI dependency: the engine that create_app stored on app.state."""
    engine: Engine = request.app.state.engine
    return engine


def get_session(
    engine: Annotated[Engine, Depends(get_engine)],
) -> Generator[Session, None, None]:
    """FastAPI dependency: one SQLModel session per request, closed when the request ends."""
    with Session(engine) as session:
        yield session
