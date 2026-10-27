"""Integration tests for participant lifecycle service functions (T2.8)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from typist.models import Participant
from typist.services.participants import (
    AliasAlreadyExistsError,
    ParticipantNotFoundError,
    ParticipantStatusConflictError,
    create_participant,
    get_participant,
    list_participants,
    record_consent,
    withdraw_participant,
)

T0 = datetime(2026, 10, 27, 10, 0, 0, tzinfo=UTC)


def test_create_and_list_participants(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        p1 = create_participant(session, alias="user_one", keyboard_label="ISO-UK")
        assert p1.status == "enrolled"
        assert p1.is_builder is False
        assert p1.is_blinded is True
        assert p1.keyboard_label == "ISO-UK"
        assert p1.consent_at is None

        p2 = create_participant(session, alias="builder_user", is_builder=True)
        assert p2.is_builder is True
        assert p2.is_blinded is False

        assert get_participant(session, p1.id).alias == "user_one"

        all_p = list_participants(session)
        assert len(all_p) >= 2
        aliases = [p.alias for p in all_p]
        assert "user_one" in aliases
        assert "builder_user" in aliases


def test_create_duplicate_alias_raises_conflict(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        create_participant(session, alias="dup_user")
        with pytest.raises(AliasAlreadyExistsError, match="dup_user"):
            create_participant(session, alias="dup_user")


def test_record_consent_lifecycle(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        p = create_participant(session, alias="consent_user")
        consented = record_consent(session, p.id, keyboard_label="ANSI", now=T0)
        assert consented.status == "baseline"
        assert consented.consent_at == T0
        assert consented.keyboard_label == "ANSI"

        with pytest.raises(ParticipantStatusConflictError, match="must be 'enrolled'"):
            record_consent(session, p.id, now=T0)

    with Session(migrated_engine) as session, pytest.raises(ParticipantNotFoundError):
        record_consent(session, "missing-pid")


def test_withdraw_participant_lifecycle(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        p = create_participant(session, alias="withdrawn_user")
        withdrawn = withdraw_participant(session, p.id)
        assert withdrawn.status == "withdrawn"

        with pytest.raises(ParticipantStatusConflictError, match="must be active"):
            withdraw_participant(session, p.id)

        p_done = Participant(id="p-done", alias="done_user", status="done")
        session.add(p_done)
        session.commit()

        with pytest.raises(ParticipantStatusConflictError, match="must be active"):
            withdraw_participant(session, "p-done")
