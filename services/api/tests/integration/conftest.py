"""Fixtures for integration tests that need the migrated schema (T1.1).

The schema always comes from the Alembic migration (upgrade_to_head), never from
SQLModel.metadata.create_all, so tests see exactly the tables a real database has.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from typist.db import create_db_engine
from typist.migrations import upgrade_to_head
from typist.models import KeystrokeEvent, Participant, SessionBlock, TextPassage
from typist.models import Session as TypingSession

SEED_STARTED_AT = datetime(2026, 9, 29, 9, 0, 0, tzinfo=UTC)


@pytest.fixture
def migrated_engine(isolated_settings: Path) -> Iterator[Engine]:
    """Upgrade the per-test database to head, then yield an engine with the app's pragmas."""
    upgrade_to_head()
    engine = create_db_engine(isolated_settings)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def seeded_ids(migrated_engine: Engine) -> dict[str, str]:
    """Add one row to every table the migration leaves empty and return their ids.

    experiment_config already holds the migration's five rows. Added: participant "p01"; a shared
    baseline passage (form A, part 0, "the cat"); a baseline session (day 1) for p01; one test
    block (block_index 0) showing that passage; one keystroke (seq 0, "t", correct, t_up known).
    Keys: participant_id, passage_id, session_id, block_id.
    """
    with Session(migrated_engine) as session:
        participant = Participant(alias="p01")
        passage = TextPassage(
            kind="baseline",
            form="A",
            part=0,
            text="the cat",
            bigram_counts={"th": 1, "he": 1, "ca": 1, "at": 1},
        )
        session.add(participant)
        session.add(passage)
        session.flush()
        typing_session = TypingSession(
            participant_id=participant.id,
            phase="baseline",
            day_index=1,
            client_info={"user_agent": "pytest"},
            started_at=SEED_STARTED_AT,
        )
        session.add(typing_session)
        session.flush()
        block = SessionBlock(
            session_id=typing_session.id,
            block_index=0,
            arm="test",
            passage_id=passage.id,
            target_text="the cat",
        )
        session.add(block)
        session.flush()
        session.add(
            KeystrokeEvent(
                block_id=block.id,
                seq=0,
                key="t",
                code="KeyT",
                t_down_ms=812.4,
                t_up_ms=900.1,
                dwell_ms=87.7,
                target_index=0,
                expected_char="t",
                outcome="correct",
                first_attempt=True,
                handler_ms=0.2,
                dispatch_lag_ms=1.1,
            )
        )
        ids = {
            "participant_id": participant.id,
            "passage_id": passage.id,
            "session_id": typing_session.id,
            "block_id": block.id,
        }
        session.commit()
    return ids
