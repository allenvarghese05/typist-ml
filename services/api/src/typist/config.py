"""Typed settings for the API, CLI and (later) the worker (design doc sections 5.2 and 7).

Each setting can be overridden with an environment variable prefixed TYPIST_ (for example
TYPIST_DB_PATH) or in services/api/.env. Relative paths are resolved against the repository root,
never the working directory, so the database always lands in the gitignored root data/ directory.
The paths below come from this file's location, which needs the editable install `uv sync` makes.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# services/api: holds pyproject.toml, alembic.ini and the optional .env file.
API_DIR = Path(__file__).resolve().parents[2]
# The repository root: holds the justfile and the gitignored data/ directory.
REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "typist.db"


class Settings(BaseSettings):
    """Process settings.

    Attributes:
        db_path: SQLite database file. Default <repo>/data/typist.db. A relative value is taken
            relative to the repository root.
        host: Address the API serves on. `just dev` passes the same value to uvicorn.
        port: Port the API serves on. `just dev` passes the same value to uvicorn.
    """

    model_config = SettingsConfigDict(
        env_prefix="TYPIST_",
        env_file=API_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_path: Path = DEFAULT_DB_PATH
    host: str = "127.0.0.1"
    port: int = 8000

    @field_validator("db_path")
    @classmethod
    def _anchor_db_path(cls, value: Path) -> Path:
        """Resolve a relative db_path against the repository root (never the working directory)."""
        path = value.expanduser()
        return path if path.is_absolute() else REPO_ROOT / path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, read once from the environment and services/api/.env."""
    return Settings()
