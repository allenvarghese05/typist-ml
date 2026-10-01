"""initial schema: the six section 8.1 tables and the experiment_config defaults

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-29 00:00:00.000000

Tables: participants, experiment_config, text_passages, sessions, session_blocks and
keystroke_events (design doc section 8.1, D24, T1.1 owner answers 2 to 19). Constraint and index
names follow typist.models.base.NAMING_CONVENTION and are written out with op.f(). Column types
are plain SQLAlchemy types, so this file never imports app code; tests/integration/test_schema.py
proves the result matches the SQLModel classes.

JSON columns (experiment_config.value, text_passages.bigram_counts, sessions.client_info) are
declared TEXT and hold json.dumps text: a declared type of JSON has NUMERIC affinity in SQLite
and would store "10" as the integer 10 (T1.1 Revision 3). The models read and write them
through typist.models.base.JSONText, which compiles to TEXT.
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Known defaults (T1.1 owner answer 16), all unfrozen. assignment_seed (T2.2) and model_id (T3.6)
# are added by the tasks that own them.
EXPERIMENT_CONFIG_DEFAULTS: dict[str, object] = {
    "practice_days": 10,
    "block_chars": 600,
    "d_min": 0.15,
    "d_max": 0.40,
    "arms_enabled": ["control", "heuristic", "markov", "llm"],
}


def upgrade() -> None:
    """Create the six tables with their constraints and indexes, then seed experiment_config."""
    op.create_table(
        "participants",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("alias", sa.String(), nullable=False),
        sa.Column("is_builder", sa.Boolean(), nullable=False),
        sa.Column("is_blinded", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("keyboard_label", sa.String(), nullable=True),
        sa.Column("consent_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('enrolled', 'baseline', 'assigned', 'practice', 'retest', 'done', 'withdrawn')",
            name=op.f("ck_participants_status"),
        ),
        sa.CheckConstraint(
            "is_builder = 0 OR is_blinded = 0",
            name=op.f("ck_participants_builder_not_blinded"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_participants")),
        sa.UniqueConstraint("alias", name=op.f("uq_participants_alias")),
    )
    experiment_config = op.create_table(
        "experiment_config",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("frozen_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_experiment_config")),
    )
    op.create_table(
        "text_passages",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("form", sa.String(), nullable=False),
        sa.Column("part", sa.Integer(), nullable=False),
        sa.Column("participant_id", sa.String(), nullable=True),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("bigram_counts", sa.Text(), nullable=False),
        sa.CheckConstraint("kind IN ('baseline', 'retest')", name=op.f("ck_text_passages_kind")),
        sa.CheckConstraint("form IN ('A', 'B')", name=op.f("ck_text_passages_form")),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["participants.id"],
            name=op.f("fk_text_passages_participant_id_participants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_text_passages")),
    )
    op.create_index(
        op.f("uq_text_passages_shared_kind_form_part"),
        "text_passages",
        ["kind", "form", "part"],
        unique=True,
        sqlite_where=sa.text("participant_id IS NULL"),
    )
    op.create_index(
        op.f("uq_text_passages_participant_kind_form_part"),
        "text_passages",
        ["kind", "form", "part", "participant_id"],
        unique=True,
        sqlite_where=sa.text("participant_id IS NOT NULL"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("participant_id", sa.String(), nullable=False),
        sa.Column("phase", sa.String(), nullable=False),
        sa.Column("day_index", sa.Integer(), nullable=False),
        sa.Column("block_order", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("wpm", sa.Float(), nullable=True),
        sa.Column("accuracy", sa.Float(), nullable=True),
        sa.Column("client_info", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "phase IN ('baseline', 'practice', 'retest')", name=op.f("ck_sessions_phase")
        ),
        sa.CheckConstraint(
            "status IN ('in_progress', 'completed', 'abandoned')", name=op.f("ck_sessions_status")
        ),
        sa.CheckConstraint("day_index >= 1", name=op.f("ck_sessions_day_index")),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["participants.id"],
            name=op.f("fk_sessions_participant_id_participants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
    )
    op.create_index(
        op.f("ix_sessions_participant_id_phase_day_index"),
        "sessions",
        ["participant_id", "phase", "day_index"],
        unique=False,
    )
    op.create_table(
        "session_blocks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("block_index", sa.Integer(), nullable=False),
        sa.Column("arm", sa.String(), nullable=False),
        sa.Column("passage_id", sa.String(), nullable=True),
        sa.Column("target_text", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "arm IN ('test', 'control', 'heuristic', 'markov', 'llm')",
            name=op.f("ck_session_blocks_arm"),
        ),
        sa.CheckConstraint("block_index >= 0", name=op.f("ck_session_blocks_block_index")),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.id"], name=op.f("fk_session_blocks_session_id_sessions")
        ),
        sa.ForeignKeyConstraint(
            ["passage_id"],
            ["text_passages.id"],
            name=op.f("fk_session_blocks_passage_id_text_passages"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_session_blocks")),
        sa.UniqueConstraint(
            "session_id", "block_index", name=op.f("uq_session_blocks_session_id_block_index")
        ),
    )
    op.create_table(
        "keystroke_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("block_id", sa.String(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("t_down_ms", sa.Float(), nullable=False),
        sa.Column("t_up_ms", sa.Float(), nullable=True),
        sa.Column("dwell_ms", sa.Float(), nullable=True),
        sa.Column("iki_ms", sa.Float(), nullable=True),
        sa.Column("release_to_press_ms", sa.Float(), nullable=True),
        sa.Column("target_index", sa.Integer(), nullable=False),
        sa.Column("expected_char", sa.String(), nullable=True),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("first_attempt", sa.Boolean(), nullable=True),
        sa.Column("after_pause", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("handler_ms", sa.Float(), nullable=False),
        sa.Column("dispatch_lag_ms", sa.Float(), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('correct', 'error', 'backspace')",
            name=op.f("ck_keystroke_events_outcome"),
        ),
        sa.CheckConstraint("seq >= 0", name=op.f("ck_keystroke_events_seq")),
        sa.ForeignKeyConstraint(
            ["block_id"],
            ["session_blocks.id"],
            name=op.f("fk_keystroke_events_block_id_session_blocks"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_keystroke_events")),
        sa.UniqueConstraint("block_id", "seq", name=op.f("uq_keystroke_events_block_id_seq")),
    )
    op.bulk_insert(
        experiment_config,
        [
            {"key": key, "value": json.dumps(value), "frozen_at": None}
            for key, value in EXPERIMENT_CONFIG_DEFAULTS.items()
        ],
    )


def downgrade() -> None:
    """Drop the six tables, children before parents.

    With foreign_keys=ON, DROP TABLE first deletes the table's rows, which fails while child rows
    still reference them; this order never has children left. This deletes all participant data;
    there is deliberately no CLI command for it (T1.1 owner answer 18).
    """
    op.drop_table("keystroke_events")
    op.drop_table("session_blocks")
    op.drop_table("sessions")
    op.drop_table("text_passages")
    op.drop_table("experiment_config")
    op.drop_table("participants")
