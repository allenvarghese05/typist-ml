"""Unit tests for overview_report service and aggregations (T4.2)."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlmodel import Session

from typist.db import create_db_engine
from typist.migrations import upgrade_to_head
from typist.models import Drill, GenerationAttempt, GenerationJob, Participant
from typist.models import Session as TypingSession
from typist.services.analysis import overview_report
from typist.services.checks import participant_session_trend
from typist.services.participants import ParticipantNotFoundError

NOW = datetime(2026, 10, 20, 10, 0, 0, tzinfo=UTC)


@pytest.fixture
def migrated_engine(isolated_settings: Path) -> Iterator[Engine]:
    """Upgrade per-test db and yield engine."""
    upgrade_to_head()
    engine = create_db_engine(isolated_settings)
    try:
        yield engine
    finally:
        engine.dispose()


def test_overview_empty_db(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        overview = overview_report(session)
        assert overview.participants == []
        assert overview.generation.total_drills == 0
        assert overview.generation.total_attempts == 0
        assert len(overview.generation.arms) == 4
        # Overhead includes one pooled "all" row with 0 events
        assert len(overview.overhead) == 1
        assert overview.overhead[0].session_id == "all"
        assert overview.overhead[0].events == 0


def test_overview_with_drills_and_attempts(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        p1 = Participant(alias="user-1", status="done", is_builder=True, is_blinded=False)
        session.add(p1)
        session.flush()

        s1 = TypingSession(
            participant_id=p1.id,
            phase="baseline",
            day_index=1,
            status="completed",
            wpm=45.0,
            accuracy=0.97,
            client_info={},
            started_at=NOW,
            ended_at=NOW,
        )
        session.add(s1)
        session.flush()

        # Seed drills
        d_ctrl = Drill(
            participant_id=p1.id,
            arm="control",
            status="used",
            target_bigrams=[],
            text="quick brown fox",
            target_density=0.0,
            mean_word_len=4.5,
            real_word_ratio=1.0,
            generator_version="1.0",
            seed=1,
        )
        d_llm = Drill(
            participant_id=p1.id,
            arm="llm",
            status="ready",
            target_bigrams=["th"],
            text="the thing with teeth",
            target_density=0.25,
            mean_word_len=4.0,
            real_word_ratio=1.0,
            generator_version="1.0",
            seed=2,
        )
        session.add_all([d_ctrl, d_llm])
        session.flush()

        # Seed jobs and attempts
        job_llm = GenerationJob(
            participant_id=p1.id,
            arm="llm",
            requested=2,
            status="done",
        )
        session.add(job_llm)
        session.flush()

        att1 = GenerationAttempt(
            job_id=job_llm.id,
            drill_id=d_llm.id,
            raw_output="the thing with teeth",
            clean_text="the thing with teeth",
            density=0.25,
            accepted=True,
            reject_reasons=[],
            tokens_per_sec=28.5,
            gen_ms=450.0,
            peak_memory_mb=1280.0,
        )
        att2 = GenerationAttempt(
            job_id=job_llm.id,
            drill_id=None,
            raw_output="bad drill text",
            clean_text="bad drill text",
            density=0.05,
            accepted=False,
            reject_reasons=["low_density"],
            tokens_per_sec=31.5,
            gen_ms=350.0,
            peak_memory_mb=1320.0,
        )
        session.add_all([att1, att2])
        session.commit()

        overview = overview_report(session)
        assert len(overview.participants) == 1
        p_summary = overview.participants[0]
        assert p_summary.id == p1.id
        assert p_summary.alias == "user-1"
        assert p_summary.status == "done"
        assert p_summary.is_builder is True
        assert p_summary.completed_sessions == 1

        assert overview.generation.total_drills == 2
        assert overview.generation.total_attempts == 2

        arms_by_name = {a.arm: a for a in overview.generation.arms}
        assert "control" in arms_by_name
        assert arms_by_name["control"].drills_count == 1
        assert arms_by_name["control"].attempts_count == 0
        assert arms_by_name["control"].acceptance_rate == 1.0

        assert "llm" in arms_by_name
        llm_arm = arms_by_name["llm"]
        assert llm_arm.drills_count == 1
        assert llm_arm.attempts_count == 2
        assert llm_arm.acceptance_rate == 0.5
        assert llm_arm.attempts_per_drill == 2.0
        assert llm_arm.mean_target_density == 0.25
        assert llm_arm.mean_word_length == 4.0
        assert llm_arm.tokens_per_sec == 30.0  # mean of 28.5 and 31.5
        assert llm_arm.mean_gen_ms == 400.0  # mean of 450 and 350
        assert llm_arm.peak_memory_mb == 1320.0  # max of 1280 and 1320


def test_participant_session_trend_raises_not_found(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session, pytest.raises(ParticipantNotFoundError):
        participant_session_trend(session, "unknown-pid")
