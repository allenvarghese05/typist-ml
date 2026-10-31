"""Unit tests for the `typist analyze` Typer CLI command (T4.1)."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlmodel import Session
from typer.testing import CliRunner

from typist.cli import app
from typist.db import create_db_engine
from typist.migrations import upgrade_to_head
from typist.models import BigramAssignment, BigramStat, Participant
from typist.models import Session as TypingSession

runner = CliRunner()
NOW = datetime(2026, 10, 30, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def migrated_engine(isolated_settings: Path) -> Iterator[Engine]:
    """Upgrade per-test db and yield engine."""
    upgrade_to_head()
    engine = create_db_engine(isolated_settings)
    try:
        yield engine
    finally:
        engine.dispose()


def test_cli_analyze_participant_not_found(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    """Invoking analyze on non-existent participant exits with code 1 and error message."""
    result = runner.invoke(app, ["analyze", "--pid", "does-not-exist"])
    assert result.exit_code == 1
    assert "no participant with id 'does-not-exist'" in result.output


def test_cli_analyze_participant_not_done(isolated_settings: Path, migrated_engine: Engine) -> None:
    """Invoking analyze on participant with status other than 'done' exits with code 1."""
    with Session(migrated_engine) as session:
        participant = Participant(alias="active-user", status="enrolled")
        session.add(participant)
        session.commit()
        pid = participant.id

    result = runner.invoke(app, ["analyze", "--pid", pid])
    assert result.exit_code == 1
    assert f"cannot analyze {pid}" in result.output
    assert "status is 'enrolled', expected 'done'" in result.output


def test_cli_analyze_success(isolated_settings: Path, migrated_engine: Engine) -> None:
    """Seeds a completed participant and runs CLI runner on analyze --pid; asserts code 0 and table output."""
    with Session(migrated_engine) as session:
        participant = Participant(alias="done-tester", status="done")
        session.add(participant)
        session.flush()
        pid = participant.id

        session.add_all(
            [
                BigramAssignment(
                    participant_id=pid,
                    set_label="A",
                    arm="control",
                    bigram="th",
                    baseline_rank=1,
                    weakness_score=0.5,
                    baseline_attempts=30,
                    baseline_errors=3,
                    frozen_at=NOW,
                ),
                BigramAssignment(
                    participant_id=pid,
                    set_label="B",
                    arm="heuristic",
                    bigram="er",
                    baseline_rank=2,
                    weakness_score=0.4,
                    baseline_attempts=30,
                    baseline_errors=3,
                    frozen_at=NOW,
                ),
            ]
        )
        session.flush()

        s_base = TypingSession(
            participant_id=pid,
            phase="baseline",
            day_index=1,
            status="completed",
            wpm=55.0,
            accuracy=0.96,
            client_info={},
            started_at=NOW,
            ended_at=NOW,
        )
        s_retest = TypingSession(
            participant_id=pid,
            phase="retest",
            day_index=2,
            status="completed",
            wpm=60.0,
            accuracy=0.98,
            client_info={},
            started_at=NOW,
            ended_at=NOW,
        )
        session.add_all([s_base, s_retest])
        session.flush()

        session.add_all(
            [
                BigramStat(
                    participant_id=pid,
                    session_id=s_base.id,
                    bigram="th",
                    attempts=30,
                    errors=3,
                    iki_n=0,
                ),
                BigramStat(
                    participant_id=pid,
                    session_id=s_base.id,
                    bigram="er",
                    attempts=30,
                    errors=3,
                    iki_n=0,
                ),
                BigramStat(
                    participant_id=pid,
                    session_id=s_retest.id,
                    bigram="th",
                    attempts=30,
                    errors=2,
                    iki_n=0,
                ),
                BigramStat(
                    participant_id=pid,
                    session_id=s_retest.id,
                    bigram="er",
                    attempts=30,
                    errors=1,
                    iki_n=0,
                ),
            ]
        )
        session.commit()

    result = runner.invoke(app, ["analyze", "--pid", pid, "--draws", "1000", "--resamples", "100"])
    assert result.exit_code == 0, result.output
    assert "Participant: done-tester" in result.output
    assert "PRIMARY OUTCOME: Error Rates and Beta Posterior Targeting Effects" in result.output
    assert "KEY SECONDARY OUTCOME: Median IKI and Bootstrap Confidence Intervals" in result.output
    assert "EXCLUSIONS REPORT:" in result.output
    assert "Set   Arm" in result.output
