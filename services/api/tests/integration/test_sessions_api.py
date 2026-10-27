"""POST /api/v1/participants/{pid}/sessions, GET /api/v1/sessions/{sid}, and
POST /api/v1/sessions/{session_id}/complete (T1.9, T2.6; design doc 10.1, 13.7, 14).
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from typist.config import get_settings
from typist.main import create_app
from typist.models import (
    BigramAssignment,
    Drill,
    ExperimentConfig,
    GenerationJob,
    KeystrokeEvent,
    Participant,
    SessionBlock,
)
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


def test_start_and_get_practice_session_blinds_arms_and_complete_enqueues_jobs(
    migrated_engine: Engine,
) -> None:
    t0 = datetime(2026, 10, 26, 10, 0, 0, tzinfo=UTC)
    arms = ("control", "heuristic", "markov", "llm")
    with Session(migrated_engine) as session:
        session.add(Participant(id="p-api-01", alias="p-api-01", status="practice"))
        session.flush()
        for rank, (label, arm, bg) in enumerate(
            zip(("A", "B", "C", "D"), arms, ("th", "he", "in", "er"), strict=True),
            start=1,
        ):
            session.add(
                BigramAssignment(
                    participant_id="p-api-01",
                    bigram=bg,
                    set_label=label,
                    arm=arm,
                    baseline_rank=rank,
                    weakness_score=0.2,
                    baseline_attempts=20,
                    baseline_errors=4,
                    frozen_at=t0,
                )
            )
        # Seed 6 ready drills per arm (the 3-day target).
        for arm in arms:
            for i in range(6):
                session.add(
                    Drill(
                        id=f"d-{arm}-{i}",
                        participant_id="p-api-01",
                        arm=arm,
                        target_bigrams=[] if arm == "control" else ["th"],
                        text=f"{arm} drill {chr(ord('a') + i)}",
                        target_density=0.0 if arm == "control" else 0.2,
                        mean_word_len=5.0,
                        real_word_ratio=1.0,
                        generator_version=f"{arm}:v1",
                        seed=i + 1,
                        status="ready",
                        created_at=t0,
                    )
                )
        session.commit()

    client = _client()
    start_resp = client.post(
        "/api/v1/participants/p-api-01/sessions",
        json={"client_info": {"ua": "pytest"}},
    )
    assert start_resp.status_code == 200
    plan = start_resp.json()
    assert plan["participant_id"] == "p-api-01"
    assert plan["phase"] == "practice"
    assert plan["day_index"] == 1
    assert plan["status"] == "in_progress"
    assert "block_order" not in plan
    assert len(plan["blocks"]) == 4
    assert [b["label"] for b in plan["blocks"]] == ["Block 1", "Block 2", "Block 3", "Block 4"]
    assert all("arm" not in b and "passage_id" not in b for b in plan["blocks"])

    # Calling POST /participants/{pid}/sessions again returns the open session idempotently.
    repeat_resp = client.post("/api/v1/participants/p-api-01/sessions")
    assert repeat_resp.status_code == 200
    assert repeat_resp.json() == plan

    # GET /sessions/{sid} returns the identical blinded SessionPlan.
    get_resp = client.get(f"/api/v1/sessions/{plan['session_id']}")
    assert get_resp.status_code == 200
    assert get_resp.json() == plan

    # Completing the practice session (now 4 ready drills left per arm, below target 6)
    # enqueues 1 pending GenerationJob per arm with requested == 2.
    complete_resp = client.post(f"/api/v1/sessions/{plan['session_id']}/complete")
    assert complete_resp.status_code == 200
    with Session(migrated_engine) as session:
        jobs = session.exec(
            select(GenerationJob).where(col(GenerationJob.participant_id) == "p-api-01")
        ).all()
    assert {(j.arm, j.requested, j.status) for j in jobs} == {
        ("control", 2, "pending"),
        ("heuristic", 2, "pending"),
        ("markov", 2, "pending"),
        ("llm", 2, "pending"),
    }


def test_session_endpoints_return_404_and_409_on_errors(migrated_engine: Engine) -> None:
    client = _client()
    assert client.post("/api/v1/participants/missing/sessions").status_code == 404
    assert client.get("/api/v1/sessions/missing").status_code == 404

    with Session(migrated_engine) as session:
        session.add(Participant(id="p-empty-pool", alias="p-empty-pool", status="practice"))
        session.add(Participant(id="p-done", alias="p-done", status="done"))
        session.commit()

    # Practice participant with 0 ready drills -> 409 Conflict.
    assert client.post("/api/v1/participants/p-empty-pool/sessions").status_code == 409
    # Participant with status 'done' -> 409 Conflict.
    assert client.post("/api/v1/participants/p-done/sessions").status_code == 409


def test_enrolled_participant_cannot_start_session_returns_409(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        session.add(Participant(id="p-unconsented", alias="p-unconsented", status="enrolled"))
        session.commit()
    client = _client()
    resp = client.post("/api/v1/participants/p-unconsented/sessions")
    assert resp.status_code == 409
    assert "consent" in resp.json()["detail"]


def test_withdrawn_participant_cannot_start_or_complete_session_returns_409(
    migrated_engine: Engine,
) -> None:
    session_id = _seed_golden(migrated_engine)
    client = _client()
    with Session(migrated_engine) as session:
        ts = session.get(TypingSession, session_id)
        assert ts is not None
        p = session.get(Participant, ts.participant_id)
        assert p is not None
        pid = p.id
        p.status = "withdrawn"
        session.add(p)
        session.commit()

    assert client.post(f"/api/v1/participants/{pid}/sessions").status_code == 409
    comp_resp = client.post(f"/api/v1/sessions/{session_id}/complete")
    assert comp_resp.status_code == 409
    assert "withdrawn" in comp_resp.json()["detail"]


def test_session_completion_advances_practice_to_retest_and_retest_to_done(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        cfg = session.get(ExperimentConfig, "practice_days")
        assert cfg is not None
        cfg.value = 1
        cfg_r = session.get(ExperimentConfig, "retest_parts")
        assert cfg_r is not None
        cfg_r.value = 1
        session.add(cfg)
        session.add(cfg_r)

        p = Participant(id="p-prog", alias="p-prog", status="practice")
        session.add(p)
        session.flush()
        s_prac = TypingSession(
            id="s-prac",
            participant_id="p-prog",
            phase="practice",
            day_index=1,
            status="in_progress",
            client_info={},
            started_at=datetime.now(UTC),
        )
        session.add(s_prac)
        session.commit()

    client = _client()
    resp_prac = client.post("/api/v1/sessions/s-prac/complete")
    assert resp_prac.status_code == 200

    with Session(migrated_engine) as session:
        p = session.get(Participant, "p-prog")
        assert p is not None and p.status == "retest"

        s_ret = TypingSession(
            id="s-ret",
            participant_id="p-prog",
            phase="retest",
            day_index=1,
            status="in_progress",
            client_info={},
            started_at=datetime.now(UTC),
        )
        session.add(s_ret)
        session.commit()

    resp_ret = client.post("/api/v1/sessions/s-ret/complete")
    assert resp_ret.status_code == 200

    with Session(migrated_engine) as session:
        p = session.get(Participant, "p-prog")
        assert p is not None and p.status == "done"

    assert client.post("/api/v1/participants/p-prog/sessions").status_code == 409
