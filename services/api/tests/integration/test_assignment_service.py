"""assignment service end to end: 16 frozen rows, seed determinism, the freeze trigger, the
precondition errors, and that delete_participant still works (T2.2)."""

import random
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select, text

from typist.corpus.word_index import WordIndex
from typist.models import BigramAssignment, KeystrokeEvent, Participant, SessionBlock
from typist.models import Session as TypingSession
from typist.services.assignment import (
    AlreadyAssignedError,
    BaselineIncompleteError,
    InvalidParticipantStatusError,
    assign_participant,
)
from typist.services.participants import delete_participant
from typist.services.session_stats import complete_session

NOW = datetime(2026, 10, 21, 12, 0, 0, tzinfo=UTC)
STARTED_AT = datetime(2026, 10, 20, 9, 0, 0, tzinfo=UTC)
SEED_A = 20261021
SEED_B = 99
PID = "p-assign-01"

# Sixteen distinct two-letter tracked bigrams and their session-0 error counts (0..15), so every
# smoothed rate is distinct and the rank order is fixed (rank 1 = most errors = "ro").
WORDS = (
    "th",
    "he",
    "in",
    "er",
    "an",
    "re",
    "nd",
    "at",
    "on",
    "nt",
    "ha",
    "es",
    "st",
    "en",
    "ed",
    "ro",
)
ERRORS = {word: errors for word, errors in zip(WORDS, range(16), strict=True)}
REPEATS = 15


def _index() -> WordIndex:
    return WordIndex(
        words=WORDS,
        frequencies={word: 1.0 for word in WORDS},
        tracked_bigrams=WORDS,
        by_bigram={word: (word,) for word in WORDS},
    )


def _fabricate_block_rows(block_id: str, session_index: int) -> tuple[str, list[KeystrokeEvent]]:
    """Build target_text and keystroke rows for one baseline block (see the module's seeding note)."""
    tokens: list[str] = []
    for word in WORDS:
        tokens.extend([word] * REPEATS)
    target_text = " ".join(tokens)
    error_at: set[int] = set()
    if session_index == 0:
        offset = 0
        for word in WORDS:
            # Mark the second letter (target_index of the 'b' char) of the first ERRORS[word]
            # repeats of this word; each token is 3 chars wide ("xy ") in the joined text.
            for repeat in range(ERRORS[word]):
                token_start = offset + repeat * 3
                error_at.add(token_start + 1)
            offset += REPEATS * 3
    rows: list[KeystrokeEvent] = []
    for seq, char in enumerate(target_text):
        outcome = "error" if seq in error_at else "correct"
        rows.append(
            KeystrokeEvent(
                block_id=block_id,
                seq=seq,
                key=char,
                code=f"Key{char.upper()}" if char != " " else "Space",
                t_down_ms=float(seq) * 100.0,
                target_index=seq,
                expected_char=char,
                outcome=outcome,
                first_attempt=True,
                handler_ms=0.1,
                dispatch_lag_ms=0.1,
            )
        )
    return target_text, rows


def _seed_baseline(session: Session, participant_id: str, *, parts: int = 2) -> None:
    """Create a participant and `parts` completed baseline sessions with derived bigram_stats."""
    session.add(Participant(id=participant_id, alias=participant_id, status="baseline"))
    session.flush()
    for part in range(parts):
        typing_session = TypingSession(
            participant_id=participant_id,
            phase="baseline",
            day_index=part + 1,
            client_info={"source": "test"},
            started_at=STARTED_AT,
        )
        session.add(typing_session)
        session.flush()
        block = SessionBlock(
            session_id=typing_session.id,
            block_index=part,
            arm="test",
            target_text="",
        )
        session.add(block)
        session.flush()
        target_text, rows = _fabricate_block_rows(block.id, part)
        block.target_text = target_text
        session.add(block)
        session.add_all(rows)
        session.flush()
        complete_session(session, typing_session.id, NOW)


def _rows(session: Session, participant_id: str) -> list[BigramAssignment]:
    return list(
        session.exec(
            select(BigramAssignment)
            .where(col(BigramAssignment.participant_id) == participant_id)
            .order_by(col(BigramAssignment.baseline_rank))
        ).all()
    )


def _mapping(rows: list[BigramAssignment]) -> dict[str, str]:
    return {row.set_label: row.arm for row in rows}


def test_assign_produces_sixteen_frozen_rows_with_the_seeded_arm_map(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed_baseline(session, PID)
        session.commit()
        result = assign_participant(
            session, PID, rng=random.Random(f"{SEED_A}:{PID}"), now=NOW, index=_index()
        )
    assert len(result) == 16
    with Session(migrated_engine) as session:
        rows = _rows(session, PID)
        p = session.get(Participant, PID)
        assert p is not None and p.status == "assigned"
    assert len(rows) == 16
    assert all(row.frozen_at is not None for row in rows)
    assert {row.set_label for row in rows} == {"A", "B", "C", "D"}
    assert sorted(row.baseline_rank for row in rows) == list(range(1, 17))
    assert all(row.baseline_attempts == 30 for row in rows)
    # Seed 20261021 shuffles (control,heuristic,markov,llm) -> [markov,heuristic,llm,control].
    assert _mapping(rows) == {"A": "markov", "B": "heuristic", "C": "llm", "D": "control"}
    # rank 1 is "ro" (15 errors); snake set 0 = A; its arm is markov.
    rank1 = next(row for row in rows if row.baseline_rank == 1)
    assert rank1.bigram == "ro"
    assert rank1.baseline_errors == 15
    assert rank1.set_label == "A"
    assert rank1.arm == "markov"


def test_same_seed_gives_identical_rows_on_a_fresh_database(
    migrated_engine: Engine, isolated_settings, tmp_path, monkeypatch
) -> None:
    # The determinism acceptance: re-derive the whole map on a second, independent database.
    def run(engine: Engine) -> list[tuple]:
        with Session(engine) as session:
            _seed_baseline(session, PID)
            session.commit()
            assign_participant(
                session, PID, rng=random.Random(f"{SEED_A}:{PID}"), now=NOW, index=_index()
            )
            return [
                (
                    r.bigram,
                    r.set_label,
                    r.arm,
                    r.baseline_rank,
                    r.weakness_score,
                    r.baseline_attempts,
                    r.baseline_errors,
                )
                for r in _rows(session, PID)
            ]

    first = run(migrated_engine)
    # A second fresh migrated database.
    from typist.db import create_db_engine
    from typist.migrations import upgrade_to_head

    monkeypatch.setenv("TYPIST_DB_PATH", str(tmp_path / "second.db"))
    from typist.config import get_settings

    get_settings.cache_clear()
    upgrade_to_head()
    second_engine = create_db_engine(tmp_path / "second.db")
    try:
        second = run(second_engine)
    finally:
        second_engine.dispose()
    assert first == second


def test_different_seed_changes_the_arm_mapping(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        _seed_baseline(session, PID)
        session.commit()
        assign_participant(
            session, PID, rng=random.Random(f"{SEED_B}:{PID}"), now=NOW, index=_index()
        )
        mapping = _mapping(_rows(session, PID))
    # Seed 99 shuffles -> [llm,markov,control,heuristic], differing from seed 20261021's map.
    assert mapping == {"A": "llm", "B": "markov", "C": "control", "D": "heuristic"}
    assert mapping != {"A": "markov", "B": "heuristic", "C": "llm", "D": "control"}


def test_reassign_raises_already_assigned(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        _seed_baseline(session, PID)
        session.commit()
        assign_participant(
            session, PID, rng=random.Random(f"{SEED_A}:{PID}"), now=NOW, index=_index()
        )
        with pytest.raises(AlreadyAssignedError):
            assign_participant(
                session, PID, rng=random.Random(f"{SEED_A}:{PID}"), now=NOW, index=_index()
            )


def test_incomplete_baseline_raises(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        _seed_baseline(session, PID, parts=1)
        session.commit()
        with pytest.raises(BaselineIncompleteError):
            assign_participant(
                session, PID, rng=random.Random(f"{SEED_A}:{PID}"), now=NOW, index=_index()
            )


def test_update_of_a_frozen_row_is_rejected_by_the_trigger(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        _seed_baseline(session, PID)
        session.commit()
        assign_participant(
            session, PID, rng=random.Random(f"{SEED_A}:{PID}"), now=NOW, index=_index()
        )
    with Session(migrated_engine) as session, pytest.raises(IntegrityError):
        session.execute(
            text("UPDATE bigram_assignment SET arm = 'control' WHERE participant_id = :pid"),
            params={"pid": PID},
        )
        session.commit()
    with Session(migrated_engine) as session:
        # The row is unchanged: set A is still mapped to markov.
        assert _mapping(_rows(session, PID))["A"] == "markov"


def test_delete_participant_removes_frozen_assignment_rows(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        _seed_baseline(session, PID)
        session.commit()
        assign_participant(
            session, PID, rng=random.Random(f"{SEED_A}:{PID}"), now=NOW, index=_index()
        )
        deletion = delete_participant(session, PID)
    assert deletion.bigram_assignment == 16
    with Session(migrated_engine) as session:
        assert _rows(session, PID) == []


def test_assign_fails_if_status_not_baseline(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        _seed_baseline(session, "p-enrolled")
        p = session.get(Participant, "p-enrolled")
        assert p is not None
        p.status = "enrolled"
        session.add(p)
        session.commit()

        with pytest.raises(InvalidParticipantStatusError, match="must be 'baseline'"):
            assign_participant(
                session,
                "p-enrolled",
                rng=random.Random(f"{SEED_A}:p-enrolled"),
                now=NOW,
                index=_index(),
            )

