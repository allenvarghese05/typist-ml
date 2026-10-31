"""Dashboard analysis reads (design doc 15.2; T1.10). session_matrix serves GET .../matrix.

Reads bigram_stats for one completed session and returns a BigramMatrix; it never re-attributes
(CLAUDE.md "one source of truth"). 404 (SessionNotFoundError, reused from session_stats) when the
session does not exist; 409 (SessionNotCompletedError) when its status is not 'completed' -- no
stats have been written yet (bigram_stats exists only for completed sessions; owner answers 1, 8).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import fmean
from typing import Final

import numpy as np
import scipy.stats as sp_stats
from sqlmodel import Session, col, select

from typist.models import BigramAssignment, BigramStat, Participant
from typist.models import Session as TypingSession
from typist.schemas.analysis import BigramMatrix, MatrixCell, ParticipantResults, SetOutcome
from typist.services.participants import ParticipantNotFoundError
from typist.services.session_stats import SessionNotFoundError
from typist.services.test_composer import ParticipantNotAssignedError

DEFAULT_SEED: Final[int] = 20261030
DEFAULT_POSTERIOR_DRAWS: Final[int] = 100_000
DEFAULT_BOOTSTRAP_RESAMPLES: Final[int] = 10_000


@dataclass(frozen=True)
class PosteriorEffectSummary:
    median_effect: float
    ci_lower: float
    ci_upper: float
    share_below_zero: float


@dataclass(frozen=True)
class BootstrapIKISummary:
    median_effect: float
    ci_lower: float
    ci_upper: float


def compute_beta_interval(
    errors: int, attempts: int, alpha: float = 0.05
) -> tuple[float, float] | None:
    """Compute the equal-tailed (1 - alpha) Jeffreys credible interval for a binomial rate.

    Prior is Beta(0.5, 0.5); posterior is Beta(errors + 0.5, attempts - errors + 0.5).
    Returns (p_lower, p_upper) as floats rounded to 6 decimal places, or None if attempts == 0.
    """
    if attempts <= 0:
        return None
    if errors < 0 or errors > attempts:
        raise ValueError(f"errors ({errors}) must be within [0, attempts ({attempts})]")
    a = errors + 0.5
    b = attempts - errors + 0.5
    lower, upper = sp_stats.beta.ppf([alpha / 2.0, 1.0 - alpha / 2.0], a, b)
    return (round(float(lower), 6), round(float(upper), 6))


def sample_posterior_effects(
    base_errors: int,
    base_attempts: int,
    ret_errors: int,
    ret_attempts: int,
    ctl_base_errors: int,
    ctl_base_attempts: int,
    ctl_ret_errors: int,
    ctl_ret_attempts: int,
    *,
    n_draws: int = DEFAULT_POSTERIOR_DRAWS,
    seed: int = DEFAULT_SEED,
) -> PosteriorEffectSummary | None:
    """Sample targeting effect E(s) = d(s) - d(control) from Beta posteriors with Jeffreys prior.

    d(s) = P(s, retest) - P(s, baseline).
    d(ctl) = P(ctl, retest) - P(ctl, baseline).
    Returns PosteriorEffectSummary or None if any attempts <= 0.
    """
    if min(base_attempts, ret_attempts, ctl_base_attempts, ctl_ret_attempts) <= 0:
        return None

    rng = np.random.default_rng(seed)
    p_base_s = rng.beta(base_errors + 0.5, base_attempts - base_errors + 0.5, size=n_draws)
    p_ret_s = rng.beta(ret_errors + 0.5, ret_attempts - ret_errors + 0.5, size=n_draws)
    p_base_ctl = rng.beta(
        ctl_base_errors + 0.5, ctl_base_attempts - ctl_base_errors + 0.5, size=n_draws
    )
    p_ret_ctl = rng.beta(
        ctl_ret_errors + 0.5, ctl_ret_attempts - ctl_ret_errors + 0.5, size=n_draws
    )

    d_s = p_ret_s - p_base_s
    d_ctl = p_ret_ctl - p_base_ctl
    effect = d_s - d_ctl

    med = float(np.median(effect))
    ci_low = float(np.percentile(effect, 2.5))
    ci_high = float(np.percentile(effect, 97.5))
    share_below = float(np.mean(effect < 0.0))

    return PosteriorEffectSummary(
        median_effect=round(med, 6),
        ci_lower=round(ci_low, 6),
        ci_upper=round(ci_high, 6),
        share_below_zero=round(share_below, 4),
    )


def compute_median_and_iqr(
    samples: Sequence[float],
) -> tuple[float, float, float, float] | None:
    """Compute median, 25th percentile, 75th percentile, and IQR for a sample of IKI measurements.

    Returns (median, q25, q75, iqr) rounded to 2 decimal places, or None if samples is empty.
    """
    if not samples:
        return None
    arr = np.asarray(samples, dtype=float)
    med = float(np.median(arr))
    q25 = float(np.percentile(arr, 25.0))
    q75 = float(np.percentile(arr, 75.0))
    iqr = q75 - q25
    return (round(med, 2), round(q25, 2), round(q75, 2), round(iqr, 2))


def bootstrap_iki_effect(
    base_samples: Sequence[float],
    ret_samples: Sequence[float],
    ctl_base_samples: Sequence[float],
    ctl_ret_samples: Sequence[float],
    *,
    n_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    seed: int = DEFAULT_SEED,
) -> BootstrapIKISummary | None:
    """Non-parametric bootstrap 95% confidence interval for IKI difference-in-differences F(s).

    F(s) = (m(s, retest) - m(s, baseline)) - (m(ctl, retest) - m(ctl, baseline)).
    Resamples with replacement within set and phase using NumPy vectorized indexing.
    Returns BootstrapIKISummary or None if any sample array is empty.
    """
    if not (base_samples and ret_samples and ctl_base_samples and ctl_ret_samples):
        return None

    a_base_s = np.asarray(base_samples, dtype=float)
    a_ret_s = np.asarray(ret_samples, dtype=float)
    a_base_ctl = np.asarray(ctl_base_samples, dtype=float)
    a_ret_ctl = np.asarray(ctl_ret_samples, dtype=float)

    rng = np.random.default_rng(seed)

    # Vectorized resampling via 2D index matrices
    idx_base_s = rng.integers(0, len(a_base_s), size=(n_resamples, len(a_base_s)))
    idx_ret_s = rng.integers(0, len(a_ret_s), size=(n_resamples, len(a_ret_s)))
    idx_base_ctl = rng.integers(0, len(a_base_ctl), size=(n_resamples, len(a_base_ctl)))
    idx_ret_ctl = rng.integers(0, len(a_ret_ctl), size=(n_resamples, len(a_ret_ctl)))

    m_base_s = np.median(a_base_s[idx_base_s], axis=1)
    m_ret_s = np.median(a_ret_s[idx_ret_s], axis=1)
    m_base_ctl = np.median(a_base_ctl[idx_base_ctl], axis=1)
    m_ret_ctl = np.median(a_ret_ctl[idx_ret_ctl], axis=1)

    f_star = (m_ret_s - m_base_s) - (m_ret_ctl - m_base_ctl)

    med = float(np.median(f_star))
    ci_low = float(np.percentile(f_star, 2.5))
    ci_high = float(np.percentile(f_star, 97.5))

    return BootstrapIKISummary(
        median_effect=round(med, 2),
        ci_lower=round(ci_low, 2),
        ci_upper=round(ci_high, 2),
    )


class SessionNotCompletedError(RuntimeError):
    """The session exists but its status is not 'completed' (the endpoint returns 409)."""


class ParticipantNotDoneError(RuntimeError):
    """The participant exists but has not completed the study (status is not 'done')."""


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


def participant_results(session: Session, participant_id: str) -> ParticipantResults:
    """Build ParticipantResults for a participant who has completed the study.

    Raises ParticipantNotFoundError if the participant does not exist,
    ParticipantNotDoneError if participant status is not 'done',
    and ParticipantNotAssignedError if there are no frozen bigram assignments.
    Reads bigram_stats across baseline and retest sessions.
    """
    participant = session.get(Participant, participant_id)
    if participant is None:
        raise ParticipantNotFoundError(participant_id)
    if participant.status != "done":
        raise ParticipantNotDoneError(
            f"participant {participant_id!r} status is {participant.status!r}, expected 'done'"
        )

    assignments = session.exec(
        select(BigramAssignment)
        .where(col(BigramAssignment.participant_id) == participant_id)
        .order_by(col(BigramAssignment.set_label), col(BigramAssignment.baseline_rank))
    ).all()
    if not assignments:
        raise ParticipantNotAssignedError(
            f"participant {participant_id!r} has no frozen assignments"
        )

    set_labels = sorted({a.set_label for a in assignments})
    bigram_to_set = {a.bigram: a.set_label for a in assignments}
    set_to_arm = {a.set_label: a.arm for a in assignments}
    set_to_bigrams: dict[str, list[str]] = {label: [] for label in set_labels}
    for a in assignments:
        set_to_bigrams[a.set_label].append(a.bigram)

    completed_sessions = session.exec(
        select(TypingSession).where(
            col(TypingSession.participant_id) == participant_id,
            col(TypingSession.status) == "completed",
        )
    ).all()

    baseline_sessions = [s for s in completed_sessions if s.phase == "baseline"]
    retest_sessions = [s for s in completed_sessions if s.phase == "retest"]

    baseline_wpms = [s.wpm for s in baseline_sessions if s.wpm is not None]
    retest_wpms = [s.wpm for s in retest_sessions if s.wpm is not None]
    baseline_wpm = round(fmean(baseline_wpms), 2) if baseline_wpms else None
    retest_wpm = round(fmean(retest_wpms), 2) if retest_wpms else None

    baseline_session_ids = {s.id for s in baseline_sessions}
    retest_session_ids = {s.id for s in retest_sessions}

    baseline_stats: Sequence[BigramStat] = (
        session.exec(
            select(BigramStat).where(col(BigramStat.session_id).in_(baseline_session_ids))
        ).all()
        if baseline_session_ids
        else []
    )
    retest_stats: Sequence[BigramStat] = (
        session.exec(
            select(BigramStat).where(col(BigramStat.session_id).in_(retest_session_ids))
        ).all()
        if retest_session_ids
        else []
    )

    baseline_counts: dict[str, dict[str, int]] = {
        label: {"attempts": 0, "errors": 0} for label in set_labels
    }
    for stat in baseline_stats:
        set_label = bigram_to_set.get(stat.bigram)
        if set_label is not None:
            baseline_counts[set_label]["attempts"] += stat.attempts
            baseline_counts[set_label]["errors"] += stat.errors

    retest_counts: dict[str, dict[str, int]] = {
        label: {"attempts": 0, "errors": 0} for label in set_labels
    }
    for stat in retest_stats:
        set_label = bigram_to_set.get(stat.bigram)
        if set_label is not None:
            retest_counts[set_label]["attempts"] += stat.attempts
            retest_counts[set_label]["errors"] += stat.errors

    sets: list[SetOutcome] = []
    for label in set_labels:
        b_att = baseline_counts[label]["attempts"]
        b_err = baseline_counts[label]["errors"]
        b_rate = round(b_err / b_att, 4) if b_att > 0 else None

        r_att = retest_counts[label]["attempts"]
        r_err = retest_counts[label]["errors"]
        r_rate = round(r_err / r_att, 4) if r_att > 0 else None

        sets.append(
            SetOutcome(
                set_label=label,
                arm=set_to_arm[label],
                bigrams=sorted(set_to_bigrams[label]),
                baseline_attempts=b_att,
                baseline_errors=b_err,
                baseline_error_rate=b_rate,
                retest_attempts=r_att,
                retest_errors=r_err,
                retest_error_rate=r_rate,
            )
        )

    return ParticipantResults(
        participant_id=participant_id,
        alias=participant.alias,
        status=participant.status,
        baseline_wpm=baseline_wpm,
        retest_wpm=retest_wpm,
        sets=sets,
    )
