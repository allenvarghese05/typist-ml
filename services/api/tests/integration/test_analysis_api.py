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
from typist.models import (
    BigramAssignment,
    BigramStat,
    KeystrokeEvent,
    Participant,
    SessionBlock,
)
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


def test_participant_results_404_when_missing(migrated_engine: Engine) -> None:
    response = _client().get("/api/v1/analysis/participants/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"detail": "participant not found"}


def test_participant_results_409_when_not_done(
    migrated_engine: Engine, seeded_ids: dict[str, str]
) -> None:
    pid = seeded_ids["participant_id"]
    response = _client().get(f"/api/v1/analysis/participants/{pid}")
    assert response.status_code == 409


def test_participant_results_200_when_done(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        participant = Participant(alias="done-user", status="done")
        session.add(participant)
        session.flush()
        pid = participant.id

        # Add assignments for Set A (control) and Set B (heuristic)
        session.add_all(
            [
                BigramAssignment(
                    participant_id=pid,
                    set_label="A",
                    arm="control",
                    bigram="th",
                    baseline_rank=1,
                    weakness_score=0.5,
                    baseline_attempts=10,
                    baseline_errors=2,
                    frozen_at=NOW,
                ),
                BigramAssignment(
                    participant_id=pid,
                    set_label="B",
                    arm="heuristic",
                    bigram="er",
                    baseline_rank=2,
                    weakness_score=0.4,
                    baseline_attempts=20,
                    baseline_errors=4,
                    frozen_at=NOW,
                ),
            ]
        )
        session.flush()

        # Add completed baseline session
        s_base = TypingSession(
            participant_id=pid,
            phase="baseline",
            day_index=1,
            status="completed",
            wpm=30.0,
            client_info={},
            started_at=NOW,
            ended_at=NOW,
        )
        session.add(s_base)
        session.flush()

        # Add completed retest session
        s_retest = TypingSession(
            participant_id=pid,
            phase="retest",
            day_index=1,
            status="completed",
            wpm=40.0,
            client_info={},
            started_at=NOW,
            ended_at=NOW,
        )
        session.add(s_retest)
        session.flush()

        # Add BigramStat rows
        session.add_all(
            [
                BigramStat(
                    participant_id=pid,
                    session_id=s_base.id,
                    bigram="th",
                    attempts=10,
                    errors=2,
                    iki_n=0,
                ),
                BigramStat(
                    participant_id=pid,
                    session_id=s_base.id,
                    bigram="er",
                    attempts=20,
                    errors=4,
                    iki_n=0,
                ),
                BigramStat(
                    participant_id=pid,
                    session_id=s_retest.id,
                    bigram="th",
                    attempts=10,
                    errors=1,
                    iki_n=0,
                ),
                BigramStat(
                    participant_id=pid,
                    session_id=s_retest.id,
                    bigram="er",
                    attempts=20,
                    errors=2,
                    iki_n=0,
                ),
            ]
        )
        session.commit()

    response = _client().get(f"/api/v1/analysis/participants/{pid}")
    assert response.status_code == 200
    body = response.json()
    assert body["participant_id"] == pid
    assert body["alias"] == "done-user"
    assert body["status"] == "done"
    assert body["baseline_wpm"] == 30.0
    assert body["retest_wpm"] == 40.0
    assert len(body["sets"]) == 2

    sets_by_label = {s["set_label"]: s for s in body["sets"]}
    assert "A" in sets_by_label
    assert sets_by_label["A"]["arm"] == "control"
    assert sets_by_label["A"]["bigrams"] == ["th"]
    assert sets_by_label["A"]["baseline_attempts"] == 10
    assert sets_by_label["A"]["baseline_errors"] == 2
    assert sets_by_label["A"]["baseline_error_rate"] == 0.2
    assert sets_by_label["A"]["retest_attempts"] == 10
    assert sets_by_label["A"]["retest_errors"] == 1
    assert sets_by_label["A"]["retest_error_rate"] == 0.1

    assert "B" in sets_by_label
    assert sets_by_label["B"]["arm"] == "heuristic"
    assert sets_by_label["B"]["bigrams"] == ["er"]
    assert sets_by_label["B"]["baseline_attempts"] == 20
    assert sets_by_label["B"]["baseline_errors"] == 4
    assert sets_by_label["B"]["baseline_error_rate"] == 0.2
    assert sets_by_label["B"]["retest_attempts"] == 20
    assert sets_by_label["B"]["retest_errors"] == 2
    assert sets_by_label["B"]["retest_error_rate"] == 0.1
