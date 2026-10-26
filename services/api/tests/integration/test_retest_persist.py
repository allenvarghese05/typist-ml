"""persist_retest and compose_and_persist_retest: created, unchanged, differ, replace, per-participant
isolation, freeze refusal when referenced by SessionBlock, and precondition errors (T2.7).
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from typist.corpus.build import build_corpus
from typist.corpus.word_index import WordIndex
from typist.models import BigramAssignment, Participant, SessionBlock, TextPassage
from typist.models import Session as TypingSession
from typist.services.participants import ParticipantNotFoundError, delete_participant
from typist.services.session_planner import plan_session
from typist.services.test_composer import (
    BaselinePassagesNotFoundError,
    ParticipantNotAssignedError,
    RetestPassagesInUseError,
    RetestPersistResult,
    RetestTextsDifferError,
    compose_and_persist_retest,
    persist_baseline,
    persist_retest,
)

STARTED_AT = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)


def _retest_passages(participant_id: str, *texts: str) -> list[TextPassage]:
    return [
        TextPassage(
            kind="retest",
            form="B",
            part=i,
            participant_id=participant_id,
            text=text,
            bigram_counts={},
        )
        for i, text in enumerate(texts)
    ]


def _participant_b(session: Session, participant_id: str) -> list[TextPassage]:
    return list(
        session.exec(
            select(TextPassage)
            .where(
                col(TextPassage.kind) == "retest",
                col(TextPassage.form) == "B",
                col(TextPassage.participant_id) == participant_id,
            )
            .order_by(col(TextPassage.part))
        ).all()
    )


def _seed_participant_with_assignment(
    session: Session, participant_id: str, bigrams: tuple[str, ...]
) -> None:
    session.add(Participant(id=participant_id, alias=participant_id, status="retest"))
    session.flush()
    sets = ("A", "B", "C", "D")
    arms = ("control", "heuristic", "markov", "llm")
    for rank, bigram in enumerate(bigrams, start=1):
        idx = (rank - 1) % 4
        session.add(
            BigramAssignment(
                participant_id=participant_id,
                bigram=bigram,
                set_label=sets[idx],
                arm=arms[idx],
                baseline_rank=rank,
                weakness_score=0.1,
                baseline_attempts=20,
                baseline_errors=2,
                frozen_at=STARTED_AT,
            )
        )
    session.flush()


def test_persist_retest_creates_unchanged_differs_replaces_and_isolates_participants(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        session.add(Participant(id="p-01", alias="p-01"))
        session.add(Participant(id="p-02", alias="p-02"))
        session.commit()

    with Session(migrated_engine) as session:
        created = persist_retest(session, "p-01", _retest_passages("p-01", "ab cd", "ef gh"))
        assert created == RetestPersistResult(status="created", parts=2, participant_id="p-01")

    with Session(migrated_engine) as session:
        unchanged = persist_retest(session, "p-01", _retest_passages("p-01", "ab cd", "ef gh"))
        assert unchanged == RetestPersistResult(status="unchanged", parts=2, participant_id="p-01")

    with Session(migrated_engine) as session, pytest.raises(RetestTextsDifferError):
        persist_retest(session, "p-01", _retest_passages("p-01", "xx yy", "zz ww"))

    # Another participant's form B rows are completely independent.
    with Session(migrated_engine) as session:
        created_p2 = persist_retest(session, "p-02", _retest_passages("p-02", "mm nn", "oo pp"))
        assert created_p2 == RetestPersistResult(status="created", parts=2, participant_id="p-02")
        replaced_p1 = persist_retest(
            session, "p-01", _retest_passages("p-01", "xx yy", "zz ww"), replace=True
        )
        assert replaced_p1 == RetestPersistResult(status="replaced", parts=2, participant_id="p-01")
        assert [p.text for p in _participant_b(session, "p-01")] == ["xx yy", "zz ww"]
        assert [p.text for p in _participant_b(session, "p-02")] == ["mm nn", "oo pp"]


def test_persist_retest_refuses_to_replace_when_referenced_by_session_block(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        session.add(Participant(id="p-01", alias="p-01"))
        session.commit()
        persist_retest(session, "p-01", _retest_passages("p-01", "ab cd", "ef gh"))

    with Session(migrated_engine) as session:
        passage = _participant_b(session, "p-01")[0]
        typing_session = TypingSession(
            participant_id="p-01",
            phase="retest",
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

    with Session(migrated_engine) as session, pytest.raises(RetestPassagesInUseError):
        persist_retest(session, "p-01", _retest_passages("p-01", "xx yy", "zz ww"), replace=True)

    with Session(migrated_engine) as session:
        assert [p.text for p in _participant_b(session, "p-01")] == ["ab cd", "ef gh"]


def test_compose_and_persist_retest_integrates_with_session_planner_and_delete_participant(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    corpus_dir = tmp_path / "corpus"
    build_corpus(corpus_dir, word_count=5000, tracked_count=50)
    index = WordIndex.load(corpus_dir)

    with Session(migrated_engine) as session:
        # Unknown participant raises ParticipantNotFoundError.
        with pytest.raises(ParticipantNotFoundError):
            compose_and_persist_retest(session, "missing", index)

        session.add(Participant(id="p-unassigned", alias="p-unassigned"))
        session.commit()
        # Unassigned participant raises ParticipantNotAssignedError.
        with pytest.raises(ParticipantNotAssignedError):
            compose_and_persist_retest(session, "p-unassigned", index)

        _seed_participant_with_assignment(session, "p-retest", index.tracked_bigrams[:16])
        session.commit()
        # Missing form A passages raises BaselinePassagesNotFoundError.
        with pytest.raises(BaselinePassagesNotFoundError):
            compose_and_persist_retest(session, "p-retest", index)

        persist_baseline(
            session,
            [
                TextPassage(
                    kind="baseline",
                    form="A",
                    part=0,
                    participant_id=None,
                    text="the and for are",
                    bigram_counts={
                        "th": 1,
                        "he": 1,
                        "an": 1,
                        "nd": 1,
                        "fo": 1,
                        "or": 1,
                        "ar": 1,
                        "re": 1,
                    },
                ),
                TextPassage(
                    kind="baseline",
                    form="A",
                    part=1,
                    participant_id=None,
                    text="but not you all",
                    bigram_counts={
                        "bu": 1,
                        "ut": 1,
                        "no": 1,
                        "ot": 1,
                        "yo": 1,
                        "ou": 1,
                        "al": 1,
                        "ll": 1,
                    },
                ),
            ],
        )

        result = compose_and_persist_retest(session, "p-retest", index)
        assert result == RetestPersistResult(status="created", parts=2, participant_id="p-retest")

        # session_planner.plan_session for phase='retest' now finds part 0 for this participant.
        planned = plan_session(session, "p-retest", "retest", now=STARTED_AT)
        assert planned.phase == "retest"
        assert planned.day_index == 1
        assert len(planned.blocks) == 1
        assert planned.blocks[0].block_index == 0
        assert len(planned.blocks[0].target_text) >= 2700

        deletion = delete_participant(session, "p-retest")
        assert deletion.text_passages == 2
