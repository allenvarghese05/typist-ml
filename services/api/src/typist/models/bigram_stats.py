"""bigram_stats table (design doc section 8.1, 8.2): per-session derived per-bigram stats (T1.9).

One row per (session_id, bigram). attempts/errors follow section 12.3 / D23(a); iki_median_ms is
statistics.median over the session's pooled clean IKI samples (not a median of medians), NULL
exactly when iki_n == 0. These rows are derived and are rebuilt wholesale by
typist.services.session_stats (delete-and-reinsert), so they are never append-only. The design
doc lists this table under T2.1, but T1.9's acceptance ("recompute reproduces the same numbers")
needs it; T1.9 creates it and T2.1 keeps its four other tables (T1.9 brief owner answer 1).
"""

from typing import Any, ClassVar

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class BigramStat(SQLModel, table=True):
    """One (session_id, bigram) row of derived stats (section 8.1 columns).

    iki_median_ms is NULL exactly when iki_n == 0. UNIQUE (session_id, bigram) makes recompute's
    delete-and-reinsert safe; the (participant_id, bigram) index serves T2.2's ranking (8.2).
    length(bigram) = 2 enforces the two-letter key (D13).
    """

    # ClassVar[Any]: see "Table names" in typist/models/__init__.py.
    __tablename__: ClassVar[Any] = "bigram_stats"
    __table_args__ = (
        sa.UniqueConstraint("session_id", "bigram"),
        sa.Index("ix_bigram_stats_participant_id_bigram", "participant_id", "bigram"),
        sa.CheckConstraint("attempts >= 0", name="attempts"),
        sa.CheckConstraint("errors >= 0", name="errors"),
        sa.CheckConstraint("iki_n >= 0", name="iki_n"),
        sa.CheckConstraint("length(bigram) = 2", name="bigram"),
    )

    id: int | None = Field(default=None, primary_key=True)
    participant_id: str = Field(foreign_key="participants.id")
    session_id: str = Field(foreign_key="sessions.id")
    bigram: str
    attempts: int
    errors: int
    iki_median_ms: float | None = None
    iki_n: int
