"""Integration test for the full end-to-end Typist-ML experiment loop (design doc 16; T2.10).

Milestone 2 capstone: A test participant goes enrolled -> baseline -> assigned -> practice ->
retest -> done end to end with scripted keystrokes in 2-set mode. Never used as empirical evidence.
"""

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from typist.api.routers.admin import get_word_index
from typist.config import get_settings
from typist.corpus.build import build_corpus
from typist.corpus.word_index import WordIndex
from typist.main import create_app
from typist.models import BigramAssignment, Drill, Participant
from typist.models import Session as TypingSession
from typist.services.pipeline_sim import run_pipeline_simulation


def test_full_pipeline_end_to_end_in_2_set_mode(
    migrated_engine: Engine, isolated_settings: Path, tmp_path: Path
) -> None:
    # 1. Hermetic corpus build
    corpus_dir = tmp_path / "corpus"
    build_corpus(corpus_dir, word_count=5000, tracked_count=50)
    index = WordIndex.load(corpus_dir)

    # 2. Setup TestClient with index override
    app = create_app(get_settings())
    app.dependency_overrides[get_word_index] = lambda: index
    client = TestClient(app)

    # 3. Execute the full pipeline simulation
    result = run_pipeline_simulation(
        client,
        migrated_engine,
        isolated_settings,
        index,
        participant_alias="pipeline-alice",
        practice_days=2,
        error_rate=0.04,
        seed=12345,
    )

    # 4. Verify summary assertions
    assert result.status == "done"
    assert result.baseline_sessions == 2
    assert result.practice_sessions == 2
    assert result.retest_sessions == 2
    assert result.checks_passed is True
    assert result.recomputed_sessions == 6

    # 5. Database state verification
    with Session(migrated_engine) as session:
        # Participant is done
        p = session.get(Participant, result.participant_id)
        assert p is not None and p.status == "done"

        # Bigram assignments are frozen in 2-set mode
        assignments = session.exec(
            select(BigramAssignment).where(col(BigramAssignment.participant_id) == p.id)
        ).all()
        assert len(assignments) > 0
        assert set(a.set_label for a in assignments) == {"A", "B"}
        assert set(a.arm for a in assignments) == {"control", "heuristic"}
        for a in assignments:
            assert a.frozen_at is not None

        # Practice drills were consumed and marked used
        used_drills = session.exec(
            select(Drill).where(col(Drill.participant_id) == p.id, col(Drill.status) == "used")
        ).all()
        assert len(used_drills) >= 4  # At least 2 practice days * 2 drills
        for drill in used_drills:
            assert drill.used_in_block_id is not None

        # All 6 sessions completed
        sessions = session.exec(
            select(TypingSession).where(col(TypingSession.participant_id) == p.id)
        ).all()
        assert len(sessions) == 6
        assert all(s.status == "completed" for s in sessions)
