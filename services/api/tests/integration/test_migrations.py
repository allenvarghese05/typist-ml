"""Alembic: env uses the app's database and pragmas; revision 0001 upgrades and downgrades
(empty, populated, round trip); new revisions pass ruff; log lines are readable (T1.1)."""

import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel

from typist.config import API_DIR
from typist.db import create_db_engine
from typist.migrations import alembic_config, upgrade_to_head
from typist.models import Participant

HEAD = "0001_initial_schema"
APP_TABLES = frozenset(
    {
        "participants",
        "experiment_config",
        "text_passages",
        "sessions",
        "session_blocks",
        "keystroke_events",
    }
)
# Literal queries per table (no SQL is built from strings).
COUNT_QUERIES: dict[str, str] = {
    "participants": "SELECT count(*) FROM participants",
    "experiment_config": "SELECT count(*) FROM experiment_config",
    "text_passages": "SELECT count(*) FROM text_passages",
    "sessions": "SELECT count(*) FROM sessions",
    "session_blocks": "SELECT count(*) FROM session_blocks",
    "keystroke_events": "SELECT count(*) FROM keystroke_events",
}
SEEDED_CONFIG_ROWS = 5


def _table_names(db_path: Path) -> set[str]:
    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    return {row[0] for row in rows}


def _versions(db_path: Path) -> list[str]:
    with closing(sqlite3.connect(db_path)) as connection:
        return [row[0] for row in connection.execute("SELECT version_num FROM alembic_version")]


def _row_counts(db_path: Path) -> dict[str, int]:
    with closing(sqlite3.connect(db_path)) as connection:
        return {
            table: connection.execute(query).fetchone()[0] for table, query in COUNT_QUERIES.items()
        }


def _schema_diff(db_path: Path) -> list[Any]:
    """Alembic autogenerate differences between the database and SQLModel.metadata."""
    engine = create_db_engine(db_path)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection, opts={"compare_type": True})
            return list(compare_metadata(context, SQLModel.metadata))
    finally:
        engine.dispose()


def test_upgrade_head_on_a_new_database_uses_the_configured_database(
    isolated_settings: Path,
) -> None:
    upgrade_to_head()
    assert isolated_settings.is_file()
    with closing(sqlite3.connect(isolated_settings)) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert _versions(isolated_settings) == [HEAD]


def test_upgrade_creates_the_six_tables(isolated_settings: Path) -> None:
    upgrade_to_head()
    assert _table_names(isolated_settings) == APP_TABLES | {"alembic_version"}


def test_downgrade_to_base_leaves_only_an_empty_version_table(isolated_settings: Path) -> None:
    upgrade_to_head()
    command.downgrade(alembic_config(), "base")
    assert _table_names(isolated_settings) == {"alembic_version"}
    assert _versions(isolated_settings) == []


def test_upgrade_downgrade_upgrade_round_trip(isolated_settings: Path) -> None:
    upgrade_to_head()
    command.downgrade(alembic_config(), "base")
    upgrade_to_head()
    assert _table_names(isolated_settings) == APP_TABLES | {"alembic_version"}
    assert _versions(isolated_settings) == [HEAD]
    assert _row_counts(isolated_settings)["experiment_config"] == SEEDED_CONFIG_ROWS
    assert _schema_diff(isolated_settings) == []


def test_downgrade_of_a_populated_database_removes_every_table(
    isolated_settings: Path, migrated_engine: Engine, seeded_ids: dict[str, str]
) -> None:
    migrated_engine.dispose()
    counts = _row_counts(isolated_settings)
    assert all(count >= 1 for count in counts.values()), counts
    with closing(sqlite3.connect(isolated_settings)) as connection:
        assert connection.execute("SELECT id FROM participants").fetchall() == [
            (seeded_ids["participant_id"],)
        ]
    command.downgrade(alembic_config(), "base")
    assert _table_names(isolated_settings) == {"alembic_version"}
    assert _versions(isolated_settings) == []
    upgrade_to_head()
    assert _row_counts(isolated_settings) == {
        table: SEEDED_CONFIG_ROWS if table == "experiment_config" else 0 for table in APP_TABLES
    }


def test_new_revision_is_fixed_and_formatted_by_ruff(tmp_path: Path) -> None:
    script_dir = tmp_path / "alembic"
    shutil.copytree(API_DIR / "alembic", script_dir, ignore=shutil.ignore_patterns("__pycache__"))
    config = alembic_config()
    config.set_main_option("script_location", str(script_dir))
    command.revision(config, message="probe revision", rev_id="0002probe")
    source = (script_dir / "versions" / "0002probe_probe_revision.py").read_text()
    compile(source, "0002probe_probe_revision.py", "exec")
    assert 'revision: str = "0002probe"' in source
    assert f'down_revision: str | Sequence[str] | None = "{HEAD}"' in source
    assert "def upgrade() -> None:" in source
    assert "def downgrade() -> None:" in source
    assert "import sqlmodel" not in source
    assert "import sqlalchemy as sa" not in source


def test_migration_log_lines_are_readable(capsys: pytest.CaptureFixture[str]) -> None:
    upgrade_to_head()
    err = capsys.readouterr().err
    assert "INFO  [alembic.runtime.migration] Context impl SQLiteImpl." in err
    assert (
        f"INFO  [alembic.runtime.migration] Running upgrade  -> {HEAD}, initial schema: "
        "the six section 8.1 tables and the experiment_config defaults"
    ) in err
    assert "%(levelname)" not in err


# Test data written to a temporary copy of alembic/versions. A """ string (ruff Q001), so the
# probe file carries a comment instead of a docstring.
PROBE_REBUILD_REVISION = """# probe: rebuild one table in batch mode

import sqlalchemy as sa
from alembic import op

revision = "0002probe"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("TABLE_NAME", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("probe", sa.Integer(), nullable=True))


def downgrade() -> None:
    pass
"""


def _probe_config(tmp_path: Path, table: str) -> Config:
    """Copy alembic/ to tmp_path and add revision 0002probe, which rebuilds `table` in batch mode.

    The copy runs the real env.py, so the rebuild uses the app's pragmas (foreign_keys=ON) and
    the migration transaction, exactly as a future revision would.
    """
    script_dir = tmp_path / "alembic"
    shutil.copytree(API_DIR / "alembic", script_dir, ignore=shutil.ignore_patterns("__pycache__"))
    probe = PROBE_REBUILD_REVISION.replace("TABLE_NAME", table)
    (script_dir / "versions" / "0002probe_rebuild.py").write_text(probe)
    config = alembic_config()
    config.set_main_option("script_location", str(script_dir))
    return config


def _column_names(connection: sqlite3.Connection, pragma: str) -> list[str]:
    return [row[1] for row in connection.execute(pragma)]


def test_batch_rebuild_of_a_leaf_table_with_rows_succeeds(
    tmp_path: Path, isolated_settings: Path, migrated_engine: Engine, seeded_ids: dict[str, str]
) -> None:
    """keystroke_events is referenced by nothing, so its rebuild keeps rows and foreign keys."""
    migrated_engine.dispose()
    command.upgrade(_probe_config(tmp_path, "keystroke_events"), "0002probe")
    assert _versions(isolated_settings) == ["0002probe"]
    with closing(sqlite3.connect(isolated_settings)) as connection:
        assert "probe" in _column_names(connection, "PRAGMA table_info(keystroke_events)")
        assert connection.execute("SELECT block_id, seq FROM keystroke_events").fetchall() == [
            (seeded_ids["block_id"], 0)
        ]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_batch_rebuild_of_a_parent_table_without_child_rows_succeeds(
    tmp_path: Path, isolated_settings: Path, migrated_engine: Engine
) -> None:
    """participants with no referencing rows: DROP TABLE's implicit delete violates nothing."""
    with Session(migrated_engine) as session:
        session.add(Participant(alias="p01"))
        session.commit()
    migrated_engine.dispose()
    command.upgrade(_probe_config(tmp_path, "participants"), "0002probe")
    assert _versions(isolated_settings) == ["0002probe"]
    with closing(sqlite3.connect(isolated_settings)) as connection:
        assert "probe" in _column_names(connection, "PRAGMA table_info(participants)")
        assert connection.execute("SELECT alias FROM participants").fetchall() == [("p01",)]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_pragma_foreign_keys_cannot_change_inside_a_transaction(tmp_path: Path) -> None:
    """SQLite ignores PRAGMA foreign_keys inside an open transaction, so a revision cannot turn
    foreign-key checks off from within env.py's migration transaction."""
    with closing(sqlite3.connect(tmp_path / "pragma.db", isolation_level=None)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN")
        connection.execute("PRAGMA foreign_keys=OFF")
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        connection.execute("COMMIT")
        connection.execute("PRAGMA foreign_keys=OFF")
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 0


def test_batch_rebuild_of_a_parent_table_with_child_rows_fails_with_foreign_keys_on(
    tmp_path: Path, isolated_settings: Path, migrated_engine: Engine, seeded_ids: dict[str, str]
) -> None:
    """Finding for T1.1 owner answer 20a: render_as_batch does NOT turn foreign-key checks off.

    alembic 1.20.0's batch rebuild creates _alembic_tmp_<table>, copies the rows, then runs
    DROP TABLE on the original. With foreign_keys=ON, SQLite first deletes the table's rows, and
    that fails while child rows reference them. PRAGMA foreign_keys cannot be changed inside the
    migration transaction (see the test above). So a batch rebuild of a referenced table that
    has referencing rows fails, and the revision is not applied.
    """
    migrated_engine.dispose()
    config = _probe_config(tmp_path, "participants")
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        command.upgrade(config, "0002probe")
    assert _versions(isolated_settings) == [HEAD]
    with closing(sqlite3.connect(isolated_settings)) as connection:
        assert connection.execute("SELECT id FROM participants").fetchall() == [
            (seeded_ids["participant_id"],)
        ]
