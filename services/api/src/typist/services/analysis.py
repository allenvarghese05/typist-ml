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

from typist.models import BigramAssignment, BigramStat, KeystrokeEvent, Participant, SessionBlock
from typist.models import Session as TypingSession
from typist.schemas.analysis import (
    BigramMatrix,
    DroppedBigram,
    ExcludedSession,
    ExclusionsReport,
    MatrixCell,
    ParticipantResults,
    SetOutcome,
)
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


@dataclass(frozen=True)
class SessionSelection:
    analyzed_sessions: list[TypingSession]
    excluded_sessions: list[ExcludedSession]


def select_phase_sessions(
    sessions: Sequence[TypingSession], phase: str
) -> SessionSelection:
    """Select the 2 most recent completed sessions for phase; log superseded and abandoned sessions.

    Sessions are ordered chronologically by (day_index, started_at).
    Completed sessions before the final 2 are superseded.
    """
    phase_sessions = [s for s in sessions if s.phase == phase]
    ordered = sorted(phase_sessions, key=lambda s: (s.day_index, s.started_at))

    completed = [s for s in ordered if s.status == "completed"]
    abandoned = [s for s in ordered if s.status == "abandoned"]

    excluded: list[ExcludedSession] = [
        ExcludedSession(
            session_id=s.id,
            phase=s.phase,
            day_index=s.day_index,
            reason="abandoned",
        )
        for s in abandoned
    ]

    if len(completed) > 2:
        superseded = completed[:-2]
        analyzed = completed[-2:]
        for s in superseded:
            excluded.append(
                ExcludedSession(
                    session_id=s.id,
                    phase=s.phase,
                    day_index=s.day_index,
                    reason="superseded",
                )
            )
    else:
        analyzed = completed

    return SessionSelection(analyzed_sessions=analyzed, excluded_sessions=excluded)


def extract_clean_iki_and_pauses(
    session: Session,
    session_ids: Sequence[str],
    target_bigrams: set[str],
) -> tuple[dict[str, list[float]], dict[str, int]]:
    """Extract raw clean IKI samples and pause counts for target_bigrams across completed blocks.

    Queries SessionBlock where session_id in session_ids and ended_at is not None (completed blocks, D26).
    Follows D14/D15/D24:
    - Bigram pair (a, b) at target_text[j-1:j+1] where target chars are lowercase letters.
    - First-attempt for both, a.outcome == 'correct', no intervening backspace.
    - If b.outcome == 'correct' and b.seq == a.seq + 1:
        gap = b.t_down_ms - a.t_down_ms
        if b.after_pause or gap > 2000.0 (PAUSE_GAP_MS):
            pause_counts[bigram] += 1
        else:
            iki_samples[bigram].append(gap)
    Returns (iki_samples_by_bigram, pause_counts_by_bigram).
    """
    if not session_ids or not target_bigrams:
        return ({b: [] for b in target_bigrams}, {b: 0 for b in target_bigrams})

    blocks = session.exec(
        select(SessionBlock)
        .where(
            col(SessionBlock.session_id).in_(session_ids),
            col(SessionBlock.ended_at).is_not(None),
        )
        .order_by(col(SessionBlock.session_id), col(SessionBlock.block_index))
    ).all()

    samples: dict[str, list[float]] = {b: [] for b in target_bigrams}
    pauses: dict[str, int] = {b: 0 for b in target_bigrams}

    for block in blocks:
        rows = session.exec(
            select(KeystrokeEvent).where(col(KeystrokeEvent.block_id) == block.id)
        ).all()
        ordered_rows = sorted(rows, key=lambda r: r.seq)

        backspace_seqs: list[int] = []
        first_attempt_at: dict[int, KeystrokeEvent] = {}
        for r in ordered_rows:
            if r.outcome == "backspace":
                backspace_seqs.append(r.seq)
            elif r.first_attempt:
                first_attempt_at[r.target_index] = r

        text = block.target_text
        for j in range(1, len(text)):
            c1, c2 = text[j - 1], text[j]
            if not ("a" <= c1 <= "z" and "a" <= c2 <= "z"):
                continue
            bg = c1 + c2
            if bg not in target_bigrams:
                continue

            a = first_attempt_at.get(j - 1)
            b = first_attempt_at.get(j)
            if a is None or b is None:
                continue
            if a.outcome != "correct":
                continue
            if any(a.seq < s < b.seq for s in backspace_seqs):
                continue

            if b.outcome == "correct" and b.seq == a.seq + 1:
                gap = b.t_down_ms - a.t_down_ms
                if b.after_pause or gap > 2000.0:
                    pauses[bg] += 1
                else:
                    samples[bg].append(gap)

    return samples, pauses


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


def participant_results(
    session: Session,
    participant_id: str,
    *,
    seed: int = DEFAULT_SEED,
    n_draws: int = DEFAULT_POSTERIOR_DRAWS,
    n_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
) -> ParticipantResults:
    """Build study-level ParticipantResults per pre-registered analysis plan (D20, D23)."""
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
    set_to_all_bigrams: dict[str, list[str]] = {label: [] for label in set_labels}
    for a in assignments:
        set_to_all_bigrams[a.set_label].append(a.bigram)

    all_sessions = session.exec(
        select(TypingSession).where(col(TypingSession.participant_id) == participant_id)
    ).all()

    base_sel = select_phase_sessions(all_sessions, "baseline")
    ret_sel = select_phase_sessions(all_sessions, "retest")

    baseline_sessions = base_sel.analyzed_sessions
    retest_sessions = ret_sel.analyzed_sessions
    excluded_sessions = base_sel.excluded_sessions + ret_sel.excluded_sessions

    baseline_wpms = [s.wpm for s in baseline_sessions if s.wpm is not None]
    retest_wpms = [s.wpm for s in retest_sessions if s.wpm is not None]
    baseline_accs = [s.accuracy for s in baseline_sessions if s.accuracy is not None]
    retest_accs = [s.accuracy for s in retest_sessions if s.accuracy is not None]

    baseline_wpm = round(fmean(baseline_wpms), 2) if baseline_wpms else None
    retest_wpm = round(fmean(retest_wpms), 2) if retest_wpms else None
    baseline_accuracy = round(fmean(baseline_accs), 4) if baseline_accs else None
    retest_accuracy = round(fmean(retest_accs), 4) if retest_accs else None

    baseline_session_ids = [s.id for s in baseline_sessions]
    retest_session_ids = [s.id for s in retest_sessions]

    baseline_stats = (
        session.exec(
            select(BigramStat).where(col(BigramStat.session_id).in_(baseline_session_ids))
        ).all()
        if baseline_session_ids
        else []
    )
    retest_stats = (
        session.exec(
            select(BigramStat).where(col(BigramStat.session_id).in_(retest_session_ids))
        ).all()
        if retest_session_ids
        else []
    )

    # Sum retest attempts per bigram to check the 20-attempt threshold (D23(c))
    retest_attempts_by_bigram: dict[str, int] = {a.bigram: 0 for a in assignments}
    for st in retest_stats:
        if st.bigram in retest_attempts_by_bigram:
            retest_attempts_by_bigram[st.bigram] += st.attempts

    dropped_bigram_objects: list[DroppedBigram] = []
    set_to_retained_bigrams: dict[str, list[str]] = {label: [] for label in set_labels}
    set_to_dropped_bigrams: dict[str, list[str]] = {label: [] for label in set_labels}

    for a in assignments:
        obs = retest_attempts_by_bigram[a.bigram]
        if obs < 20:
            dropped_bigram_objects.append(
                DroppedBigram(
                    bigram=a.bigram,
                    set_label=a.set_label,
                    arm=a.arm,
                    retest_attempts=obs,
                )
            )
            set_to_dropped_bigrams[a.set_label].append(a.bigram)
        else:
            set_to_retained_bigrams[a.set_label].append(a.bigram)

    retained_bigram_set = {
        bg for bgs in set_to_retained_bigrams.values() for bg in bgs
    }

    # Pool baseline attempts and errors on retained bigrams
    baseline_counts: dict[str, dict[str, int]] = {
        label: {"attempts": 0, "errors": 0} for label in set_labels
    }
    for st in baseline_stats:
        if st.bigram in retained_bigram_set:
            lbl = bigram_to_set[st.bigram]
            baseline_counts[lbl]["attempts"] += st.attempts
            baseline_counts[lbl]["errors"] += st.errors

    # Pool retest attempts and errors on retained bigrams
    retest_counts: dict[str, dict[str, int]] = {
        label: {"attempts": 0, "errors": 0} for label in set_labels
    }
    for st in retest_stats:
        if st.bigram in retained_bigram_set:
            lbl = bigram_to_set[st.bigram]
            retest_counts[lbl]["attempts"] += st.attempts
            retest_counts[lbl]["errors"] += st.errors

    # Extract raw clean IKI samples and pause counts
    b_samples, b_pauses = extract_clean_iki_and_pauses(
        session, baseline_session_ids, retained_bigram_set
    )
    r_samples, r_pauses = extract_clean_iki_and_pauses(
        session, retest_session_ids, retained_bigram_set
    )

    set_b_iki: dict[str, list[float]] = {label: [] for label in set_labels}
    set_r_iki: dict[str, list[float]] = {label: [] for label in set_labels}
    pause_counts: dict[str, int] = {}

    for label in set_labels:
        p_base_count = 0
        p_ret_count = 0
        for bg in set_to_retained_bigrams[label]:
            set_b_iki[label].extend(b_samples.get(bg, []))
            set_r_iki[label].extend(r_samples.get(bg, []))
            p_base_count += b_pauses.get(bg, 0)
            p_ret_count += r_pauses.get(bg, 0)
        pause_counts[f"{label}:baseline"] = p_base_count
        pause_counts[f"{label}:retest"] = p_ret_count

    # Primary outcome calculations per set
    control_label = next(
        (label for label, arm in set_to_arm.items() if arm == "control"), None
    )

    # Intermediate structures
    base_rates: dict[str, float | None] = {}
    ret_rates: dict[str, float | None] = {}
    rate_changes: dict[str, float | None] = {}
    base_intervals: dict[str, tuple[float, float] | None] = {}
    ret_intervals: dict[str, tuple[float, float] | None] = {}

    for label in set_labels:
        b_att = baseline_counts[label]["attempts"]
        b_err = baseline_counts[label]["errors"]
        r_att = retest_counts[label]["attempts"]
        r_err = retest_counts[label]["errors"]

        b_rate = round(b_err / b_att, 4) if b_att > 0 else None
        r_rate = round(r_err / r_att, 4) if r_att > 0 else None
        base_rates[label] = b_rate
        ret_rates[label] = r_rate
        rate_changes[label] = (
            round(r_rate - b_rate, 4)
            if (r_rate is not None and b_rate is not None)
            else None
        )

        base_intervals[label] = compute_beta_interval(b_err, b_att)
        ret_intervals[label] = compute_beta_interval(r_err, r_att)

    # Key secondary outcome calculations per set
    set_b_timing: dict[str, tuple[float, float, float, float] | None] = {}
    set_r_timing: dict[str, tuple[float, float, float, float] | None] = {}
    timing_changes: dict[str, float | None] = {}

    for label in set_labels:
        t_base = compute_median_and_iqr(set_b_iki[label])
        t_ret = compute_median_and_iqr(set_r_iki[label])
        set_b_timing[label] = t_base
        set_r_timing[label] = t_ret
        timing_changes[label] = (
            round(t_ret[0] - t_base[0], 2)
            if (t_ret is not None and t_base is not None)
            else None
        )

    # Assemble SetOutcome objects
    sets: list[SetOutcome] = []
    ctl_rate_change = (
        rate_changes.get(control_label) if control_label else None
    )
    ctl_timing_change = (
        timing_changes.get(control_label) if control_label else None
    )

    for label in set_labels:
        arm = set_to_arm[label]
        b_att = baseline_counts[label]["attempts"]
        b_err = baseline_counts[label]["errors"]
        r_att = retest_counts[label]["attempts"]
        r_err = retest_counts[label]["errors"]

        b_ci = base_intervals[label]
        r_ci = ret_intervals[label]

        t_base = set_b_timing[label]
        t_ret = set_r_timing[label]

        d_s = rate_changes[label]
        c_s = timing_changes[label]

        # Targeting effects vs control
        targeting_effect: float | None = None
        post_effect: PosteriorEffectSummary | None = None
        iki_targeting_effect: float | None = None
        iki_bootstrap: BootstrapIKISummary | None = None

        if arm != "control" and control_label is not None:
            if d_s is not None and ctl_rate_change is not None:
                targeting_effect = round(d_s - ctl_rate_change, 4)

            ctl_b_att = baseline_counts[control_label]["attempts"]
            ctl_b_err = baseline_counts[control_label]["errors"]
            ctl_r_att = retest_counts[control_label]["attempts"]
            ctl_r_err = retest_counts[control_label]["errors"]

            post_effect = sample_posterior_effects(
                b_err,
                b_att,
                r_err,
                r_att,
                ctl_b_err,
                ctl_b_att,
                ctl_r_err,
                ctl_r_att,
                n_draws=n_draws,
                seed=seed,
            )

            if c_s is not None and ctl_timing_change is not None:
                iki_targeting_effect = round(c_s - ctl_timing_change, 2)

            iki_bootstrap = bootstrap_iki_effect(
                set_b_iki[label],
                set_r_iki[label],
                set_b_iki[control_label],
                set_r_iki[control_label],
                n_resamples=n_resamples,
                seed=seed,
            )

        sets.append(
            SetOutcome(
                set_label=label,
                arm=arm,
                bigrams=sorted(set_to_all_bigrams[label]),
                retained_bigrams=sorted(set_to_retained_bigrams[label]),
                dropped_bigrams=sorted(set_to_dropped_bigrams[label]),
                baseline_attempts=b_att,
                baseline_errors=b_err,
                baseline_error_rate=base_rates[label],
                baseline_beta_ci_lower=b_ci[0] if b_ci else None,
                baseline_beta_ci_upper=b_ci[1] if b_ci else None,
                retest_attempts=r_att,
                retest_errors=r_err,
                retest_error_rate=ret_rates[label],
                retest_beta_ci_lower=r_ci[0] if r_ci else None,
                retest_beta_ci_upper=r_ci[1] if r_ci else None,
                error_rate_change=d_s,
                targeting_effect=targeting_effect,
                posterior_effect_median=(
                    post_effect.median_effect if post_effect else None
                ),
                posterior_effect_ci_lower=(
                    post_effect.ci_lower if post_effect else None
                ),
                posterior_effect_ci_upper=(
                    post_effect.ci_upper if post_effect else None
                ),
                share_below_zero=(
                    post_effect.share_below_zero if post_effect else None
                ),
                baseline_iki_n=len(set_b_iki[label]),
                baseline_iki_median_ms=t_base[0] if t_base else None,
                baseline_iki_iqr_ms=t_base[3] if t_base else None,
                retest_iki_n=len(set_r_iki[label]),
                retest_iki_median_ms=t_ret[0] if t_ret else None,
                retest_iki_iqr_ms=t_ret[3] if t_ret else None,
                iki_change_ms=c_s,
                iki_targeting_effect_ms=iki_targeting_effect,
                iki_bootstrap_median_ms=(
                    iki_bootstrap.median_effect if iki_bootstrap else None
                ),
                iki_bootstrap_ci_lower_ms=(
                    iki_bootstrap.ci_lower if iki_bootstrap else None
                ),
                iki_bootstrap_ci_upper_ms=(
                    iki_bootstrap.ci_upper if iki_bootstrap else None
                ),
            )
        )

    exclusions_report = ExclusionsReport(
        excluded_sessions=excluded_sessions,
        dropped_bigrams=dropped_bigram_objects,
        pause_counts=pause_counts,
    )

    return ParticipantResults(
        participant_id=participant_id,
        alias=participant.alias,
        status=participant.status,
        is_builder=participant.is_builder,
        is_blinded=participant.is_blinded,
        baseline_wpm=baseline_wpm,
        baseline_accuracy=baseline_accuracy,
        retest_wpm=retest_wpm,
        retest_accuracy=retest_accuracy,
        analyzed_baseline_session_ids=baseline_session_ids,
        analyzed_retest_session_ids=retest_session_ids,
        posterior_draws=n_draws,
        bootstrap_resamples=n_resamples,
        seed=seed,
        sets=sets,
        exclusions=exclusions_report,
    )
