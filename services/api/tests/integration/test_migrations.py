"""Alembic: the environment uses the app's database setting and pragmas; new revisions pass ruff."""

import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from alembic import command

from typist.config import API_DIR
from typist.migrations import alembic_config, upgrade_to_head


def test_upgrade_head_on_empty_history_uses_the_configured_database(
    isolated_settings: Path,
) -> None:
    upgrade_to_head()
    assert isolated_settings.is_file()
    with closing(sqlite3.connect(isolated_settings)) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_new_revision_is_fixed_and_formatted_by_ruff(tmp_path: Path) -> None:
    script_dir = tmp_path / "alembic"
    shutil.copytree(API_DIR / "alembic", script_dir, ignore=shutil.ignore_patterns("__pycache__"))
    config = alembic_config()
    config.set_main_option("script_location", str(script_dir))
    command.revision(config, message="probe revision", rev_id="0001probe")
    source = (script_dir / "versions" / "0001probe_probe_revision.py").read_text()
    compile(source, "0001probe_probe_revision.py", "exec")
    assert 'revision: str = "0001probe"' in source
    assert "down_revision: str | Sequence[str] | None = None" in source
    assert "def upgrade() -> None:" in source
    assert "def downgrade() -> None:" in source
    assert "import sqlmodel" not in source
    assert "import sqlalchemy as sa" not in source
