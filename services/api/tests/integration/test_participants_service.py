"""delete_participant: explicit child-to-parent deletion (T1.1 owner answer 10)."""

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from typist.models import KeystrokeEvent, Participant, SessionBlock, TextPassage
from typist.models import Session as TypingSession
from typist.services.participants import (
    ParticipantDeletion,
    ParticipantNotFoundError,
    delete_participant,
)

STARTED_AT = datetime(2026, 9, 29, 10, 0, tzinfo=UTC)
COUNT_QUERIES = (
    "SELECT count(*) FROM participants",
    "SELECT count(*) FROM text_passages",
    "SELECT count(*) FROM sessions",
    "SELECT count(*) FROM session_blocks",
    "SELECT count(*) FROM keystroke_events",
)


def _event(block_id: str, seq: int) -> KeystrokeEvent:
    return KeystrokeEvent(
        block_id=block_id,
        seq=seq,
        key="a",
        code="KeyA",
        t_down_ms=100.0 * (seq + 1),
        target_index=seq,
        expected_char="a",
        outcome="correct",
        first_attempt=True,
        handler_ms=0.1,
        dispatch_lag_ms=0.5,
    )


def _counts(db_path: Path) -> list[int]:
    with closing(sqlite3.connect(db_path)) as connection:
        return [connection.execute(query).fetchone()[0] for query in COUNT_QUERIES]


def test_delete_participant_removes_only_that_participants_rows(
    isolated_settings: Path, migrated_engine: Engine, seeded_ids: dict[str, str]
) -> None:
    p01 = seeded_ids["participant_id"]
    with Session(migrated_engine) as session:
        own_passage = TextPassage(
            kind="retest",
            form="B",
            part=0,
            participant_id=p01,
            text="a cat",
            bigram_counts={"ca": 1, "at": 1},
        )
        retest = TypingSession(
            participant_id=p01, phase="retest", day_index=1, client_info={}, started_at=STARTED_AT
        )
        session.add(own_passage)
        session.add(retest)
        session.flush()
        retest_block = SessionBlock(
            session_id=retest.id,
            block_index=0,
            arm="test",
            passage_id=own_passage.id,
            target_text="a cat",
        )
        session.add(retest_block)
        session.flush()
        session.add(_event(retest_block.id, 0))
        session.add(_event(retest_block.id, 1))
        other = Participant(alias="p02")
        session.add(other)
        session.flush()
        other_session = TypingSession(
            participant_id=other.id,
            phase="baseline",
            day_index=1,
            client_info={},
            started_at=STARTED_AT,
        )
        session.add(other_session)
        session.flush()
        other_block = SessionBlock(
            session_id=other_session.id,
            block_index=0,
            arm="test",
            passage_id=seeded_ids["passage_id"],
            target_text="the cat",
        )
        session.add(other_block)
        session.flush()
        session.add(_event(other_block.id, 0))
        other_id = other.id
        session.commit()

    with Session(migrated_engine) as session:
        deletion = delete_participant(session, p01)

    assert deletion == ParticipantDeletion(
        keystroke_events=3, session_blocks=2, sessions=2, text_passages=1, participants=1
    )
    with closing(sqlite3.connect(isolated_settings)) as connection:
        assert connection.execute("SELECT id FROM participants").fetchall() == [(other_id,)]
        assert connection.execute("SELECT id FROM text_passages").fetchall() == [
            (seeded_ids["passage_id"],)
        ]
        assert connection.execute("SELECT participant_id FROM sessions").fetchall() == [(other_id,)]
        assert connection.execute("SELECT count(*) FROM session_blocks").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM keystroke_events").fetchone()[0] == 1
        connection.execute("PRAGMA foreign_keys=ON")
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_delete_participant_without_sessions(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        participant = Participant(alias="p03")
        participant_id = participant.id
        session.add(participant)
        session.commit()
    with Session(migrated_engine) as session:
        deletion = delete_participant(session, participant_id)
    assert deletion == ParticipantDeletion(
        keystroke_events=0, session_blocks=0, sessions=0, text_passages=0, participants=1
    )


@pytest.mark.usefixtures("seeded_ids")
def test_delete_unknown_participant_raises_and_deletes_nothing(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    before = _counts(isolated_settings)
    with Session(migrated_engine) as session, pytest.raises(ParticipantNotFoundError):
        delete_participant(session, "no-such-id")
    assert _counts(isolated_settings) == before == [1, 1, 1, 1, 1]
