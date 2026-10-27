"""Integration tests for admin endpoints (T2.8, T2.9)."""

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


def test_admin_pool_endpoints(migrated_engine: Engine) -> None:
    client = _client()
    # 404 when participant does not exist
    assert client.get("/api/v1/admin/pool?participant_id=missing").status_code == 404

    with Session(migrated_engine) as session:
        session.add(Participant(id=PID, alias="pilot-pool", status="baseline"))
        session.commit()

    # Get all pools
    resp_all = client.get("/api/v1/admin/pool")
    assert resp_all.status_code == 200
    all_data = resp_all.json()
    assert len(all_data) >= 1
    assert any(p["participant_id"] == PID for p in all_data)

    # Filter by participant_id
    resp_single = client.get(f"/api/v1/admin/pool?participant_id={PID}")
    assert resp_single.status_code == 200
    single_data = resp_single.json()
    assert len(single_data) == 1
    assert single_data[0]["participant_id"] == PID
    assert len(single_data[0]["arms"]) == 4


def test_admin_pool_replenish(migrated_engine: Engine) -> None:
    client = _client()
    # 404 missing
    assert (
        client.post("/api/v1/admin/pool/replenish", json={"participant_id": "missing"}).status_code
        == 404
    )

    with Session(migrated_engine) as session:
        session.add(Participant(id="p-unassigned", alias="unassigned", status="baseline"))
        session.commit()

    # 409 unassigned
    resp_unassigned = client.post(
        "/api/v1/admin/pool/replenish", json={"participant_id": "p-unassigned"}
    )
    assert resp_unassigned.status_code == 409
    assert "no frozen bigram assignment" in resp_unassigned.json()["detail"]

    # Assign participant
    with Session(migrated_engine) as session:
        _seed_baseline(session, PID)
        session.commit()
    assign_resp = client.post(f"/api/v1/admin/participants/{PID}/assign")
    assert assign_resp.status_code == 200

    # 200 replenish
    resp_replenish = client.post("/api/v1/admin/pool/replenish", json={"participant_id": PID})
    assert resp_replenish.status_code == 200
    jobs = resp_replenish.json()
    assert len(jobs) > 0
    assert all(j["participant_id"] == PID for j in jobs)


def test_admin_jobs_endpoints(migrated_engine: Engine) -> None:
    client = _client()
    # 404 on missing participant
    assert client.post("/api/v1/admin/jobs", json={"participant_id": "missing"}).status_code == 404

    with Session(migrated_engine) as session:
        session.add(Participant(id=PID, alias="pilot-jobs", status="assigned"))
        session.commit()

    # 422 on invalid arm
    resp_invalid_arm = client.post(
        "/api/v1/admin/jobs", json={"participant_id": PID, "arm": "invalid_arm"}
    )
    assert resp_invalid_arm.status_code == 422

    # 409 on targeted arm without assignment
    resp_unassigned_arm = client.post(
        "/api/v1/admin/jobs", json={"participant_id": PID, "arm": "llm"}
    )
    assert resp_unassigned_arm.status_code == 409

    # 201 on control arm (needs no bigram assignment)
    resp_control = client.post(
        "/api/v1/admin/jobs", json={"participant_id": PID, "arm": "control", "requested": 3}
    )
    assert resp_control.status_code == 201
    created_jobs = resp_control.json()
    assert len(created_jobs) == 1
    assert created_jobs[0]["arm"] == "control"
    assert created_jobs[0]["requested"] == 3
    assert created_jobs[0]["status"] == "pending"

    # GET /admin/jobs
    resp_jobs = client.get("/api/v1/admin/jobs")
    assert resp_jobs.status_code == 200
    jobs = resp_jobs.json()
    assert len(jobs) >= 1

    # Filter by participant_id & status
    resp_filtered = client.get(f"/api/v1/admin/jobs?participant_id={PID}&status=pending&limit=10")
    assert resp_filtered.status_code == 200
    filtered_jobs = resp_filtered.json()
    assert len(filtered_jobs) == 1
    assert filtered_jobs[0]["participant_id"] == PID
    assert filtered_jobs[0]["status"] == "pending"


def test_admin_checks_endpoint(migrated_engine: Engine) -> None:
    client = _client()
    assert client.get("/api/v1/admin/checks/missing").status_code == 404

    with Session(migrated_engine) as session:
        session.add(Participant(id=PID, alias="pilot-checks", status="baseline"))
        session.commit()

    resp = client.get(f"/api/v1/admin/checks/{PID}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["participant_id"] == PID
    assert data["passed"] is True
    assert "seq_gaps" in data["checks"]
    assert "dwell_anomalies" in data["checks"]
    assert "short_blocks" in data["checks"]
    assert "missing_keyups" in data["checks"]
    assert "in_progress_sessions" in data["checks"]
    assert data["trend"] == []
