"""Integration tests for POST /api/v1/blocks/{bid}/start and /complete (T2.8)."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session

from typist.config import get_settings
from typist.main import create_app
from typist.models import Participant, SessionBlock
from typist.models import Session as TypingSession

T0 = datetime(2026, 10, 27, 10, 0, 0, tzinfo=UTC)


def _client() -> TestClient:
    return TestClient(create_app(get_settings()))


def _seed_block(
    engine: Engine,
    *,
    participant_status: str = "baseline",
    session_status: str = "in_progress",
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
) -> str:
    with Session(engine) as session:
        participant = Participant(alias=f"user_{datetime.now(UTC).timestamp()}", status=participant_status)
        session.add(participant)
        session.flush()
        ts = TypingSession(
            participant_id=participant.id,
            phase="baseline",
            day_index=1,
            status=session_status,
            client_info={},
            started_at=T0,
        )
        session.add(ts)
        session.flush()
        block = SessionBlock(
            session_id=ts.id,
            block_index=0,
            arm="test",
            target_text="test text",
            started_at=started_at,
            ended_at=ended_at,
        )
        session.add(block)
        session.commit()
        return block.id


def test_block_start_and_complete_lifecycle(migrated_engine: Engine) -> None:
    block_id = _seed_block(migrated_engine)
    client = _client()

    start_resp = client.post(f"/api/v1/blocks/{block_id}/start")
    assert start_resp.status_code == 200
    data = start_resp.json()
    assert data["id"] == block_id
    assert data["label"] == "Block 1"
    assert data["started_at"] is not None
    assert data["ended_at"] is None
    assert "arm" not in data

    repeat_start = client.post(f"/api/v1/blocks/{block_id}/start")
    assert repeat_start.status_code == 409
    assert "already started" in repeat_start.json()["detail"]

    complete_resp = client.post(f"/api/v1/blocks/{block_id}/complete")
    assert complete_resp.status_code == 200
    comp_data = complete_resp.json()
    assert comp_data["ended_at"] is not None

    repeat_complete = client.post(f"/api/v1/blocks/{block_id}/complete")
    assert repeat_complete.status_code == 409
    assert "already completed" in repeat_complete.json()["detail"]


def test_block_complete_without_start_returns_409(migrated_engine: Engine) -> None:
    block_id = _seed_block(migrated_engine)
    client = _client()
    resp = client.post(f"/api/v1/blocks/{block_id}/complete")
    assert resp.status_code == 409
    assert "not started" in resp.json()["detail"]


def test_block_endpoints_return_404_on_missing_block(migrated_engine: Engine) -> None:
    client = _client()
    assert client.post("/api/v1/blocks/missing/start").status_code == 404
    assert client.post("/api/v1/blocks/missing/complete").status_code == 404


def test_block_endpoints_return_409_when_session_not_in_progress(migrated_engine: Engine) -> None:
    block_id = _seed_block(migrated_engine, session_status="completed")
    client = _client()
    assert client.post(f"/api/v1/blocks/{block_id}/start").status_code == 409
    assert client.post(f"/api/v1/blocks/{block_id}/complete").status_code == 409


def test_block_endpoints_return_409_when_participant_withdrawn(migrated_engine: Engine) -> None:
    block_id = _seed_block(migrated_engine, participant_status="withdrawn")
    client = _client()
    assert client.post(f"/api/v1/blocks/{block_id}/start").status_code == 409
    assert client.post(f"/api/v1/blocks/{block_id}/complete").status_code == 409
