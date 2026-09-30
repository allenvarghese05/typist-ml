"""The migrated schema (revision 0001) against the SQLModel classes and T1.1 owner answers 4-19."""

import json
import re
import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import CheckConstraint, Engine
from sqlalchemy.exc import StatementError
from sqlmodel import Session, SQLModel

from typist.db import utc_now
from typist.models import ExperimentConfig, KeystrokeEvent, Participant

EXPECTED_NAMES: dict[str, set[str]] = {
    "participants": {
        "pk_participants",
        "uq_participants_alias",
        "ck_participants_status",
        "ck_participants_builder_not_blinded",
    },
    "experiment_config": {"pk_experiment_config"},
    "text_passages": {
        "pk_text_passages",
        "fk_text_passages_participant_id_participants",
        "ck_text_passages_kind",
        "ck_text_passages_form",
        "uq_text_passages_shared_kind_form_part",
        "uq_text_passages_participant_kind_form_part",
    },
    "sessions": {
        "pk_sessions",
        "fk_sessions_participant_id_participants",
        "ck_sessions_phase",
        "ck_sessions_status",
        "ck_sessions_day_index",
        "ix_sessions_participant_id_phase_day_index",
    },
    "session_blocks": {
        "pk_session_blocks",
        "fk_session_blocks_session_id_sessions",
        "fk_session_blocks_passage_id_text_passages",
        "uq_session_blocks_session_id_block_index",
        "ck_session_blocks_arm",
        "ck_session_blocks_block_index",
    },
    "keystroke_events": {
        "pk_keystroke_events",
        "fk_keystroke_events_block_id_session_blocks",
        "uq_keystroke_events_block_id_seq",
        "ck_keystroke_events_outcome",
        "ck_keystroke_events_seq",
    },
}

EXPECTED_CHECKS: dict[str, str] = {
    "ck_participants_status": (
        "status IN ('enrolled', 'baseline', 'assigned', 'practice', 'retest', 'done', 'withdrawn')"
    ),
    "ck_participants_builder_not_blinded": "is_builder = 0 OR is_blinded = 0",
    "ck_text_passages_kind": "kind IN ('baseline', 'retest')",
    "ck_text_passages_form": "form IN ('A', 'B')",
    "ck_sessions_phase": "phase IN ('baseline', 'practice', 'retest')",
    "ck_sessions_status": "status IN ('in_progress', 'completed', 'abandoned')",
    "ck_sessions_day_index": "day_index >= 1",
    "ck_session_blocks_arm": "arm IN ('test', 'control', 'heuristic', 'markov', 'llm')",
    "ck_session_blocks_block_index": "block_index >= 0",
    "ck_keystroke_events_outcome": "outcome IN ('correct', 'error', 'backspace')",
    "ck_keystroke_events_seq": "seq >= 0",
}

EXPECTED_CONFIG: dict[str, object] = {
    "practice_days": 10,
    "block_chars": 600,
    "d_min": 0.15,
    "d_max": 0.40,
    "arms_enabled": ["control", "heuristic", "markov", "llm"],
}

# Assumption C: CURRENT_TIMESTAMP writes whole seconds, Python writes microseconds.
STORED_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d{6})?$")

# Each INSERT is valid except for one value, which its CHECK must reject. Each multi-line string
# is wrapped in its own parentheses (ruff ISC004).
CHECK_VIOLATIONS: list[tuple[str, str]] = [
    (
        (
            "INSERT INTO participants (id, alias, is_builder, is_blinded, status) "
            "VALUES ('bad', 'p99', 0, 1, 'active')"
        ),
        "ck_participants_status",
    ),
    (
        (
            "INSERT INTO participants (id, alias, is_builder, is_blinded, status) "
            "VALUES ('bad', 'p99', 1, 1, 'enrolled')"
        ),
        "ck_participants_builder_not_blinded",
    ),
    (
        (
            "INSERT INTO text_passages (id, kind, form, part, text, bigram_counts) "
            "VALUES ('bad', 'practice', 'A', 9, 'ab', '{}')"
        ),
        "ck_text_passages_kind",
    ),
    (
        (
            "INSERT INTO text_passages (id, kind, form, part, text, bigram_counts) "
            "VALUES ('bad', 'baseline', 'C', 9, 'ab', '{}')"
        ),
        "ck_text_passages_form",
    ),
    (
        (
            "INSERT INTO sessions (id, participant_id, phase, day_index, status, client_info, "
            "started_at) VALUES ('bad', :participant_id, 'warmup', 2, 'in_progress', '{}', "
            "'2026-09-29 09:00:00.000000')"
        ),
        "ck_sessions_phase",
    ),
    (
        (
            "INSERT INTO sessions (id, participant_id, phase, day_index, status, client_info, "
            "started_at) VALUES ('bad', :participant_id, 'baseline', 2, 'complete', '{}', "
            "'2026-09-29 09:00:00.000000')"
        ),
        "ck_sessions_status",
    ),
    (
        (
            "INSERT INTO sessions (id, participant_id, phase, day_index, status, client_info, "
            "started_at) VALUES ('bad', :participant_id, 'baseline', 0, 'in_progress', '{}', "
            "'2026-09-29 09:00:00.000000')"
        ),
        "ck_sessions_day_index",
    ),
    (
        (
            "INSERT INTO session_blocks (id, session_id, block_index, arm, target_text) "
            "VALUES ('bad', :session_id, 1, 'random', 'ab')"
        ),
        "ck_session_blocks_arm",
    ),
    (
        (
            "INSERT INTO session_blocks (id, session_id, block_index, arm, target_text) "
            "VALUES ('bad', :session_id, -1, 'test', 'ab')"
        ),
        "ck_session_blocks_block_index",
    ),
    (
        (
            "INSERT INTO keystroke_events (block_id, seq, key, code, t_down_ms, target_index, "
            "outcome, handler_ms, dispatch_lag_ms) "
            "VALUES (:block_id, 1, 'a', 'KeyA', 1.0, 1, 'miss', 0.1, 0.1)"
        ),
        "ck_keystroke_events_outcome",
    ),
    (
        (
            "INSERT INTO keystroke_events (block_id, seq, key, code, t_down_ms, target_index, "
            "outcome, handler_ms, dispatch_lag_ms) "
            "VALUES (:block_id, -1, 'a', 'KeyA', 1.0, 1, 'correct', 0.1, 0.1)"
        ),
        "ck_keystroke_events_seq",
    ),
]

ID_QUERIES = (
    "SELECT typeof(id), length(id), id FROM participants",
    "SELECT typeof(id), length(id), id FROM text_passages",
    "SELECT typeof(id), length(id), id FROM sessions",
    "SELECT typeof(id), length(id), id FROM session_blocks",
)

KEYSTROKE_INSERT = (
    "INSERT INTO keystroke_events (id, block_id, seq, key, code, t_down_ms, target_index, "
    "outcome, handler_ms, dispatch_lag_ms) "
    "VALUES (:id, :block_id, :seq, 'h', 'KeyH', 950.0, 1, 'correct', 0.1, 0.1)"
)
# A complete literal, not KEYSTROKE_INSERT + "...": semgrep flags SQL built by concatenation.
KEYSTROKE_UPSERT = (
    "INSERT INTO keystroke_events (id, block_id, seq, key, code, t_down_ms, target_index, "
    "outcome, handler_ms, dispatch_lag_ms) "
    "VALUES (:id, :block_id, :seq, 'h', 'KeyH', 950.0, 1, 'correct', 0.1, 0.1) "
    "ON CONFLICT (block_id, seq) DO NOTHING"
)


def _connect(db_path: Path) -> sqlite3.Connection:
    """A raw connection with foreign keys on, as the app has, for writes that bypass the ORM."""
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _schema_sql(db_path: Path) -> str:
    """All CREATE TABLE and CREATE INDEX statements, joined."""
    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL").fetchall()
    return "\n".join(row[0] for row in rows)


def test_migrated_schema_matches_the_models(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, SQLModel.metadata) == []


def test_model_constraint_and_index_names_follow_the_convention() -> None:
    for table_name, expected in EXPECTED_NAMES.items():
        table = SQLModel.metadata.tables[table_name]
        names = {str(c.name) for c in table.constraints} | {str(i.name) for i in table.indexes}
        assert names == expected, table_name


@pytest.mark.usefixtures("migrated_engine")
def test_migrated_constraint_and_index_names_match(isolated_settings: Path) -> None:
    sql = _schema_sql(isolated_settings)
    for expected in EXPECTED_NAMES.values():
        for name in expected:
            assert name in sql, name


@pytest.mark.usefixtures("migrated_engine")
def test_check_constraints_are_identical_in_models_and_migration(isolated_settings: Path) -> None:
    model_checks = {
        str(constraint.name): str(constraint.sqltext)
        for table in SQLModel.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert model_checks == EXPECTED_CHECKS
    sql = _schema_sql(isolated_settings)
    for name, sqltext in EXPECTED_CHECKS.items():
        assert f"CONSTRAINT {name} CHECK ({sqltext})" in sql, name


@pytest.mark.usefixtures("migrated_engine")
def test_partial_unique_indexes_have_their_where_clauses(isolated_settings: Path) -> None:
    with closing(sqlite3.connect(isolated_settings)) as connection:
        rows = dict(
            connection.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type = 'index' AND tbl_name = 'text_passages' AND sql IS NOT NULL"
            ).fetchall()
        )
    shared = rows["uq_text_passages_shared_kind_form_part"]
    own = rows["uq_text_passages_participant_kind_form_part"]
    assert shared.startswith("CREATE UNIQUE INDEX")
    assert shared.endswith("WHERE participant_id IS NULL")
    assert own.startswith("CREATE UNIQUE INDEX")
    assert own.endswith("WHERE participant_id IS NOT NULL")


def test_experiment_config_holds_the_seeded_defaults(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    with closing(sqlite3.connect(isolated_settings)) as connection:
        rows = connection.execute("SELECT key, value, frozen_at FROM experiment_config").fetchall()
    assert {key: json.loads(value) for key, value, _ in rows} == EXPECTED_CONFIG
    assert [frozen_at for _, _, frozen_at in rows] == [None] * len(EXPECTED_CONFIG)
    with Session(migrated_engine) as session:
        arms = session.get(ExperimentConfig, "arms_enabled")
        assert arms is not None
        assert arms.value == ["control", "heuristic", "markov", "llm"]


@pytest.mark.parametrize(
    ("sql", "constraint"), CHECK_VIOLATIONS, ids=[name for _, name in CHECK_VIOLATIONS]
)
def test_check_constraint_rejects_a_bad_value(
    isolated_settings: Path, seeded_ids: dict[str, str], sql: str, constraint: str
) -> None:
    params = {key: value for key, value in seeded_ids.items() if f":{key}" in sql}
    with (
        closing(_connect(isolated_settings)) as connection,
        pytest.raises(sqlite3.IntegrityError, match=f"CHECK constraint failed: {constraint}"),
    ):
        connection.execute(sql, params)


def test_block_index_has_no_upper_bound(
    isolated_settings: Path, seeded_ids: dict[str, str]
) -> None:
    with closing(_connect(isolated_settings)) as connection, connection:
        connection.execute(
            "INSERT INTO session_blocks (id, session_id, block_index, arm, target_text) "
            "VALUES ('b4', :session_id, 4, 'test', 'ab')",
            {"session_id": seeded_ids["session_id"]},
        )
    with closing(sqlite3.connect(isolated_settings)) as connection:
        row = connection.execute("SELECT block_index FROM session_blocks WHERE id = 'b4'")
        assert row.fetchone()[0] == 4


@pytest.mark.usefixtures("migrated_engine")
def test_foreign_keys_reject_a_missing_parent(isolated_settings: Path) -> None:
    with (
        closing(_connect(isolated_settings)) as connection,
        pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"),
    ):
        connection.execute(
            "INSERT INTO sessions (id, participant_id, phase, day_index, status, client_info, "
            "started_at) VALUES ('s', 'missing', 'baseline', 1, 'in_progress', '{}', "
            "'2026-09-29 09:00:00.000000')"
        )


@pytest.mark.usefixtures("seeded_ids")
def test_alias_is_unique(isolated_settings: Path) -> None:
    with (
        closing(_connect(isolated_settings)) as connection,
        pytest.raises(
            sqlite3.IntegrityError,
            match=re.escape("UNIQUE constraint failed: participants.alias"),
        ),
    ):
        connection.execute(
            "INSERT INTO participants (id, alias, is_builder, is_blinded, status) "
            "VALUES ('p-2', 'p01', 0, 1, 'enrolled')"
        )


def test_block_seq_is_unique(isolated_settings: Path, seeded_ids: dict[str, str]) -> None:
    with (
        closing(_connect(isolated_settings)) as connection,
        pytest.raises(
            sqlite3.IntegrityError,
            match=re.escape(
                "UNIQUE constraint failed: keystroke_events.block_id, keystroke_events.seq"
            ),
        ),
    ):
        connection.execute(
            KEYSTROKE_INSERT, {"id": None, "block_id": seeded_ids["block_id"], "seq": 0}
        )


def test_on_conflict_do_nothing_stores_a_repeated_keystroke_once(
    isolated_settings: Path, seeded_ids: dict[str, str]
) -> None:
    params = {"id": None, "block_id": seeded_ids["block_id"], "seq": 1}
    with closing(_connect(isolated_settings)) as connection, connection:
        first = connection.execute(KEYSTROKE_UPSERT, params).rowcount
        second = connection.execute(KEYSTROKE_UPSERT, params).rowcount
    assert (first, second) == (1, 0)
    with closing(sqlite3.connect(isolated_settings)) as connection:
        count = connection.execute("SELECT count(*) FROM keystroke_events WHERE seq = 1")
        assert count.fetchone()[0] == 1


def test_block_index_is_unique_per_session(
    isolated_settings: Path, seeded_ids: dict[str, str]
) -> None:
    with (
        closing(_connect(isolated_settings)) as connection,
        pytest.raises(
            sqlite3.IntegrityError,
            match=re.escape(
                "UNIQUE constraint failed: session_blocks.session_id, session_blocks.block_index"
            ),
        ),
    ):
        connection.execute(
            "INSERT INTO session_blocks (id, session_id, block_index, arm, target_text) "
            "VALUES ('b0', :session_id, 0, 'test', 'ab')",
            {"session_id": seeded_ids["session_id"]},
        )


@pytest.mark.usefixtures("seeded_ids")
def test_shared_passages_are_unique_by_kind_form_part(isolated_settings: Path) -> None:
    with (
        closing(_connect(isolated_settings)) as connection,
        pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed"),
    ):
        connection.execute(
            "INSERT INTO text_passages (id, kind, form, part, text, bigram_counts) "
            "VALUES ('dup', 'baseline', 'A', 0, 'ab', '{}')"
        )


def test_participant_passages_are_unique_per_participant(
    isolated_settings: Path, seeded_ids: dict[str, str]
) -> None:
    own = (
        "INSERT INTO text_passages (id, kind, form, part, participant_id, text, bigram_counts) "
        "VALUES (?, 'retest', 'B', 0, ?, 'ab', '{}')"
    )
    with closing(_connect(isolated_settings)) as connection, connection:
        connection.execute(own, ("r1", seeded_ids["participant_id"]))
        connection.execute(
            "INSERT INTO participants (id, alias, is_builder, is_blinded, status) "
            "VALUES ('p-2', 'p02', 0, 1, 'enrolled')"
        )
        connection.execute(own, ("r2", "p-2"))
        connection.execute(
            "INSERT INTO text_passages (id, kind, form, part, text, bigram_counts) "
            "VALUES ('r3', 'retest', 'B', 0, 'ab', '{}')"
        )
    with (
        closing(_connect(isolated_settings)) as connection,
        pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed"),
    ):
        connection.execute(own, ("r4", seeded_ids["participant_id"]))


def test_keystroke_rows_store_space_backspace_and_negative_release_to_press(
    isolated_settings: Path, migrated_engine: Engine, seeded_ids: dict[str, str]
) -> None:
    block_id = seeded_ids["block_id"]
    with Session(migrated_engine) as session:
        session.add(
            KeystrokeEvent(
                block_id=block_id,
                seq=1,
                key=" ",
                code="Space",
                t_down_ms=60.0,
                iki_ms=60.0,
                release_to_press_ms=-35.0,
                target_index=1,
                expected_char=" ",
                outcome="correct",
                first_attempt=True,
                handler_ms=0.3,
                dispatch_lag_ms=0.9,
            )
        )
        session.add(
            KeystrokeEvent(
                block_id=block_id,
                seq=2,
                key="Backspace",
                code="Backspace",
                t_down_ms=300.0,
                iki_ms=240.0,
                target_index=2,
                outcome="backspace",
                handler_ms=0.2,
                dispatch_lag_ms=0.8,
            )
        )
        session.commit()
    with closing(sqlite3.connect(isolated_settings)) as connection:
        rows = connection.execute(
            "SELECT seq, key, t_up_ms, dwell_ms, release_to_press_ms, expected_char, "
            "first_attempt, after_pause FROM keystroke_events WHERE seq IN (1, 2) ORDER BY seq"
        ).fetchall()
    assert rows == [
        (1, " ", None, None, -35.0, " ", 1, 0),
        (2, "Backspace", None, None, None, None, None, 0),
    ]


def test_after_pause_defaults_to_false_in_the_database(
    isolated_settings: Path, migrated_engine: Engine, seeded_ids: dict[str, str]
) -> None:
    with closing(_connect(isolated_settings)) as connection, connection:
        connection.execute(
            KEYSTROKE_INSERT, {"id": None, "block_id": seeded_ids["block_id"], "seq": 3}
        )
    with Session(migrated_engine) as session:
        session.add(
            KeystrokeEvent(
                block_id=seeded_ids["block_id"],
                seq=4,
                key="e",
                code="KeyE",
                t_down_ms=2000.0,
                target_index=2,
                expected_char="e",
                outcome="correct",
                first_attempt=True,
                after_pause=True,
                handler_ms=0.1,
                dispatch_lag_ms=0.1,
            )
        )
        session.commit()
    with closing(sqlite3.connect(isolated_settings)) as connection:
        rows = connection.execute(
            "SELECT seq, after_pause FROM keystroke_events WHERE seq IN (3, 4) ORDER BY seq"
        ).fetchall()
    assert rows == [(3, 0), (4, 1)]


def test_keystroke_event_id_is_the_sqlite_rowid(
    isolated_settings: Path, seeded_ids: dict[str, str]
) -> None:
    with closing(_connect(isolated_settings)) as connection, connection:
        connection.execute(
            KEYSTROKE_INSERT, {"id": 10, "block_id": seeded_ids["block_id"], "seq": 1}
        )
    with closing(sqlite3.connect(isolated_settings)) as connection:
        pairs = connection.execute("SELECT id, rowid FROM keystroke_events ORDER BY id").fetchall()
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'keystroke_events'"
        ).fetchone()[0]
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
    assert pairs == [(1, 1), (10, 10)]
    assert "AUTOINCREMENT" not in table_sql.upper()
    assert "sqlite_sequence" not in tables


def test_ids_are_36_character_uuid4_text(
    isolated_settings: Path, seeded_ids: dict[str, str]
) -> None:
    with closing(sqlite3.connect(isolated_settings)) as connection:
        for query in ID_QUERIES:
            rows = connection.execute(query).fetchall()
            assert len(rows) == 1, query
            kind, length, value = rows[0]
            assert (kind, length) == ("text", 36), query
            assert uuid.UUID(value).version == 4
            assert value in seeded_ids.values()


def test_timestamps_round_trip_as_aware_utc(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    consent = datetime(2026, 9, 29, 14, 3, 5, 123456, tzinfo=UTC)
    created = datetime(2026, 9, 29, 14, 0, 0, 654321, tzinfo=UTC)
    with Session(migrated_engine) as session:
        participant = Participant(alias="p01", consent_at=consent, created_at=created)
        participant_id = participant.id
        session.add(participant)
        session.commit()
    with Session(migrated_engine) as session:
        stored = session.get(Participant, participant_id)
        assert stored is not None
        assert stored.consent_at == consent
        assert stored.created_at == created
        assert stored.consent_at is not None
        assert stored.consent_at.utcoffset() == timedelta(0)
    with closing(sqlite3.connect(isolated_settings)) as connection:
        raw = connection.execute(
            "SELECT consent_at, created_at FROM participants WHERE id = ?", (participant_id,)
        ).fetchone()
    assert raw == ("2026-09-29 14:03:05.123456", "2026-09-29 14:00:00.654321")
    assert all(STORED_TIMESTAMP.match(value) for value in raw)


def test_created_at_defaults_to_the_database_clock(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    before = utc_now().replace(microsecond=0) - timedelta(seconds=1)
    with closing(_connect(isolated_settings)) as connection, connection:
        connection.execute(
            "INSERT INTO participants (id, alias, is_builder, is_blinded, status) "
            "VALUES ('p-raw', 'p98', 0, 1, 'enrolled')"
        )
    with Session(migrated_engine) as session:
        orm_participant = Participant(alias="p97")
        session.add(orm_participant)
        session.commit()
        session.refresh(orm_participant)
        raw_participant = session.get(Participant, "p-raw")
        assert raw_participant is not None
        values = [orm_participant.created_at, raw_participant.created_at]
    after = utc_now() + timedelta(seconds=1)
    for value in values:
        assert value is not None
        assert value.utcoffset() == timedelta(0)
        assert before <= value <= after
    with closing(sqlite3.connect(isolated_settings)) as connection:
        stored = [row[0] for row in connection.execute("SELECT created_at FROM participants")]
    assert len(stored) == 2
    assert all(STORED_TIMESTAMP.match(value) for value in stored)


def test_naive_datetimes_are_rejected_on_write(migrated_engine: Engine) -> None:
    # Deliberately naive: built aware (ruff DTZ001), then the tzinfo is dropped.
    naive = datetime(2026, 9, 29, 14, 3, 5, tzinfo=UTC).replace(tzinfo=None)
    with Session(migrated_engine) as session:
        session.add(Participant(alias="p01", consent_at=naive))
        with pytest.raises(StatementError, match="timezone"):
            session.commit()
