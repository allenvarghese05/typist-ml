"""Unit tests for daily checks and pool status service (T2.9)."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from typist.db import create_db_engine
from typist.migrations import upgrade_to_head
from typist.models import (
    BigramAssignment,
    BigramStat,
    KeystrokeEvent,
    Participant,
    SessionBlock,
)
from typist.models import Session as TypingSession
from typist.services.checks import (
    get_all_pools_status,
    get_participant_pool_status,
    run_participant_checks,
)
from typist.services.participants import ParticipantNotFoundError


@pytest.fixture
def migrated_engine(isolated_settings: Path) -> Iterator[Engine]:
    """Upgrade per-test db and yield engine."""
    upgrade_to_head()
    engine = create_db_engine(isolated_settings)
    try:
        yield engine
    finally:
        engine.dispose()


def _create_participant(session: Session, pid: str = "p-1", alias: str = "pilot-1") -> Participant:
    p = Participant(id=pid, alias=alias, status="baseline")
    session.add(p)
    session.commit()
    return p


def test_run_checks_on_empty_participant(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        p = _create_participant(session)
        report = run_participant_checks(session, p.id)

        assert report.participant_id == p.id
        assert report.alias == p.alias
        assert report.passed is True
        assert report.checks.seq_gaps.passed is True
        assert report.checks.seq_gaps.count == 0
        assert report.checks.dwell_anomalies.passed is True
        assert report.checks.dwell_anomalies.negative_count == 0
        assert report.checks.dwell_anomalies.over_1000ms_count == 0
        assert report.checks.short_blocks.passed is True
        assert report.checks.short_blocks.count == 0
        assert report.checks.missing_keyups.passed is True
        assert report.checks.missing_keyups.missing_count == 0
        assert report.checks.in_progress_sessions.passed is True
        assert report.checks.in_progress_sessions.count == 0
        assert report.trend == []

        pool = get_participant_pool_status(session, p.id)
        assert pool.participant_id == p.id
        assert len(pool.arms) == 4
        for arm_st in pool.arms:
            assert arm_st.ready_count == 0
            assert arm_st.deficit == arm_st.target_count
            assert arm_st.is_ready is False

        all_pools = get_all_pools_status(session)
        assert len(all_pools) == 1

    with Session(migrated_engine) as session:
        with pytest.raises(ParticipantNotFoundError):
            run_participant_checks(session, "missing-p")
        with pytest.raises(ParticipantNotFoundError):
            get_participant_pool_status(session, "missing-p")


def test_run_checks_detects_sequence_gap(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        p = _create_participant(session)
        now = datetime.now(UTC)
        s = TypingSession(
            id="s-gap",
            participant_id=p.id,
            phase="baseline",
            day_index=1,
            status="completed",
            started_at=now,
            client_info={},
        )
        session.add(s)
        session.flush()

        b = SessionBlock(
            id="b-gap",
            session_id=s.id,
            block_index=0,
            arm="test",
            target_text="test",
        )
        session.add(b)
        session.flush()

        seqs = [0, 1, 2, 5]
        for seq in seqs:
            session.add(
                KeystrokeEvent(
                    block_id=b.id,
                    seq=seq,
                    key="a",
                    code="KeyA",
                    t_down_ms=100.0 * seq,
                    t_up_ms=100.0 * seq + 50.0,
                    dwell_ms=50.0,
                    target_index=seq,
                    expected_char="a",
                    outcome="correct",
                    first_attempt=True,
                    handler_ms=0.1,
                    dispatch_lag_ms=1.0,
                )
            )
        session.commit()

        report = run_participant_checks(session, p.id)
        assert report.passed is False
        assert report.checks.seq_gaps.passed is False
        assert report.checks.seq_gaps.count == 1
        assert len(report.checks.seq_gaps.details) == 1
        assert "gap between seq 2 and 5" in report.checks.seq_gaps.details[0]


def test_run_checks_detects_negative_dwell_and_stuck_key(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        p = _create_participant(session)
        now = datetime.now(UTC)
        s = TypingSession(
            id="s-dwell",
            participant_id=p.id,
            phase="baseline",
            day_index=1,
            status="completed",
            started_at=now,
            client_info={},
        )
        session.add(s)
        session.flush()

        b = SessionBlock(
            id="b-dwell",
            session_id=s.id,
            block_index=0,
            arm="test",
            target_text="ab",
        )
        session.add(b)
        session.flush()

        session.add(
            KeystrokeEvent(
                block_id=b.id,
                seq=0,
                key="a",
                code="KeyA",
                t_down_ms=100.0,
                t_up_ms=95.0,
                dwell_ms=-5.0,
                target_index=0,
                expected_char="a",
                outcome="correct",
                first_attempt=True,
                handler_ms=0.1,
                dispatch_lag_ms=1.0,
            )
        )
        session.add(
            KeystrokeEvent(
                block_id=b.id,
                seq=1,
                key="b",
                code="KeyB",
                t_down_ms=200.0,
                t_up_ms=1400.0,
                dwell_ms=1200.0,
                target_index=1,
                expected_char="b",
                outcome="correct",
                first_attempt=True,
                handler_ms=0.1,
                dispatch_lag_ms=1.0,
            )
        )
        session.commit()

        report = run_participant_checks(session, p.id)
        assert report.passed is False
        assert report.checks.dwell_anomalies.passed is False
        assert report.checks.dwell_anomalies.negative_count == 1
        assert report.checks.dwell_anomalies.over_1000ms_count == 1
        assert len(report.checks.dwell_anomalies.details) == 2


def test_run_checks_short_blocks(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        p = _create_participant(session)
        now = datetime.now(UTC)
        s = TypingSession(
            id="s-short",
            participant_id=p.id,
            phase="baseline",
            day_index=1,
            status="completed",
            started_at=now,
            client_info={},
        )
        session.add(s)
        session.flush()

        b = SessionBlock(
            id="b-short",
            session_id=s.id,
            block_index=0,
            arm="test",
            target_text="1234567890123456789012345",  # 25 chars
        )
        session.add(b)
        session.flush()

        for seq in range(10):  # only 10 events
            session.add(
                KeystrokeEvent(
                    block_id=b.id,
                    seq=seq,
                    key="x",
                    code="KeyX",
                    t_down_ms=10.0 * seq,
                    t_up_ms=10.0 * seq + 5.0,
                    dwell_ms=5.0,
                    target_index=seq,
                    expected_char="x",
                    outcome="correct",
                    first_attempt=True,
                    handler_ms=0.1,
                    dispatch_lag_ms=1.0,
                )
            )
        session.commit()

        report = run_participant_checks(session, p.id)
        assert report.passed is False
        assert report.checks.short_blocks.passed is False
        assert report.checks.short_blocks.count == 1
        assert "10 events < 25 target chars" in report.checks.short_blocks.details[0]


def test_run_checks_missing_keyups_threshold(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        p = _create_participant(session)
        now = datetime.now(UTC)
        s = TypingSession(
            id="s-keyups",
            participant_id=p.id,
            phase="baseline",
            day_index=1,
            status="completed",
            started_at=now,
            client_info={},
        )
        session.add(s)
        session.flush()

        b = SessionBlock(
            id="b-keyups",
            session_id=s.id,
            block_index=0,
            arm="test",
            target_text="a" * 100,
        )
        session.add(b)
        session.flush()

        # Seed 100 events, 1 missing t_up_ms (1% <= 5% -> PASS)
        for seq in range(100):
            session.add(
                KeystrokeEvent(
                    block_id=b.id,
                    seq=seq,
                    key="a",
                    code="KeyA",
                    t_down_ms=10.0 * seq,
                    t_up_ms=None if seq == 0 else 10.0 * seq + 5.0,
                    dwell_ms=None if seq == 0 else 5.0,
                    target_index=seq,
                    expected_char="a",
                    outcome="correct",
                    first_attempt=True,
                    handler_ms=0.1,
                    dispatch_lag_ms=1.0,
                )
            )
        session.commit()

        report = run_participant_checks(session, p.id)
        assert report.checks.missing_keyups.passed is True
        assert report.checks.missing_keyups.missing_count == 1
        assert report.checks.missing_keyups.total_events == 100
        assert report.checks.missing_keyups.missing_share == 0.01

        # Now update 9 more to have None t_up_ms (total 10 missing -> 10% > 5% -> FAIL)
        events = session.exec(
            select(KeystrokeEvent).where(col(KeystrokeEvent.block_id) == b.id)
        ).all()
        for i in range(1, 10):
            events[i].t_up_ms = None
            session.add(events[i])
        session.commit()

        report2 = run_participant_checks(session, p.id)
        assert report2.checks.missing_keyups.passed is False
        assert report2.checks.missing_keyups.missing_count == 10
        assert report2.checks.missing_keyups.missing_share == 0.10


def test_run_checks_in_progress_sessions(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        p = _create_participant(session)
        now = datetime.now(UTC)
        s = TypingSession(
            id="s-prog",
            participant_id=p.id,
            phase="baseline",
            day_index=1,
            status="in_progress",
            started_at=now,
            client_info={},
        )
        session.add(s)
        session.commit()

        report = run_participant_checks(session, p.id)
        assert report.passed is False
        assert report.checks.in_progress_sessions.passed is False
        assert report.checks.in_progress_sessions.count == 1
        assert "left in_progress" in report.checks.in_progress_sessions.details[0]


def test_session_trends_per_set_calculation(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        p = _create_participant(session)
        session.add(
            BigramAssignment(
                participant_id=p.id,
                bigram="th",
                set_label="A",
                arm="control",
                baseline_rank=1,
                weakness_score=0.8,
                baseline_attempts=10,
                baseline_errors=2,
            )
        )
        session.add(
            BigramAssignment(
                participant_id=p.id,
                bigram="he",
                set_label="B",
                arm="heuristic",
                baseline_rank=2,
                weakness_score=0.7,
                baseline_attempts=10,
                baseline_errors=1,
            )
        )
        now = datetime.now(UTC)
        s = TypingSession(
            id="s-trend",
            participant_id=p.id,
            phase="practice",
            day_index=1,
            status="completed",
            started_at=now,
            wpm=72.5,
            accuracy=0.96,
            client_info={},
        )
        session.add(s)
        session.flush()

        session.add(
            BigramStat(
                participant_id=p.id,
                session_id=s.id,
                bigram="th",
                attempts=20,
                errors=1,
                iki_n=0,
            )
        )
        session.commit()

        report = run_participant_checks(session, p.id)
        assert len(report.trend) == 1
        trend_entry = report.trend[0]
        assert trend_entry.session_id == s.id
        assert trend_entry.wpm == 72.5
        assert trend_entry.accuracy == 0.96
        assert trend_entry.per_set_attempts["A"] == 20
        assert trend_entry.per_set_errors["A"] == 1
        assert trend_entry.per_set_error_rate["A"] == 0.05
        assert trend_entry.per_set_attempts["B"] == 0
        assert trend_entry.per_set_errors["B"] == 0
        assert trend_entry.per_set_error_rate["B"] is None
