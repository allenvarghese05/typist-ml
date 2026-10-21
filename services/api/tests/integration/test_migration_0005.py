"""Migration 0005 seeds the five assignment config keys and installs the freeze trigger; its
downgrade removes both, leaving 0001-0004 intact (T2.2)."""

import sqlite3
from contextlib import closing
from pathlib import Path

from alembic import command
from sqlalchemy import Engine

from typist.migrations import alembic_config

NEW_KEYS = {
    "assignment_seed": 20261021,
    "assignment_prior_strength": 20,
    "assignment_min_observations": 15,
    "assignment_per_set": 4,
    "assignment_per_set_fallback": 3,
}
TRIGGER = "trg_bigram_assignment_frozen"


def _config(db_path: Path) -> dict[str, object]:
    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute("SELECT key, value FROM experiment_config").fetchall()
    import json

    return {key: json.loads(value) for key, value in rows}


def _triggers(db_path: Path) -> set[str]:
    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
        ).fetchall()
    return {row[0] for row in rows}


def test_0005_seeds_the_five_keys_and_installs_the_trigger(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    config = _config(isolated_settings)
    for key, value in NEW_KEYS.items():
        assert config[key] == value
    assert TRIGGER in _triggers(isolated_settings)


def test_0005_trigger_blocks_update_of_a_frozen_row(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    migrated_engine.dispose()
    with closing(sqlite3.connect(isolated_settings)) as connection:
        connection.execute(
            "INSERT INTO participants (id, alias, is_builder, is_blinded, status) "
            "VALUES ('p9', 'p9', 0, 1, 'enrolled')"
        )
        connection.execute(
            "INSERT INTO bigram_assignment (participant_id, bigram, set_label, arm, "
            "baseline_rank, weakness_score, baseline_attempts, baseline_errors, frozen_at) "
            "VALUES ('p9', 'th', 'A', 'control', 1, 0.5, 30, 2, '2026-10-21 12:00:00')"
        )
        connection.commit()
        try:
            connection.execute("UPDATE bigram_assignment SET arm = 'llm' WHERE participant_id = 'p9'")
        except sqlite3.IntegrityError as error:
            assert "frozen" in str(error)
        else:  # pragma: no cover - the trigger must abort
            raise AssertionError("the freeze trigger did not block the UPDATE")
        arm = connection.execute(
            "SELECT arm FROM bigram_assignment WHERE participant_id = 'p9'"
        ).fetchone()[0]
        assert arm == "control"  # unchanged


def test_downgrade_0005_removes_keys_and_trigger(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    migrated_engine.dispose()
    command.downgrade(alembic_config(), "0004_m2_tables")
    config = _config(isolated_settings)
    assert all(key not in config for key in NEW_KEYS)
    assert TRIGGER not in _triggers(isolated_settings)
    # 0001/0002 keys survive.
    assert config["practice_days"] == 10
    assert config["baseline_min_occurrences"] == 15
