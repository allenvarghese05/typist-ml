"""Assignment: rank weak bigrams, deal them into sets in snake order, map sets to arms with a
seeded shuffle, and freeze (design doc 3.4; D01, D04; T2.2).

The one place the frozen within-person map is written (CLAUDE.md "one source of truth"). Pure
functions (smoothed_rate, rank_candidates, snake_deal, shuffle_arms, select_count) do the maths on
plain frozen dataclasses so they are unit-tested without a database; load_assignment_config and
load_baseline read rows; assign_participant does the all-or-nothing insert with frozen_at set.
Counts (baseline_attempts/baseline_errors) are pooled from bigram_stats across the two baseline
sessions; the tie-break IKI median is RE-POOLED from raw keystroke samples via T1.7's
attribute_block_samples + merge_bigram_samples (never a median of session medians; CLAUDE.md;
owner answer 4). The only randomness is one random.Random stream the caller passes in, used only
for rng.shuffle of the arms (owner answer 5); the ranking is a total order (-smoothed_rate, -z,
bigram). Freeze is enforced by the SQLite trigger from migration 0005; this service never UPDATEs a
row and refuses a second run (AlreadyAssignedError). D28 sets the candidate threshold to 15.
"""

import logging
import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from statistics import fmean, median, pstdev

from sqlmodel import Session, col, select

from typist.corpus.word_index import WordIndex
from typist.models import (
    BigramAssignment,
    BigramStat,
    ExperimentConfig,
    KeystrokeEvent,
    Participant,
    SessionBlock,
)
from typist.models import Session as TypingSession
from typist.models.bigram_assignment import SET_LABELS
from typist.services.attribution import BigramSamples, attribute_block_samples
from typist.services.participants import ParticipantNotFoundError
from typist.services.session_stats import merge_bigram_samples

logger = logging.getLogger(__name__)

_ASSIGNMENT_CONFIG_KEYS = (
    "assignment_seed",
    "assignment_prior_strength",
    "assignment_min_observations",
    "assignment_per_set",
    "assignment_per_set_fallback",
    "baseline_parts",
)


class AssignmentError(RuntimeError):
    """Base class for an assignment that cannot proceed (T2.8's endpoint maps these to 404/409)."""


class BaselineIncompleteError(AssignmentError):
    """The participant does not have exactly baseline_parts completed baseline sessions (409)."""


class AlreadyAssignedError(AssignmentError):
    """The participant already has frozen bigram_assignment rows; assign is once-only (409)."""


class NoBaselineDataError(AssignmentError):
    """The participant has baseline sessions but zero pooled bigram attempts (no p0 is defined)."""


class TooFewCandidatesError(AssignmentError):
    """Fewer qualifying candidate bigrams than the fallback pool needs; never assign a degenerate map."""


class MissingConfigError(LookupError):
    """An experiment_config key the assignment service needs is absent (run migrations)."""


@dataclass(frozen=True)
class AssignmentConfig:
    """The experiment_config values assignment needs (owner answer 2; baseline_parts from 0002)."""

    seed: int
    prior_strength: int
    min_observations: int
    per_set: int
    per_set_fallback: int
    baseline_parts: int
    arms: tuple[str, ...]


@dataclass(frozen=True)
class PooledBigram:
    """One bigram's baseline snapshot pooled over the two baseline sessions.

    attempts/errors are summed from bigram_stats; iki_median_ms is the single median over raw IKI
    samples re-pooled across both sessions' blocks (None when no clean sample exists).
    """

    bigram: str
    attempts: int
    errors: int
    iki_median_ms: float | None


@dataclass(frozen=True)
class Baseline:
    """load_baseline output: every pooled baseline bigram (sorted by bigram) and the prior centre p0."""

    bigrams: tuple[PooledBigram, ...]
    p0: float


@dataclass(frozen=True)
class RankedBigram:
    """A candidate after ranking: its 1-based rank and the smoothed error rate stored as weakness_score."""

    bigram: str
    rank: int
    smoothed_rate: float
    attempts: int
    errors: int


def smoothed_rate(errors: int, attempts: int, *, p0: float, strength: int) -> float:
    """Return the Beta posterior mean (errors + strength*p0) / (attempts + strength) (3.4 step 2).

    The prior is Beta(alpha0 = strength*p0, beta0 = strength*(1 - p0)); its posterior mean after
    observing `errors` in `attempts` is (errors + strength*p0) / (attempts + strength). strength is
    the empirical-Bayes prior strength (config assignment_prior_strength, 20). Caller guarantees
    attempts + strength > 0 (strength >= 1).
    """
    return (errors + strength * p0) / (attempts + strength)


def rank_candidates(
    candidates: Sequence[PooledBigram], *, p0: float, strength: int
) -> list[RankedBigram]:
    """Rank candidates by smoothed error rate, breaking ties by IKI z-score then bigram (3.4 step 3).

    For every candidate computes smoothed_rate(errors, attempts, p0, strength). The tie-break
    z-score standardises a candidate's iki_median_ms against the population of candidate medians
    that are not None: z = (m - mean(medians)) / pstdev(medians); when fewer than two such medians
    exist or pstdev == 0 every z is 0.0, and a candidate whose iki_median_ms is None gets z = 0.0
    (neutral; owner answer 4). Sort key is (-smoothed_rate, -z, bigram) -- the bigram string is the
    final total order so the result is fully deterministic. rank is 1-based in that order. Pure: no
    database, no randomness.
    """
    medians = [c.iki_median_ms for c in candidates if c.iki_median_ms is not None]
    if len(medians) >= 2:
        mean_m = fmean(medians)
        std_m = pstdev(medians)
    else:
        mean_m = 0.0
        std_m = 0.0

    def z_of(value: float | None) -> float:
        if value is None or std_m == 0.0:
            return 0.0
        return (value - mean_m) / std_m

    scored = [
        (smoothed_rate(c.errors, c.attempts, p0=p0, strength=strength), z_of(c.iki_median_ms), c)
        for c in candidates
    ]
    scored.sort(key=lambda item: (-item[0], -item[1], item[2].bigram))
    return [
        RankedBigram(
            bigram=c.bigram,
            rank=position,
            smoothed_rate=rate,
            attempts=c.attempts,
            errors=c.errors,
        )
        for position, (rate, _z, c) in enumerate(scored, start=1)
    ]


def select_count(qualifying: int, *, per_set: int, fallback: int, sets: int) -> int:
    """Return how many bigrams to take: per_set*sets if enough qualify, else fallback*sets (3.4 step 4).

    Raises TooFewCandidatesError when qualifying < fallback*sets, so a degenerate map is never
    produced (owner answer 1). Both returned sizes are multiples of `sets` (even snake deal).
    """
    full = per_set * sets
    floor = fallback * sets
    if qualifying >= full:
        return full
    if qualifying >= floor:
        return floor
    raise TooFewCandidatesError(f"too few candidates: {qualifying} < {floor}")


def snake_deal(ranked: Sequence[RankedBigram], sets: int) -> list[tuple[RankedBigram, int]]:
    """Pair each ranked bigram with a 0-based set index in snake order (3.4 step 5).

    Order over `sets` columns is 0,1,...,sets-1 then sets-1,...,1,0, repeating: rank 1 -> set 0,
    rank 2 -> set 1, ..., rank sets -> set sets-1, rank sets+1 -> set sets-1, and so on. This
    balances weakness across sets. Pure: input order is the rank order. For 16 over 4 sets set 0
    gets ranks {1,8,9,16}; for 8 over 2 sets set 0 gets ranks {1,4,5,8}.
    """
    dealt: list[tuple[RankedBigram, int]] = []
    for index, item in enumerate(ranked):
        cycle, position = divmod(index, sets)
        set_index = position if cycle % 2 == 0 else sets - 1 - position
        dealt.append((item, set_index))
    return dealt


def shuffle_arms(arms: Sequence[str], rng: random.Random) -> list[str]:
    """Return a shuffled copy of arms using rng.shuffle (3.4 step 6; owner answer 5).

    arms is config.arms (arms_enabled, in its stored order). rng is the only randomness source in
    the task; it is the single stream random.Random(f"{assignment_seed}:{participant_id}") the
    caller builds. Does not mutate arms.
    """
    shuffled = list(arms)
    rng.shuffle(shuffled)
    return shuffled


def load_assignment_config(session: Session) -> AssignmentConfig:
    """Read the five assignment keys, baseline_parts, and arms_enabled from experiment_config.

    Raises MissingConfigError if any key is absent (run migrations). The five assignment keys and
    baseline_parts are integers; arms_enabled is a JSON list stored as text, returned as a tuple in
    its stored order (owner answer 1: sets = len(arms_enabled)).
    """
    ints: dict[str, int] = {}
    for key in _ASSIGNMENT_CONFIG_KEYS:
        row = session.get(ExperimentConfig, key)
        if row is None:
            raise MissingConfigError(key)
        ints[key] = int(row.value)
    arms_row = session.get(ExperimentConfig, "arms_enabled")
    if arms_row is None:
        raise MissingConfigError("arms_enabled")
    return AssignmentConfig(
        seed=ints["assignment_seed"],
        prior_strength=ints["assignment_prior_strength"],
        min_observations=ints["assignment_min_observations"],
        per_set=ints["assignment_per_set"],
        per_set_fallback=ints["assignment_per_set_fallback"],
        baseline_parts=ints["baseline_parts"],
        arms=tuple(str(arm) for arm in arms_row.value),
    )


def _completed_baseline_session_ids(session: Session, participant_id: str) -> list[str]:
    """Ids of the participant's completed baseline sessions, ordered by id (deterministic)."""
    return list(
        session.exec(
            select(TypingSession.id)
            .where(
                col(TypingSession.participant_id) == participant_id,
                col(TypingSession.phase) == "baseline",
                col(TypingSession.status) == "completed",
            )
            .order_by(col(TypingSession.id))
        ).all()
    )


def load_baseline(
    session: Session, participant_id: str, config: AssignmentConfig
) -> Baseline:
    """Pool bigram_stats counts and re-pool raw IKI samples across the completed baseline sessions.

    attempts/errors per bigram are summed over the participant's completed baseline-session
    bigram_stats rows. The tie-break iki_median_ms is re-pooled: attribute_block_samples runs on
    each baseline block's keystroke rows, merge_bigram_samples concatenates the raw samples across
    blocks (NOT a median of medians; owner answer 4), and one statistics.median per bigram gives the
    median (None when no clean sample). p0 is Sum(errors)/Sum(attempts) over ALL pooled baseline
    bigrams (owner answer 3), or 0.0 when there are no attempts (assign_participant then raises
    NoBaselineDataError). bigrams is sorted by bigram. `config` is unused here but keeps the DB
    functions' signatures uniform. Determinism: every read is ordered and iteration is over
    sorted keys.
    """
    session_ids = _completed_baseline_session_ids(session, participant_id)
    attempts: dict[str, int] = {}
    errors: dict[str, int] = {}
    stat_rows = session.exec(
        select(BigramStat)
        .where(col(BigramStat.session_id).in_(session_ids))
        .order_by(col(BigramStat.session_id), col(BigramStat.bigram))
    ).all()
    for row in stat_rows:
        attempts[row.bigram] = attempts.get(row.bigram, 0) + row.attempts
        errors[row.bigram] = errors.get(row.bigram, 0) + row.errors
    blocks = session.exec(
        select(SessionBlock)
        .where(col(SessionBlock.session_id).in_(session_ids))
        .order_by(col(SessionBlock.id))
    ).all()
    per_block: list[dict[str, BigramSamples]] = []
    for block in blocks:
        rows = session.exec(
            select(KeystrokeEvent).where(col(KeystrokeEvent.block_id) == block.id)
        ).all()
        per_block.append(attribute_block_samples(block.target_text, rows))
    pooled = merge_bigram_samples(per_block)
    total_errors = sum(errors.values())
    total_attempts = sum(attempts.values())
    p0 = total_errors / total_attempts if total_attempts > 0 else 0.0
    bigrams = tuple(
        PooledBigram(
            bigram=bigram,
            attempts=attempts[bigram],
            errors=errors[bigram],
            iki_median_ms=(
                median(pooled[bigram].iki_samples)
                if bigram in pooled and pooled[bigram].iki_samples
                else None
            ),
        )
        for bigram in sorted(attempts)
    )
    return Baseline(bigrams=bigrams, p0=p0)


def assign_participant(
    session: Session,
    participant_id: str,
    *,
    rng: random.Random,
    now: datetime,
    index: WordIndex,
) -> tuple[BigramAssignment, ...]:
    """Rank, split, map and freeze one participant's weak bigrams, all-or-nothing (design doc 3.4).

    Preconditions (owner answer 6; no status transition -- T2.8 owns that):
      * the participant exists, else ParticipantNotFoundError;
      * exactly config.baseline_parts completed baseline sessions, else BaselineIncompleteError;
      * no existing bigram_assignment rows, else AlreadyAssignedError.
    Then load_baseline gives p0 and the pooled bigrams; zero total attempts -> NoBaselineDataError.
    Candidates are the pooled bigrams that are in index.tracked_bigrams (3.4 step 1 universe) and
    have attempts >= config.min_observations (D28 threshold). select_count decides 16/12 (or 8/6)
    and raises TooFewCandidatesError below the floor; a fallback selection is logged (owner answer
    1). rank_candidates ranks them, snake_deal maps rank -> set index, shuffle_arms(config.arms,
    rng) maps set index -> arm (set label SET_LABELS[set_index]). All rows are inserted with
    frozen_at = now in one transaction and committed; the migration-0005 trigger makes them
    immutable. rng must be the caller's random.Random(f"{seed}:{participant_id}") (owner answer 5).
    Returns the inserted rows in rank order.
    """
    if session.get(Participant, participant_id) is None:
        raise ParticipantNotFoundError(participant_id)
    config = load_assignment_config(session)
    session_ids = _completed_baseline_session_ids(session, participant_id)
    if len(session_ids) != config.baseline_parts:
        raise BaselineIncompleteError(
            f"{participant_id}: {len(session_ids)} completed baseline sessions, "
            f"need {config.baseline_parts}"
        )
    existing = session.exec(
        select(BigramAssignment.bigram).where(
            col(BigramAssignment.participant_id) == participant_id
        )
    ).first()
    if existing is not None:
        raise AlreadyAssignedError(participant_id)
    baseline = load_baseline(session, participant_id, config)
    if sum(b.attempts for b in baseline.bigrams) == 0:
        raise NoBaselineDataError(participant_id)
    tracked = set(index.tracked_bigrams)
    candidates = [
        b
        for b in baseline.bigrams
        if b.bigram in tracked and b.attempts >= config.min_observations
    ]
    sets = len(config.arms)
    count = select_count(
        len(candidates),
        per_set=config.per_set,
        fallback=config.per_set_fallback,
        sets=sets,
    )
    if count < config.per_set * sets:
        logger.warning(
            "assignment fallback: %s qualifying candidates for %s, taking %s (3 per set)",
            len(candidates),
            participant_id,
            count,
        )
    ranked = rank_candidates(
        candidates, p0=baseline.p0, strength=config.prior_strength
    )[:count]
    arms = shuffle_arms(config.arms, rng)
    rows = [
        BigramAssignment(
            participant_id=participant_id,
            bigram=item.bigram,
            set_label=SET_LABELS[set_index],
            arm=arms[set_index],
            baseline_rank=item.rank,
            weakness_score=item.smoothed_rate,
            baseline_attempts=item.attempts,
            baseline_errors=item.errors,
            frozen_at=now,
        )
        for item, set_index in snake_deal(ranked, sets)
    ]
    session.add_all(rows)
    session.commit()
    return tuple(rows)
