"""bigram_stats: the per-session derived per-bigram table (design doc 8.1, 8.2; T1.9).

Revision ID: 0003_bigram_stats
Revises: 0002_baseline_config
Create Date: 2026-10-19 00:00:00.000000

Creates bigram_stats with UNIQUE (session_id, bigram), index (participant_id, bigram) and the
CHECKs attempts>=0, errors>=0, iki_n>=0, length(bigram)=2. Constraint and index names follow
typist.models.base.NAMING_CONVENTION, written out with op.f(). Column types are plain SQLAlchemy
types, so this file imports no app code; tests/integration/test_schema.py proves the result
matches the SQLModel class. Downgrade drops the table (and its index). The design doc lists this
table under T2.1, but T1.9 needs it for its acceptance (T1.9 brief owner answer 1).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_bigram_stats"
down_revision: str | Sequence[str] | None = "0002_baseline_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create bigram_stats with its unique constraint, index and checks."""
    op.create_table(
        "bigram_stats",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("participant_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("bigram", sa.String(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("errors", sa.Integer(), nullable=False),
        sa.Column("iki_median_ms", sa.Float(), nullable=True),
        sa.Column("iki_n", sa.Integer(), nullable=False),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_bigram_stats_attempts")),
        sa.CheckConstraint("errors >= 0", name=op.f("ck_bigram_stats_errors")),
        sa.CheckConstraint("iki_n >= 0", name=op.f("ck_bigram_stats_iki_n")),
        sa.CheckConstraint("length(bigram) = 2", name=op.f("ck_bigram_stats_bigram")),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["participants.id"],
            name=op.f("fk_bigram_stats_participant_id_participants"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.id"], name=op.f("fk_bigram_stats_session_id_sessions")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bigram_stats")),
        sa.UniqueConstraint("session_id", "bigram", name=op.f("uq_bigram_stats_session_id_bigram")),
    )
    op.create_index(
        op.f("ix_bigram_stats_participant_id_bigram"),
        "bigram_stats",
        ["participant_id", "bigram"],
        unique=False,
    )


def downgrade() -> None:
    """Drop bigram_stats (SQLite drops its index with the table; the index drop is explicit)."""
    op.drop_index(op.f("ix_bigram_stats_participant_id_bigram"), table_name="bigram_stats")
    op.drop_table("bigram_stats")
