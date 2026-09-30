"""record_key_up: the one allowed keystroke update (T1.1 owner answer 6)."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from typist.models import KeystrokeEvent
from typist.services.keystrokes import (
    KeystrokeEventNotFoundError,
    KeyUpAlreadyRecordedError,
    record_key_up,
)

ROW_QUERY = (
    "SELECT t_up_ms, dwell_ms, t_down_ms, release_to_press_ms FROM keystroke_events WHERE seq = 1"
)


def _add_event_without_key_up(engine: Engine, block_id: str) -> None:
    with Session(engine) as session:
        session.add(
            KeystrokeEvent(
                block_id=block_id,
                seq=1,
                key="h",
                code="KeyH",
                t_down_ms=812.5,
                iki_ms=100.0,
                target_index=1,
                expected_char="h",
                outcome="correct",
                first_attempt=True,
                handler_ms=0.2,
                dispatch_lag_ms=1.0,
            )
        )
        session.commit()


def _row(db_path: Path) -> tuple[object, ...]:
    with closing(sqlite3.connect(db_path)) as connection:
        return tuple(connection.execute(ROW_QUERY).fetchone())


def test_record_key_up_sets_t_up_and_dwell(
    isolated_settings: Path, migrated_engine: Engine, seeded_ids: dict[str, str]
) -> None:
    _add_event_without_key_up(migrated_engine, seeded_ids["block_id"])
    with Session(migrated_engine) as session:
        event = record_key_up(session, seeded_ids["block_id"], 1, 900.25)
        assert (event.t_up_ms, event.dwell_ms) == (900.25, 87.75)
    assert _row(isolated_settings) == (900.25, 87.75, 812.5, None)


def test_second_key_up_is_rejected_and_the_row_is_unchanged(
    isolated_settings: Path, migrated_engine: Engine, seeded_ids: dict[str, str]
) -> None:
    _add_event_without_key_up(migrated_engine, seeded_ids["block_id"])
    with Session(migrated_engine) as session:
        record_key_up(session, seeded_ids["block_id"], 1, 900.25)
    with Session(migrated_engine) as session, pytest.raises(KeyUpAlreadyRecordedError):
        record_key_up(session, seeded_ids["block_id"], 1, 950.0)
    assert _row(isolated_settings) == (900.25, 87.75, 812.5, None)


def test_key_up_on_a_row_stored_with_t_up_is_rejected(
    migrated_engine: Engine, seeded_ids: dict[str, str]
) -> None:
    with Session(migrated_engine) as session, pytest.raises(KeyUpAlreadyRecordedError):
        record_key_up(session, seeded_ids["block_id"], 0, 950.0)


def test_key_up_for_a_missing_row_raises(
    migrated_engine: Engine, seeded_ids: dict[str, str]
) -> None:
    with Session(migrated_engine) as session, pytest.raises(KeystrokeEventNotFoundError):
        record_key_up(session, seeded_ids["block_id"], 99, 950.0)


def test_negative_dwell_is_stored_as_is(
    isolated_settings: Path, migrated_engine: Engine, seeded_ids: dict[str, str]
) -> None:
    _add_event_without_key_up(migrated_engine, seeded_ids["block_id"])
    with Session(migrated_engine) as session:
        record_key_up(session, seeded_ids["block_id"], 1, 800.0)
    assert _row(isolated_settings) == (800.0, -12.5, 812.5, None)
