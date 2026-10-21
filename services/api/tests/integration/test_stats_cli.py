"""typist stats recompute: rebuilds completed sessions and reproduces identical numbers (T1.9)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from sqlalchemy import Engine
from sqlmodel import Session, col, select
from typer.testing import CliRunner

from typist.cli import app
from typist.models import BigramStat, KeystrokeEvent, Participant, SessionBlock
from typist.models import Session as TypingSession
from typist.services.session_stats import complete_session

runner = CliRunner()
FIXTURE_PATH: Final = Path(__file__).resolve().parents[1] / "fixtures" / "golden_session.json"
ROW_FIELDS: Final = (
    "seq",
    "key",
    "code",
    "t_down_ms",
    "t_up_ms",
    "dwell_ms",
    "iki_ms",
    "target_index",
    "expected_char",
    "outcome",
    "first_attempt",
    "after_pause",
    "handler_ms",
    "dispatch_lag_ms",
)
NOW: Final = datetime(2026, 10, 19, 10, 0, 0, tzinfo=UTC)


def _golden() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _seed_completed(engine: Engine) -> str:
    golden = _golden()
    with Session(engine) as session:
        participant = Participant(alias="golden")
        session.add(participant)
        session.flush()
        ts = TypingSession(
            participant_id=participant.id,
            phase=golden["session"]["phase"],
            day_index=1,
            client_info={},
            started_at=datetime(2026, 10, 6, 9, 0, 0, tzinfo=UTC),
        )
        session.add(ts)
        session.flush()
        block = SessionBlock(
            session_id=ts.id,
            block_index=golden["session"]["block_index"],
            arm=golden["session"]["arm"],
            target_text=golden["session"]["target_text"],
        )
        session.add(block)
        session.flush()
        rows = [{field: row[field] for field in ROW_FIELDS} for row in golden["keystrokes"]]
        session.add_all([KeystrokeEvent(block_id=block.id, **values) for values in rows])
        session_id = ts.id
        session.commit()
        complete_session(session, session_id, NOW)
    return session_id


def _bigrams(engine: Engine, session_id: str) -> list[tuple[Any, ...]]:
    with Session(engine) as session:
        rows = session.exec(
            select(BigramStat).where(col(BigramStat.session_id) == session_id)
        ).all()
    return sorted((r.bigram, r.attempts, r.errors, r.iki_median_ms, r.iki_n) for r in rows)


def test_recompute_reproduces_the_same_numbers(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    session_id = _seed_completed(migrated_engine)
    before = _bigrams(migrated_engine, session_id)
    result = runner.invoke(app, ["stats", "recompute"])
    assert result.exit_code == 0, result.output
    assert "recomputed 1 session(s); skipped 0" in result.output
    assert _bigrams(migrated_engine, session_id) == before
    assert len(before) == 19


def test_help_lists_the_stats_recompute_command() -> None:
    root = runner.invoke(app, ["--help"])
    assert root.exit_code == 0, root.output
    assert "stats" in root.output
    group = runner.invoke(app, ["stats", "--help"])
    assert group.exit_code == 0, group.output
    assert "recompute" in group.output
