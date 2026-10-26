"""GET /api/v1/health in-process, on a temporary SQLite file (design doc section 17.2; T2.5)."""

from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from typist.config import Settings
from typist.db import utc_now
from typist.main import create_app
from typist.worker import heartbeat_path, write_heartbeat

OK = {"status": "ok", "db": "ok", "worker_heartbeat_age_s": None}
ERROR = {"status": "error", "db": "error", "worker_heartbeat_age_s": None}


def client_for(db_path: Path) -> TestClient:
    return TestClient(create_app(Settings(db_path=db_path)))


def test_health_returns_ok_and_creates_the_database(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "typist.db"
    with client_for(db_path) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == OK
    assert db_path.is_file()


def test_health_returns_503_when_the_database_cannot_be_opened(tmp_path: Path) -> None:
    directory = tmp_path / "not-a-file"
    directory.mkdir()
    with client_for(directory) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json() == ERROR


def test_health_is_served_only_under_the_api_prefix(tmp_path: Path) -> None:
    with client_for(tmp_path / "typist.db") as client:
        assert client.get("/health").status_code == 404
        assert client.get("/api/health").status_code == 404


def test_docs_are_disabled_and_openapi_is_under_the_prefix(tmp_path: Path) -> None:
    with client_for(tmp_path / "typist.db") as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        schema = client.get("/api/v1/openapi.json")
    assert schema.status_code == 200
    assert "/api/v1/health" in schema.json()["paths"]


def test_no_cors_headers_are_sent(tmp_path: Path) -> None:
    with client_for(tmp_path / "typist.db") as client:
        response = client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert "access-control-allow-origin" not in response.headers


def test_create_app_without_arguments_uses_the_environment(isolated_settings: Path) -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == OK
    assert app.state.settings.db_path == isolated_settings
    assert isolated_settings.is_file()


def test_health_reports_worker_heartbeat_age_when_heartbeat_file_exists(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "data" / "typist.db"
    write_heartbeat(db_path, now=utc_now() - timedelta(seconds=1.5))
    with client_for(db_path) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["worker_heartbeat_age_s"] is not None
    assert 1.0 <= body["worker_heartbeat_age_s"] <= 5.0


def test_health_returns_ok_when_heartbeat_is_missing_or_corrupt(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "data" / "typist.db"
    target = heartbeat_path(db_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("not-a-timestamp", encoding="utf-8")
    with client_for(db_path) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == OK
