"""persist_baseline: created, unchanged, differ, replace and the freeze refusal (T1.8 owner 7)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from typist.models import Participant, SessionBlock, TextPassage
from typist.models import Session as TypingSession
from typist.services.test_composer import (
    BaselinePassagesInUseError,
    BaselinePersistResult,
    BaselineTextsDifferError,
    persist_baseline,
)

STARTED_AT = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)


def _passages(*texts: str) -> list[TextPassage]:
    return [
        TextPassage(
            kind="baseline",
            form="A",
            part=i,
            participant_id=None,
            text=text,
            bigram_counts={},
        )
        for i, text in enumerate(texts)
    ]


def _shared_a(session: Session) -> list[TextPassage]:
    return list(
        session.exec(
            select(TextPassage)
            .where(
                col(TextPassage.kind) == "baseline",
                col(TextPassage.form) == "A",
                col(TextPassage.participant_id).is_(None),
            )
            .order_by(col(TextPassage.part))
        ).all()
    )


def test_persist_creates_when_absent(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        result = persist_baseline(session, _passages("ab cd", "ef gh"))
    assert result == BaselinePersistResult(status="created", parts=2)
    with Session(migrated_engine) as session:
        assert [p.text for p in _shared_a(session)] == ["ab cd", "ef gh"]


def test_persist_is_unchanged_on_identical_texts(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        persist_baseline(session, _passages("ab cd", "ef gh"))
    with Session(migrated_engine) as session:
        result = persist_baseline(session, _passages("ab cd", "ef gh"))
        assert result == BaselinePersistResult(status="unchanged", parts=2)


def test_persist_raises_on_difference_without_replace(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        persist_baseline(session, _passages("ab cd", "ef gh"))
    with Session(migrated_engine) as session, pytest.raises(BaselineTextsDifferError):
        persist_baseline(session, _passages("zz zz", "yy yy"))
    with Session(migrated_engine) as session:
        assert [p.text for p in _shared_a(session)] == ["ab cd", "ef gh"]


def test_persist_replaces_when_requested_and_not_referenced(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        persist_baseline(session, _passages("ab cd", "ef gh"))
    with Session(migrated_engine) as session:
        result = persist_baseline(session, _passages("zz zz", "yy yy"), replace=True)
        assert result == BaselinePersistResult(status="replaced", parts=2)
    with Session(migrated_engine) as session:
        assert [p.text for p in _shared_a(session)] == ["zz zz", "yy yy"]


def test_persist_refuses_to_replace_a_referenced_passage(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        persist_baseline(session, _passages("ab cd", "ef gh"))
    with Session(migrated_engine) as session:
        passage = _shared_a(session)[0]
        participant = Participant(alias="p01")
        session.add(participant)
        session.flush()
        typing_session = TypingSession(
            participant_id=participant.id,
            phase="baseline",
            day_index=1,
            client_info={},
            started_at=STARTED_AT,
        )
        session.add(typing_session)
        session.flush()
        session.add(
            SessionBlock(
                session_id=typing_session.id,
                block_index=0,
                arm="test",
                passage_id=passage.id,
                target_text=passage.text,
            )
        )
        session.commit()
    with Session(migrated_engine) as session, pytest.raises(BaselinePassagesInUseError):
        persist_baseline(session, _passages("zz zz", "yy yy"), replace=True)
    with Session(migrated_engine) as session:
        assert [p.text for p in _shared_a(session)] == ["ab cd", "ef gh"]
