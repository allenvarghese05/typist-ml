"""Model package: naming convention, ids, CHECK text (T1.1)."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect
from sqlmodel import SQLModel

from typist.models import ExperimentConfig, KeystrokeEvent, Participant, SessionBlock, TextPassage
from typist.models import Session as TypingSession
from typist.models.base import NAMING_CONVENTION, new_id, sql_in


def test_metadata_uses_the_naming_convention() -> None:
    assert SQLModel.metadata.naming_convention == NAMING_CONVENTION
    assert set(NAMING_CONVENTION) == {"ix", "uq", "ck", "fk", "pk"}


def test_new_id_returns_distinct_hyphenated_uuid4_strings() -> None:
    first, second = new_id(), new_id()
    assert first != second
    for value in (first, second):
        assert len(value) == 36
        assert str(uuid.UUID(value)) == value
        assert uuid.UUID(value).version == 4


def test_sql_in_quotes_each_value() -> None:
    assert sql_in("arm", ("test", "control")) == "arm IN ('test', 'control')"


def test_sql_in_rejects_a_single_quote() -> None:
    with pytest.raises(ValueError, match="single quote"):
        sql_in("arm", ("o'brien",))


SIX_TABLES = {
    "participants",
    "experiment_config",
    "text_passages",
    "sessions",
    "session_blocks",
    "keystroke_events",
}


def test_metadata_holds_exactly_the_six_tables() -> None:
    assert set(SQLModel.metadata.tables) == SIX_TABLES


def test_table_names_follow_section_8_1() -> None:
    # The mapped table's name (a plain str); Model.__tablename__ is typed as a declared_attr.
    assert inspect(Participant).tables[0].name == "participants"
    assert inspect(ExperimentConfig).tables[0].name == "experiment_config"
    assert inspect(TextPassage).tables[0].name == "text_passages"
    assert inspect(TypingSession).tables[0].name == "sessions"
    assert inspect(SessionBlock).tables[0].name == "session_blocks"
    assert inspect(KeystrokeEvent).tables[0].name == "keystroke_events"


def test_every_constraint_and_index_is_named() -> None:
    for table in SQLModel.metadata.tables.values():
        for constraint in table.constraints:
            assert constraint.name, f"unnamed constraint on {table.name}"
        for index in table.indexes:
            assert index.name, f"unnamed index on {table.name}"


def test_participant_defaults() -> None:
    participant = Participant(alias="p01")
    assert len(participant.id) == 36
    assert participant.status == "enrolled"
    assert participant.is_builder is False
    assert participant.is_blinded is True
    assert participant.keyboard_label is None
    assert participant.consent_at is None
    assert participant.created_at is None


def test_session_and_block_defaults() -> None:
    session = TypingSession(
        participant_id="p",
        phase="baseline",
        day_index=1,
        client_info={},
        started_at=datetime(2026, 9, 29, 9, 0, tzinfo=UTC),
    )
    assert session.status == "in_progress"
    assert (session.block_order, session.wpm, session.accuracy, session.ended_at) == (
        None,
        None,
        None,
        None,
    )
    block = SessionBlock(session_id=session.id, block_index=0, arm="test", target_text="ab")
    assert (block.passage_id, block.started_at, block.ended_at) == (None, None, None)


def test_passage_and_config_defaults() -> None:
    passage = TextPassage(kind="baseline", form="A", part=0, text="ab", bigram_counts={"ab": 1})
    assert passage.participant_id is None
    assert ExperimentConfig(key="d_min", value=0.15).frozen_at is None


def test_keystroke_event_defaults() -> None:
    event = KeystrokeEvent(
        block_id="b",
        seq=0,
        key="t",
        code="KeyT",
        t_down_ms=1.0,
        target_index=0,
        outcome="correct",
        handler_ms=0.1,
        dispatch_lag_ms=0.1,
    )
    assert event.id is None
    assert event.after_pause is False
    assert (event.t_up_ms, event.dwell_ms, event.iki_ms, event.release_to_press_ms) == (
        None,
        None,
        None,
        None,
    )
    assert (event.expected_char, event.first_attempt) == (None, None)
