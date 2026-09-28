"""GET /api/v1/health in-process, on a temporary SQLite file (design doc section 17.2)."""

from pathlib import Path

from fastapi.testclient import TestClient

from typist.config import Settings
from typist.main import create_app

OK = {"status": "ok", "db": "ok"}
ERROR = {"status": "error", "db": "error"}


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
