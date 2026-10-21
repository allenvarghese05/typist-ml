"""typist overhead: p50/p95/p99 printed per session plus an "all" row (T1.10; design doc 12.5)."""

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session
from typer.testing import CliRunner

from typist.cli import app
from typist.models import KeystrokeEvent, Participant, SessionBlock
from typist.models import Session as TypingSession

runner = CliRunner()


def _event(block_id: str, seq: int, handler: float, dispatch: float) -> KeystrokeEvent:
    return KeystrokeEvent(
        block_id=block_id,
        seq=seq,
        key="a",
        code="KeyA",
        t_down_ms=float(seq),
        target_index=seq,
        expected_char="a",
        outcome="correct",
        first_attempt=True,
        handler_ms=handler,
        dispatch_lag_ms=dispatch,
    )


def _seed_session(
    session: Session, participant_id: str, started_at: datetime, samples: list[float]
) -> str:
    ts = TypingSession(
        participant_id=participant_id,
        phase="baseline",
        day_index=1,
        client_info={},
        started_at=started_at,
    )
    session.add(ts)
    session.flush()
    block = SessionBlock(session_id=ts.id, block_index=0, arm="test", target_text="aa")
    session.add(block)
    session.flush()
    session.add_all([_event(block.id, i, value, value) for i, value in enumerate(samples)])
    return ts.id


def _seed(engine: Engine) -> tuple[str, str]:
    with Session(engine) as session:
        participant = Participant(alias="p01")
        session.add(participant)
        session.flush()
        first = _seed_session(
            session,
            participant.id,
            datetime(2026, 10, 6, 9, 0, 0, tzinfo=UTC),
            [1.0, 2.0, 3.0, 4.0, 5.0],
        )
        second = _seed_session(
            session,
            participant.id,
            datetime(2026, 10, 7, 9, 0, 0, tzinfo=UTC),
            [10.0],
        )
        session.commit()
    return first, second


def test_overhead_prints_the_percentile_labels_and_numbers(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    _seed(migrated_engine)
    result = runner.invoke(app, ["overhead"])
    assert result.exit_code == 0, result.output
    assert "p50" in result.output
    assert "p95" in result.output
    assert "p99" in result.output
    # First session [1,2,3,4,5]: p50 3.000, p95 4.800, p99 4.960 for both metrics.
    assert "3.000/4.800/4.960" in result.output
    # Second session [10]: single value is its own percentiles.
    assert "10.000/10.000/10.000" in result.output
    # The pooled row is present.
    assert "all" in result.output


def test_overhead_with_no_events_says_so(isolated_settings: Path, migrated_engine: Engine) -> None:
    result = runner.invoke(app, ["overhead"])
    assert result.exit_code == 0, result.output
    assert "no keystroke events" in result.output
