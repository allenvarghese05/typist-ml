"""Integration tests for participant API routes (T2.8)."""

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from typist.config import get_settings
from typist.main import create_app


def _client() -> TestClient:
    return TestClient(create_app(get_settings()))


def test_participant_crud_and_consent_lifecycle(migrated_engine: Engine) -> None:
    client = _client()

    create_resp = client.post(
        "/api/v1/participants",
        json={"alias": "p_api_1", "keyboard_label": "ISO"},
    )
    assert create_resp.status_code == 200
    p1 = create_resp.json()
    assert p1["alias"] == "p_api_1"
    assert p1["status"] == "enrolled"
    assert p1["is_builder"] is False
    assert p1["is_blinded"] is True
    pid = p1["id"]

    dup_resp = client.post("/api/v1/participants", json={"alias": "p_api_1"})
    assert dup_resp.status_code == 409

    consent_resp = client.post(f"/api/v1/participants/{pid}/consent")
    assert consent_resp.status_code == 200
    consented = consent_resp.json()
    assert consented["status"] == "baseline"
    assert consented["consent_at"] is not None

    repeat_consent = client.post(f"/api/v1/participants/{pid}/consent")
    assert repeat_consent.status_code == 409

    list_resp = client.get("/api/v1/participants")
    assert list_resp.status_code == 200
    assert any(p["id"] == pid for p in list_resp.json())

    withdraw_resp = client.post(f"/api/v1/participants/{pid}/withdraw")
    assert withdraw_resp.status_code == 200
    assert withdraw_resp.json()["status"] == "withdrawn"

    repeat_withdraw = client.post(f"/api/v1/participants/{pid}/withdraw")
    assert repeat_withdraw.status_code == 409

    del_resp = client.delete(f"/api/v1/participants/{pid}")
    assert del_resp.status_code == 200
    assert del_resp.json()["participants"] == 1

    assert client.delete(f"/api/v1/participants/{pid}").status_code == 404
