"""Settings: the database path is anchored at the repo root, never the working directory."""

from pathlib import Path

import pytest

from typist.config import API_DIR, DEFAULT_DB_PATH, REPO_ROOT, Settings

THIS_FILE = Path(__file__).resolve()


def test_paths_are_derived_from_the_source_tree() -> None:
    assert THIS_FILE.parents[4] == REPO_ROOT
    assert THIS_FILE.parents[2] == API_DIR
    assert (REPO_ROOT / "justfile").is_file()
    assert (API_DIR / "pyproject.toml").is_file()


def test_default_db_path_is_repo_root_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TYPIST_DB_PATH", raising=False)
    settings = Settings()
    assert settings.db_path == REPO_ROOT / "data" / "typist.db"
    assert settings.db_path == DEFAULT_DB_PATH


def test_default_host_and_port() -> None:
    settings = Settings()
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000


def test_env_prefix_overrides_db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "elsewhere.db"
    monkeypatch.setenv("TYPIST_DB_PATH", str(target))
    assert Settings().db_path == target


def test_relative_db_path_resolves_against_repo_root_not_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TYPIST_DB_PATH", "data/other.db")
    assert Settings().db_path == REPO_ROOT / "data" / "other.db"


def test_env_file_is_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("TYPIST_PORT=8123\nUNRELATED_KEY=1\n")
    monkeypatch.setitem(Settings.model_config, "env_file", env_file)
    assert Settings().port == 8123
