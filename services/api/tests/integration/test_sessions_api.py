"""POST /api/v1/sessions/{session_id}/complete: 404, 409 and the golden 200 (T1.9; design doc 14)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session

from typist.config import get_settings
from typist.main import create_app
from typist.models import KeystrokeEvent, Participant, SessionBlock
from typist.models import Session as TypingSession

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


def _golden() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _client() -> TestClient:
    return TestClient(create_app(get_settings()))


def _seed_golden(engine: Engine, status: str = "in_progress") -> str:
    golden = _golden()
    with Session(engine) as session:
        participant = Participant(alias="golden")
        session.add(participant)
        session.flush()
        ts = TypingSession(
            participant_id=participant.id,
            phase=golden["session"]["phase"],
            day_index=1,
            client_info={"source": "golden"},
            started_at=datetime(2026, 10, 6, 9, 0, 0, tzinfo=UTC),
            status=status,
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
    return session_id


def test_complete_unknown_session_returns_404(migrated_engine: Engine) -> None:
    response = _client().post("/api/v1/sessions/does-not-exist/complete")
    assert response.status_code == 404


def test_complete_already_completed_session_returns_409(migrated_engine: Engine) -> None:
    session_id = _seed_golden(migrated_engine, status="completed")
    response = _client().post(f"/api/v1/sessions/{session_id}/complete")
    assert response.status_code == 409


def test_complete_golden_session_returns_the_summary(migrated_engine: Engine) -> None:
    session_id = _seed_golden(migrated_engine)
    response = _client().post(f"/api/v1/sessions/{session_id}/complete")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "session_id": session_id,
        "wpm": 22.0,
        "accuracy": 0.859375,
        "bigram_count": 19,
        "blocks": 1,
    }
    # Completing an already-completed session now returns 409.
    assert _client().post(f"/api/v1/sessions/{session_id}/complete").status_code == 409
