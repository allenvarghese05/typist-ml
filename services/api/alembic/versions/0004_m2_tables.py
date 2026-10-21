"""m2 tables: bigram_assignment, drills, generation_jobs, generation_attempts (design doc 8.1, 8.2).

Revision ID: 0004_m2_tables
Revises: 0003_bigram_stats
Create Date: 2026-10-21 00:00:00.000000

Adds the four remaining M2 tables (bigram_stats was created in 0003_bigram_stats; T1.9 owner answer 1).
bigram_assignment has the composite PK (participant_id, bigram) -- the first composite PK in the
schema. Indexes (8.2): drills (participant_id, arm, status); generation_jobs (status, created_at);
generation_attempts (job_id). Constraint and index names follow typist.models.base.NAMING_CONVENTION,
written out with op.f(). Column types are plain SQLAlchemy types, so this file imports no app code;
tests/integration/test_schema.py proves the result matches the SQLModel classes. Downgrade drops the
four tables children-first (with foreign_keys=ON, DROP TABLE first deletes rows, which fails while
child rows still reference them).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_m2_tables"
down_revision: str | Sequence[str] | None = "0003_bigram_stats"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the four tables with their constraints and indexes (parents before children)."""
    op.create_table(
        "bigram_assignment",
        sa.Column("participant_id", sa.String(), nullable=False),
        sa.Column("bigram", sa.String(), nullable=False),
        sa.Column("set_label", sa.String(), nullable=False),
        sa.Column("arm", sa.String(), nullable=False),
        sa.Column("baseline_rank", sa.Integer(), nullable=False),
        sa.Column("weakness_score", sa.Float(), nullable=False),
        sa.Column("baseline_attempts", sa.Integer(), nullable=False),
        sa.Column("baseline_errors", sa.Integer(), nullable=False),
        sa.Column("frozen_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "set_label IN ('A', 'B', 'C', 'D')", name=op.f("ck_bigram_assignment_set_label")
        ),
        sa.CheckConstraint(
            "arm IN ('control', 'heuristic', 'markov', 'llm')",
            name=op.f("ck_bigram_assignment_arm"),
        ),
        sa.CheckConstraint("length(bigram) = 2", name=op.f("ck_bigram_assignment_bigram")),
        sa.CheckConstraint("baseline_rank >= 1", name=op.f("ck_bigram_assignment_baseline_rank")),
        sa.CheckConstraint(
            "baseline_attempts >= 0", name=op.f("ck_bigram_assignment_baseline_attempts")
        ),
        sa.CheckConstraint(
            "baseline_errors >= 0", name=op.f("ck_bigram_assignment_baseline_errors")
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["participants.id"],
            name=op.f("fk_bigram_assignment_participant_id_participants"),
        ),
        sa.PrimaryKeyConstraint("participant_id", "bigram", name=op.f("pk_bigram_assignment")),
    )
    op.create_table(
        "drills",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("participant_id", sa.String(), nullable=False),
        sa.Column("arm", sa.String(), nullable=False),
        sa.Column("target_bigrams", sa.Text(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("target_density", sa.Float(), nullable=False),
        sa.Column("mean_word_len", sa.Float(), nullable=False),
        sa.Column("real_word_ratio", sa.Float(), nullable=False),
        sa.Column("generator_version", sa.String(), nullable=False),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("prompt_version", sa.String(), nullable=True),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("used_in_block_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "arm IN ('control', 'heuristic', 'markov', 'llm')", name=op.f("ck_drills_arm")
        ),
        sa.CheckConstraint("status IN ('ready', 'used', 'retired')", name=op.f("ck_drills_status")),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["participants.id"],
            name=op.f("fk_drills_participant_id_participants"),
        ),
        sa.ForeignKeyConstraint(
            ["used_in_block_id"],
            ["session_blocks.id"],
            name=op.f("fk_drills_used_in_block_id_session_blocks"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_drills")),
    )
    op.create_index(
        op.f("ix_drills_participant_id_arm_status"),
        "drills",
        ["participant_id", "arm", "status"],
        unique=False,
    )
    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("participant_id", sa.String(), nullable=False),
        sa.Column("arm", sa.String(), nullable=False),
        sa.Column("requested", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("retries", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "arm IN ('control', 'heuristic', 'markov', 'llm')",
            name=op.f("ck_generation_jobs_arm"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'done', 'failed')",
            name=op.f("ck_generation_jobs_status"),
        ),
        sa.CheckConstraint("requested >= 1", name=op.f("ck_generation_jobs_requested")),
        sa.CheckConstraint("retries >= 0", name=op.f("ck_generation_jobs_retries")),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["participants.id"],
            name=op.f("fk_generation_jobs_participant_id_participants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generation_jobs")),
    )
    op.create_index(
        op.f("ix_generation_jobs_status_created_at"),
        "generation_jobs",
        ["status", "created_at"],
        unique=False,
    )
    op.create_table(
        "generation_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("drill_id", sa.String(), nullable=True),
        sa.Column("raw_output", sa.String(), nullable=False),
        sa.Column("clean_text", sa.String(), nullable=False),
        sa.Column("density", sa.Float(), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("reject_reasons", sa.Text(), nullable=False),
        sa.Column("gen_ms", sa.Float(), nullable=True),
        sa.Column("gen_tokens", sa.Integer(), nullable=True),
        sa.Column("tokens_per_sec", sa.Float(), nullable=True),
        sa.Column("peak_memory_mb", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["generation_jobs.id"],
            name=op.f("fk_generation_attempts_job_id_generation_jobs"),
        ),
        sa.ForeignKeyConstraint(
            ["drill_id"], ["drills.id"], name=op.f("fk_generation_attempts_drill_id_drills")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generation_attempts")),
    )
    op.create_index(
        op.f("ix_generation_attempts_job_id"),
        "generation_attempts",
        ["job_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the four tables, children before parents (indexes dropped explicitly first)."""
    op.drop_index(op.f("ix_generation_attempts_job_id"), table_name="generation_attempts")
    op.drop_table("generation_attempts")
    op.drop_index(op.f("ix_generation_jobs_status_created_at"), table_name="generation_jobs")
    op.drop_table("generation_jobs")
    op.drop_index(op.f("ix_drills_participant_id_arm_status"), table_name="drills")
    op.drop_table("drills")
    op.drop_table("bigram_assignment")
