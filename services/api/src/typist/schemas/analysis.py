"""Response schemas for the analysis router (design doc 7, 15.2; T1.10, T4.1).

Table models are never returned from the API (17.1). BigramMatrix is the M1 dashboard view: a
completed session's per-bigram attempts, errors, server-computed error rate and median IKI, read
straight from bigram_stats (one source of truth; the browser renders, it does not recompute).
ParticipantResults provides study-level per-set outcomes, Jeffreys Beta credible intervals,
posterior effect draws, median IKI bootstrap intervals, and the pre-registered exclusions report.
"""

from typing import cast

from pydantic import BaseModel, Field


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


class ExcludedSession(BaseModel):
    """A session excluded from outcome analysis per D23/analysis-plan."""

    session_id: str
    phase: str
    day_index: int
    reason: str  # 'abandoned', 'superseded'


class DroppedBigram(BaseModel):
    """A tracked bigram dropped because it had fewer than 20 pooled retest attempts (D23(c))."""

    bigram: str
    set_label: str
    arm: str
    retest_attempts: int


class ExclusionsReport(BaseModel):
    """Pre-registered exclusions report (D20, D23, analysis-plan)."""

    excluded_sessions: list[ExcludedSession] = Field(
        default_factory=lambda: cast(list[ExcludedSession], [])
    )
    dropped_bigrams: list[DroppedBigram] = Field(
        default_factory=lambda: cast(list[DroppedBigram], [])
    )
    pause_counts: dict[str, int] = Field(default_factory=dict)


class SetOutcome(BaseModel):
    """Outcome for one experimental set (e.g. Set A, mapped to arm 'control')."""

    set_label: str
    arm: str
    bigrams: list[str]
    retained_bigrams: list[str] = Field(default_factory=list)
    dropped_bigrams: list[str] = Field(default_factory=list)

    # Primary outcome: error rates and Beta credible intervals
    baseline_attempts: int
    baseline_errors: int
    baseline_error_rate: float | None
    baseline_beta_ci_lower: float | None = None
    baseline_beta_ci_upper: float | None = None

    retest_attempts: int
    retest_errors: int
    retest_error_rate: float | None
    retest_beta_ci_lower: float | None = None
    retest_beta_ci_upper: float | None = None

    error_rate_change: float | None = None
    targeting_effect: float | None = None
    posterior_effect_median: float | None = None
    posterior_effect_ci_lower: float | None = None
    posterior_effect_ci_upper: float | None = None
    share_below_zero: float | None = None

    # Key secondary outcome: median IKI and bootstrap confidence intervals
    baseline_iki_n: int = 0
    baseline_iki_median_ms: float | None = None
    baseline_iki_iqr_ms: float | None = None

    retest_iki_n: int = 0
    retest_iki_median_ms: float | None = None
    retest_iki_iqr_ms: float | None = None

    iki_change_ms: float | None = None
    iki_targeting_effect_ms: float | None = None
    iki_bootstrap_median_ms: float | None = None
    iki_bootstrap_ci_lower_ms: float | None = None
    iki_bootstrap_ci_upper_ms: float | None = None


class ParticipantResults(BaseModel):
    """Participant study-level outcomes across sets (design doc 14; T2.10, T4.1)."""

    participant_id: str
    alias: str
    status: str
    is_builder: bool = False
    is_blinded: bool = False
    baseline_wpm: float | None = None
    baseline_accuracy: float | None = None
    retest_wpm: float | None = None
    retest_accuracy: float | None = None
    analyzed_baseline_session_ids: list[str] = Field(default_factory=list)
    analyzed_retest_session_ids: list[str] = Field(default_factory=list)
    posterior_draws: int = 100_000
    bootstrap_resamples: int = 10_000
    seed: int = 20261030
    sets: list[SetOutcome] = Field(default_factory=lambda: cast(list[SetOutcome], []))
    exclusions: ExclusionsReport | None = None
