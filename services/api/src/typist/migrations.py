"""Alembic entry points shared by the `typist db migrate` command and the tests."""

from alembic import command
from alembic.config import Config

from typist.config import API_DIR

ALEMBIC_INI = API_DIR / "alembic.ini"


def alembic_config() -> Config:
    """Load services/api/alembic.ini. Its paths use %(here)s, so this works from any directory."""
    return Config(str(ALEMBIC_INI))


def upgrade_to_head() -> None:
    """Apply every migration (alembic upgrade head) to Settings.db_path (TYPIST_DB_PATH)."""
    command.upgrade(alembic_config(), "head")
