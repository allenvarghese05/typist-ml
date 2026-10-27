"""Integration tests for POST /api/v1/admin/participants/{pid}/assign (T2.8)."""

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session
from test_assignment_service import PID, _index, _seed_baseline

from typist.api.routers.admin import get_word_index
from typist.config import get_settings
from typist.main import create_app
from typist.models import Participant


def _client() -> TestClient:
    app = create_app(get_settings())
    app.dependency_overrides[get_word_index] = lambda: _index()
    return TestClient(app)


def test_admin_assign_end_to_end(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        _seed_baseline(session, PID)
        session.commit()

    client = _client()
    resp = client.post(f"/api/v1/admin/participants/{PID}/assign")
    assert resp.status_code == 200
    data = resp.json()
    assert data["participant_id"] == PID
    assert data["status"] == "assigned"
    assert data["frozen_bigrams"] == 16
    assert set(data["mapping"].keys()) == {"A", "B", "C", "D"}

    with Session(migrated_engine) as session:
        p = session.get(Participant, PID)
        assert p is not None and p.status == "assigned"

    repeat_resp = client.post(f"/api/v1/admin/participants/{PID}/assign")
    assert repeat_resp.status_code == 409
    assert "cannot be assigned" in repeat_resp.json()["detail"]


def test_admin_assign_rejects_non_baseline_and_incomplete(migrated_engine: Engine) -> None:
    client = _client()
    assert client.post("/api/v1/admin/participants/missing/assign").status_code == 404

    with Session(migrated_engine) as session:
        session.add(Participant(id="p-enrolled", alias="p-enrolled", status="enrolled"))
        session.commit()

    resp_enrolled = client.post("/api/v1/admin/participants/p-enrolled/assign")
    assert resp_enrolled.status_code == 409
    assert "must be 'baseline'" in resp_enrolled.json()["detail"]

    with Session(migrated_engine) as session:
        _seed_baseline(session, "p-incomp", parts=1)
        session.commit()

    resp_incomp = client.post("/api/v1/admin/participants/p-incomp/assign")
    assert resp_incomp.status_code == 409
    assert "completed baseline sessions" in resp_incomp.json()["detail"]
