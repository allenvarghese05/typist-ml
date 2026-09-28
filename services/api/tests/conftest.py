"""Shared pytest setup: the mlx marker (skipped off Apple Silicon) and per-test settings isolation."""

import platform
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from typist.config import Settings, get_settings

MLX_MARKER = "mlx: loads a model with mlx-lm; runs only on macOS arm64 (Apple Silicon)"
MLX_SKIP_REASON = "needs mlx-lm on Apple Silicon (macOS arm64)"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", MLX_MARKER)


def is_apple_silicon() -> bool:
    """True on macOS arm64, the only platform where mlx-lm installs (CLAUDE.md)."""
    return sys.platform == "darwin" and platform.machine() == "arm64"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if is_apple_silicon():
        return
    skip_mlx = pytest.mark.skip(reason=MLX_SKIP_REASON)
    for item in items:
        if item.get_closest_marker("mlx") is not None:
            item.add_marker(skip_mlx)


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point every test at its own temporary database and ignore services/api/.env.

    Yields the database path (TYPIST_DB_PATH). No test may touch the repo-root data/ directory.
    """
    db_path = tmp_path / "typist.db"
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    monkeypatch.delenv("TYPIST_HOST", raising=False)
    monkeypatch.delenv("TYPIST_PORT", raising=False)
    monkeypatch.setenv("TYPIST_DB_PATH", str(db_path))
    get_settings.cache_clear()
    yield db_path
    get_settings.cache_clear()
