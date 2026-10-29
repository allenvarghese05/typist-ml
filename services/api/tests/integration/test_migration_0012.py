"""Migration 0012 freezes all 33 experiment_config keys and installs immutability triggers (T3.5)."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import Engine

from typist.migrations import alembic_config

EXPECTED_FROZEN_AT = "2026-10-29 00:00:00"
EXPECTED_SEEDED_KEYS_COUNT = 33
UPDATE_TRIGGER = "trg_experiment_config_frozen_update"
DELETE_TRIGGER = "trg_experiment_config_frozen_delete"


def _triggers(db_path: Path) -> set[str]:
    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
        ).fetchall()
    return {row[0] for row in rows}


def test_0012_freezes_all_seeded_keys(isolated_settings: Path, migrated_engine: Engine) -> None:
    """All 33 seeded keys have frozen_at set to '2026-10-29 00:00:00' and both triggers exist."""
    with closing(sqlite3.connect(isolated_settings)) as connection:
        rows = connection.execute("SELECT key, frozen_at FROM experiment_config").fetchall()
    assert len(rows) == EXPECTED_SEEDED_KEYS_COUNT
    for key, frozen_at in rows:
        assert frozen_at == EXPECTED_FROZEN_AT, f"key {key} was not frozen"

    triggers = _triggers(isolated_settings)
    assert UPDATE_TRIGGER in triggers
    assert DELETE_TRIGGER in triggers


def test_0012_blocks_update_of_a_frozen_key(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    """Updating a frozen key aborts with sqlite3.IntegrityError; value remains unchanged."""
    migrated_engine.dispose()
    with closing(sqlite3.connect(isolated_settings)) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="experiment_config keys are frozen"):
            connection.execute(
                "UPDATE experiment_config SET value = '999' WHERE key = 'practice_days'"
            )
        row = connection.execute(
            "SELECT value, frozen_at FROM experiment_config WHERE key = 'practice_days'"
        ).fetchone()
        assert row is not None
        assert row[0] == "10"
        assert row[1] == EXPECTED_FROZEN_AT

        # Also verify d_min cannot be updated
        with pytest.raises(sqlite3.IntegrityError, match="experiment_config keys are frozen"):
            connection.execute("UPDATE experiment_config SET value = '0.25' WHERE key = 'd_min'")
        row_dmin = connection.execute(
            "SELECT value FROM experiment_config WHERE key = 'd_min'"
        ).fetchone()
        assert row_dmin is not None
        assert row_dmin[0] == "0.1"


def test_0012_blocks_delete_of_a_frozen_key(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    """Deleting a frozen key aborts with sqlite3.IntegrityError; row remains intact."""
    migrated_engine.dispose()
    with closing(sqlite3.connect(isolated_settings)) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="experiment_config keys are frozen"):
            connection.execute("DELETE FROM experiment_config WHERE key = 'assignment_seed'")
        row = connection.execute(
            "SELECT value, frozen_at FROM experiment_config WHERE key = 'assignment_seed'"
        ).fetchone()
        assert row is not None
        assert row[0] == "20261021"


def test_0012_blocks_unfreezing_a_frozen_key(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    """Attempting to unfreeze a key by setting frozen_at = NULL triggers RAISE(ABORT)."""
    migrated_engine.dispose()
    with closing(sqlite3.connect(isolated_settings)) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="experiment_config keys are frozen"):
            connection.execute(
                "UPDATE experiment_config SET frozen_at = NULL WHERE key = 'llm_model_id'"
            )
        row = connection.execute(
            "SELECT frozen_at FROM experiment_config WHERE key = 'llm_model_id'"
        ).fetchone()
        assert row is not None
        assert row[0] == EXPECTED_FROZEN_AT


def test_0012_allows_insert_and_update_of_unfrozen_key(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    """Unfrozen rows (frozen_at IS NULL) can be inserted, modified, and deleted freely."""
    migrated_engine.dispose()
    with closing(sqlite3.connect(isolated_settings)) as connection:
        connection.execute(
            "INSERT INTO experiment_config (key, value, frozen_at) VALUES ('probe_key', '\"initial\"', NULL)"
        )
        connection.commit()

        # Update succeeds on unfrozen row
        connection.execute(
            "UPDATE experiment_config SET value = '\"updated\"' WHERE key = 'probe_key'"
        )
        connection.commit()
        val = connection.execute(
            "SELECT value FROM experiment_config WHERE key = 'probe_key'"
        ).fetchone()[0]
        assert val == '"updated"'

        # Freezing the probe key succeeds
        connection.execute(
            f"UPDATE experiment_config SET frozen_at = '{EXPECTED_FROZEN_AT}' WHERE key = 'probe_key'"
        )
        connection.commit()

        # Now that it is frozen, update aborts
        with pytest.raises(sqlite3.IntegrityError, match="experiment_config keys are frozen"):
            connection.execute(
                "UPDATE experiment_config SET value = '\"blocked\"' WHERE key = 'probe_key'"
            )

        # And delete aborts
        with pytest.raises(sqlite3.IntegrityError, match="experiment_config keys are frozen"):
            connection.execute("DELETE FROM experiment_config WHERE key = 'probe_key'")


def test_downgrade_0012_drops_triggers_and_resets_frozen_at(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    """Downgrade to 0011 drops triggers, resets frozen_at to None, and allows updates."""
    migrated_engine.dispose()
    command.downgrade(alembic_config(), "0011_calibrate_density")
    triggers = _triggers(isolated_settings)
    assert UPDATE_TRIGGER not in triggers
    assert DELETE_TRIGGER not in triggers

    with closing(sqlite3.connect(isolated_settings)) as connection:
        rows = connection.execute("SELECT key, frozen_at FROM experiment_config").fetchall()
        assert len(rows) == EXPECTED_SEEDED_KEYS_COUNT
        assert all(frozen_at is None for _, frozen_at in rows)

        # Updates succeed when unfrozen post-downgrade
        connection.execute("UPDATE experiment_config SET value = '99' WHERE key = 'practice_days'")
        connection.commit()
        val = connection.execute(
            "SELECT value FROM experiment_config WHERE key = 'practice_days'"
        ).fetchone()[0]
        assert val == "99"
