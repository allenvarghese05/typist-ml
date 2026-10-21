"""GET /api/v1/analysis/sessions/{session_id}/matrix: 404, 409 and the golden 200 (T1.10)."""

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
from typist.services.session_stats import complete_session

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


def _client() -> TestClient:
    return TestClient(create_app(get_settings()))


def _seed_completed_golden(engine: Engine) -> str:
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


def test_matrix_unknown_session_returns_404(migrated_engine: Engine) -> None:
    response = _client().get("/api/v1/analysis/sessions/does-not-exist/matrix")
    assert response.status_code == 404


def test_matrix_in_progress_session_returns_409(
    migrated_engine: Engine, seeded_ids: dict[str, str]
) -> None:
    # seeded_ids' session is in_progress (T1.9 build record); it is not completed -> 409.
    response = _client().get(f"/api/v1/analysis/sessions/{seeded_ids['session_id']}/matrix")
    assert response.status_code == 409


def test_matrix_completed_golden_session_returns_200(migrated_engine: Engine) -> None:
    session_id = _seed_completed_golden(migrated_engine)
    response = _client().get(f"/api/v1/analysis/sessions/{session_id}/matrix")
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == session_id
    assert body["phase"] == _golden()["session"]["phase"]
    assert body["wpm"] == 22.0
    assert body["accuracy"] == 0.859375
    assert len(body["cells"]) == 19
    cells = {cell["bigram"]: cell for cell in body["cells"]}
    # Every stored cell has attempts >= 1, so error_rate is errors/attempts, never None.
    for cell in body["cells"]:
        assert cell["attempts"] >= 1
        assert cell["error_rate"] == cell["errors"] / cell["attempts"]
        if cell["iki_n"] == 0:
            assert cell["iki_median_ms"] is None
    # Cells are ordered by bigram.
    assert list(cells) == sorted(cells)
