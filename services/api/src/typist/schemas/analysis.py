"""Response schemas for the analysis router (design doc 7, 15.2; T1.10).

Table models are never returned from the API (17.1). BigramMatrix is the M1 dashboard view: a
completed session's per-bigram attempts, errors, server-computed error rate and median IKI, read
straight from bigram_stats (one source of truth; the browser renders, it does not recompute).
"""

from pydantic import BaseModel


class MatrixCell(BaseModel):
    """One (bigram) cell. error_rate = errors/attempts, computed server-side (None if attempts == 0).

    iki_median_ms is None exactly when iki_n == 0 (every pair paused or non-adjacent; D23(a)/D24).
    Only bigrams that have a bigram_stats row appear; absent bigrams are "no data" in the client.
    """

    bigram: str
    attempts: int
    errors: int
    error_rate: float | None
    iki_median_ms: float | None
    iki_n: int


class BigramMatrix(BaseModel):
    """A completed session's bigram matrix: session identity, headline stats and the cells."""

    session_id: str
    participant_id: str
    phase: str
    wpm: float | None
    accuracy: float | None
    cells: list[MatrixCell]
