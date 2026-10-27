"""Integration tests for typist check [--pid] CLI (T2.9)."""

from datetime import UTC, datetime

from sqlalchemy import Engine
from sqlmodel import Session
from typer.testing import CliRunner

from typist.cli import app
from typist.models import KeystrokeEvent, Participant, SessionBlock
from typist.models import Session as TypingSession

runner = CliRunner()


def test_cli_check_specific_participant(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        session.add(Participant(id="p-clean", alias="clean-user", status="baseline"))
        session.commit()

    result = runner.invoke(app, ["check", "--pid", "p-clean"])
    assert result.exit_code == 0
    assert "clean-user (p-clean)" in result.output
    assert "Data Quality Checks: [PASSED]" in result.output
    assert "[PASS] Sequence Gaps: 0 gap(s)" in result.output
    assert "[PASS] Dwell Anomalies: 0 negative, 0 > 1000ms" in result.output
    assert "[PASS] Short Blocks: 0 short block(s)" in result.output
    assert "[PASS] Missing Keyups: 0/0" in result.output
    assert "[PASS] In-Progress Sessions: 0 lingering" in result.output


def test_cli_check_fails_on_anomaly(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        session.add(Participant(id="p-gap", alias="gap-user", status="baseline"))
        now = datetime.now(UTC)
        s = TypingSession(
            id="s-gap-cli",
            participant_id="p-gap",
            phase="baseline",
            day_index=1,
            status="completed",
            started_at=now,
            client_info={},
        )
        session.add(s)
        session.flush()

        b = SessionBlock(
            id="b-gap-cli",
            session_id=s.id,
            block_index=0,
            arm="test",
            target_text="test",
        )
        session.add(b)
        session.flush()

        # Seed gap between 0 and 3
        for seq in [0, 3]:
            session.add(
                KeystrokeEvent(
                    block_id=b.id,
                    seq=seq,
                    key="a",
                    code="KeyA",
                    t_down_ms=10.0 * seq,
                    t_up_ms=10.0 * seq + 5.0,
                    dwell_ms=5.0,
                    target_index=seq,
                    expected_char="a",
                    outcome="correct",
                    first_attempt=True,
                    handler_ms=0.1,
                    dispatch_lag_ms=1.0,
                )
            )
        session.commit()

    result = runner.invoke(app, ["check", "--pid", "p-gap"])
    assert result.exit_code == 1
    assert "Data Quality Checks: [FAILED]" in result.output
    assert "[FAIL] Sequence Gaps: 1 gap(s)" in result.output


def test_cli_check_missing_participant(migrated_engine: Engine) -> None:
    result = runner.invoke(app, ["check", "--pid", "nonexistent"])
    assert result.exit_code == 1
    assert "no participant with id 'nonexistent'" in result.output


def test_cli_check_all_participants(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        session.add(Participant(id="p-all-1", alias="alpha", status="baseline"))
        session.add(Participant(id="p-all-2", alias="beta", status="baseline"))
        session.commit()

    result = runner.invoke(app, ["check"])
    assert result.exit_code == 0
    assert "alpha (p-all-1)" in result.output
    assert "beta (p-all-2)" in result.output
