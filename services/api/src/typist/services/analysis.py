"""Dashboard analysis reads (design doc 15.2; T1.10). session_matrix serves GET .../matrix.

Reads bigram_stats for one completed session and returns a BigramMatrix; it never re-attributes
(CLAUDE.md "one source of truth"). 404 (SessionNotFoundError, reused from session_stats) when the
session does not exist; 409 (SessionNotCompletedError) when its status is not 'completed' -- no
stats have been written yet (bigram_stats exists only for completed sessions; owner answers 1, 8).
"""

from sqlmodel import Session, col, select

from typist.models import BigramStat
from typist.models import Session as TypingSession
from typist.schemas.analysis import BigramMatrix, MatrixCell
from typist.services.session_stats import SessionNotFoundError


class SessionNotCompletedError(RuntimeError):
    """The session exists but its status is not 'completed' (the endpoint returns 409)."""


def session_matrix(session: Session, session_id: str) -> BigramMatrix:
    """Build the BigramMatrix for one completed session from its bigram_stats rows.

    Raises SessionNotFoundError if the session does not exist, SessionNotCompletedError if its
    status is not 'completed'. Cells are ordered by bigram; error_rate = errors/attempts (None if
    attempts == 0, which never happens for a stored row but is guarded anyway). Reads only.
    """
    row = session.get(TypingSession, session_id)
    if row is None:
        raise SessionNotFoundError(session_id)
    if row.status != "completed":
        raise SessionNotCompletedError(session_id)
    stats = session.exec(
        select(BigramStat)
        .where(col(BigramStat.session_id) == session_id)
        .order_by(col(BigramStat.bigram))
    ).all()
    cells = [
        MatrixCell(
            bigram=stat.bigram,
            attempts=stat.attempts,
            errors=stat.errors,
            error_rate=(stat.errors / stat.attempts if stat.attempts > 0 else None),
            iki_median_ms=stat.iki_median_ms,
            iki_n=stat.iki_n,
        )
        for stat in stats
    ]
    return BigramMatrix(
        session_id=session_id,
        participant_id=row.participant_id,
        phase=row.phase,
        wpm=row.wpm,
        accuracy=row.accuracy,
        cells=cells,
    )
