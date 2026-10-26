"""Compose the baseline (form A) and retest (form B) texts and write them to text_passages
(design doc sections 3.2, 3.5, 7, 8.1, 13.3, 16; T1.8, T2.7).

compose_baseline is the pure, seeded, coverage-efficient 13.3 composer (plan O1a) for shared form A
passages. compose_retest is the pure, seeded composer for per-participant form B passages (T2.7):
it targets the participant's frozen assigned bigrams from bigram_assignment to at least
retest_min_occurrences (40) combined across retest_parts (2) parts, balancing progress across parts
and then filling the remainder of retest_part_chars (2700) by lifting the lowest-coverage corpus
tracked bigrams. At every step it strictly prefers candidate words that did not appear in form A,
falling back to form A words only when a source bigram has zero eligible non-form-A words left in
that part ("different words from form A where possible"). persist_baseline and persist_retest are
idempotent DB writers that refuse to replace passages referenced by any session_blocks row.
"""

import math
import random
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from sqlmodel import Session, col, select

from typist.corpus.word_index import WordIndex, count_bigrams, word_bigrams
from typist.models import (
    BigramAssignment,
    ExperimentConfig,
    Participant,
    SessionBlock,
    TextPassage,
)
from typist.services.participants import ParticipantNotFoundError

# Design-doc constants for the 13.3 composer loop; not experiment knobs, so not in experiment_config
# (cf. T1.7 keeping the 2000 ms pause threshold as a literal). Changing these changes the algorithm.
_TEMPERATURE = 0.5  # 13.3 step 4 softmax temperature.
_TOP_CANDIDATES = 50  # 13.3 step 4 "sample one of the top 50".
_CANDIDATE_POOL = 400  # eligible words gathered per step before deficit-weighted re-ranking (O1a).
_MIN_WORD_LEN = 2  # 13.4 word-length range, applied to real words (owner answer 8).
_MAX_WORD_LEN = 10
_MAX_USES_PER_PART = 2  # 13.3 step 5 "skip words already used twice" (owner answer 8).

_BASELINE_CONFIG_KEYS = (
    "tracked_bigram_count",
    "baseline_min_occurrences",
    "baseline_parts",
    "baseline_part_chars",
    "corpus_seed",
)

_RETEST_CONFIG_KEYS = (
    "tracked_bigram_count",
    "retest_min_occurrences",
    "retest_parts",
    "retest_part_chars",
    "corpus_seed",
)


@dataclass(frozen=True)
class BaselineConfig:
    """The experiment_config values the baseline composer needs (all integers)."""

    tracked_bigram_count: int
    baseline_min_occurrences: int
    baseline_parts: int
    baseline_part_chars: int
    corpus_seed: int


@dataclass(frozen=True)
class RetestConfig:
    """The experiment_config values the retest (form B) composer needs (all integers; T2.7)."""

    tracked_bigram_count: int
    retest_min_occurrences: int
    retest_parts: int
    retest_part_chars: int
    corpus_seed: int


class MissingConfigError(LookupError):
    """An experiment_config key the test composer needs is absent (run migrations)."""


class BaselineTextsDifferError(RuntimeError):
    """Shared form A passages already exist and differ from the composed texts (need --replace)."""


class BaselinePassagesInUseError(RuntimeError):
    """A session block references a form A passage, so it must not be replaced (freeze guard)."""


class BaselinePassagesNotFoundError(RuntimeError):
    """Shared form A passages do not exist yet in text_passages (run compose-baseline first)."""


class ParticipantNotAssignedError(RuntimeError):
    """The participant has no frozen bigram_assignment rows yet (run assign first)."""


class RetestTextsDifferError(RuntimeError):
    """This participant's form B passages already exist and differ (need --replace)."""


class RetestPassagesInUseError(RuntimeError):
    """A session block references one of this participant's form B passages (freeze guard)."""


@dataclass(frozen=True)
class BaselinePersistResult:
    """Outcome of persist_baseline: status is 'created', 'unchanged' or 'replaced'."""

    status: str
    parts: int


@dataclass(frozen=True)
class RetestPersistResult:
    """Outcome of persist_retest: status is 'created', 'unchanged' or 'replaced'."""

    status: str
    parts: int
    participant_id: str


@dataclass(frozen=True)
class _Candidate:
    """A usable word: its log wordfreq frequency, tracked bigrams, and assigned bigrams."""

    log_frequency: float
    target_bigrams: tuple[str, ...]
    assigned_bigrams: tuple[str, ...] = ()


def load_baseline_config(session: Session) -> BaselineConfig:
    """Read the five baseline keys from experiment_config; raise MissingConfigError if any is absent."""
    values: dict[str, int] = {}
    for key in _BASELINE_CONFIG_KEYS:
        row = session.get(ExperimentConfig, key)
        if row is None:
            raise MissingConfigError(key)
        values[key] = int(row.value)
    return BaselineConfig(**values)


def load_retest_config(session: Session) -> RetestConfig:
    """Read the five retest keys from experiment_config; raise MissingConfigError if any is absent."""
    values: dict[str, int] = {}
    for key in _RETEST_CONFIG_KEYS:
        row = session.get(ExperimentConfig, key)
        if row is None:
            raise MissingConfigError(key)
        values[key] = int(row.value)
    return RetestConfig(**values)


def load_form_a_words(session: Session) -> frozenset[str]:
    """Return all distinct words used in shared baseline (form A) passages in text_passages.

    Raises BaselinePassagesNotFoundError if no shared form A rows exist in text_passages yet.
    """
    rows = session.exec(
        select(TextPassage)
        .where(
            col(TextPassage.kind) == "baseline",
            col(TextPassage.form) == "A",
            col(TextPassage.participant_id).is_(None),
        )
        .order_by(col(TextPassage.part))
    ).all()
    if not rows:
        raise BaselinePassagesNotFoundError(
            "shared form A passages are missing; run `typist corpus compose-baseline` first"
        )
    return frozenset(word for passage in rows for word in passage.text.split(" ") if word)


def load_assigned_bigrams(session: Session, participant_id: str) -> tuple[str, ...]:
    """Return the participant's frozen assigned bigrams ordered by baseline_rank ASC.

    Raises ParticipantNotFoundError if the participant does not exist, or
    ParticipantNotAssignedError if the participant has no rows in bigram_assignment.
    """
    if session.get(Participant, participant_id) is None:
        raise ParticipantNotFoundError(participant_id)
    rows = session.exec(
        select(BigramAssignment)
        .where(col(BigramAssignment.participant_id) == participant_id)
        .order_by(col(BigramAssignment.baseline_rank))
    ).all()
    if not rows:
        raise ParticipantNotAssignedError(
            f"participant {participant_id!r} has no frozen bigram_assignment rows"
        )
    return tuple(row.bigram for row in rows)


def _eligible(words: tuple[str, ...], used: dict[str, int]) -> list[str]:
    """Return the first up to _CANDIDATE_POOL words not yet used _MAX_USES_PER_PART times."""
    out: list[str] = []
    for word in words:
        if used.get(word, 0) < _MAX_USES_PER_PART:
            out.append(word)
            if len(out) >= _CANDIDATE_POOL:
                break
    return out


def _has_eligible(words: tuple[str, ...], used: dict[str, int]) -> bool:
    """True if any word in words has been used fewer than _MAX_USES_PER_PART times this part."""
    return any(used.get(word, 0) < _MAX_USES_PER_PART for word in words)


def _retest_eligible(
    preferred: tuple[str, ...],
    fallback: tuple[str, ...],
    used: dict[str, int],
) -> list[str]:
    """Return eligible non-form-A words first; fall back to form-A words only if none remain."""
    pref = _eligible(preferred, used)
    if pref:
        return pref
    return _eligible(fallback, used)


def _has_retest_eligible(
    preferred: tuple[str, ...],
    fallback: tuple[str, ...],
    used: dict[str, int],
) -> bool:
    """True if either preferred or fallback has any word used fewer than _MAX_USES_PER_PART times."""
    return _has_eligible(preferred, used) or _has_eligible(fallback, used)


def _source_bigram(
    tracked: tuple[str, ...],
    coverage: dict[str, int],
    target: int,
    used: dict[str, int],
    by_target: dict[str, tuple[str, ...]],
    rng: random.Random,
) -> str | None:
    """Pick the tracked bigram to source candidate words from this step (plan O1a).

    Prefer a still-under-target bigram (coverage < target) that still has an eligible word,
    choosing the largest remaining deficit (target - coverage) with ties broken by rng over the
    sorted bigrams. When every tracked bigram has reached target, fall back to the lowest-coverage
    bigram that still has an eligible word (to fill the remaining length with real words). Return
    None when no tracked bigram has any eligible word left this part (the part then ends).
    """
    under = [
        bigram
        for bigram in tracked
        if coverage[bigram] < target and _has_eligible(by_target[bigram], used)
    ]
    if under:
        most = max(target - coverage[bigram] for bigram in under)
        tied = sorted(bigram for bigram in under if target - coverage[bigram] == most)
        return rng.choice(tied)
    available = [bigram for bigram in tracked if _has_eligible(by_target[bigram], used)]
    if not available:
        return None
    lowest = min(coverage[bigram] for bigram in available)
    tied = sorted(bigram for bigram in available if coverage[bigram] == lowest)
    return rng.choice(tied)


def _choose_word(
    eligible: list[str],
    candidates: dict[str, _Candidate],
    coverage: dict[str, int],
    target: int,
    rng: random.Random,
    *,
    use_assigned_only: bool = False,
) -> str:
    """Deficit-weighted, per-unit-length selection among eligible (plan O1a; 13.3 step 4).

    Each word's gain is the sum over its relevant bigrams of max(target - coverage[b], 0), divided
    by len(word) + 1 (per unit length including the following space). Words are ranked by gain
    descending, then log-frequency descending (a mild tie-break), then the word ascending; one of
    the top _TOP_CANDIDATES is softmax-sampled with temperature _TEMPERATURE using rng.
    """

    def gain(word: str) -> float:
        bigrams = (
            candidates[word].assigned_bigrams
            if use_assigned_only
            else candidates[word].target_bigrams
        )
        contribution = sum(max(target - coverage[bigram], 0) for bigram in bigrams)
        return contribution / (len(word) + 1)

    ranked = sorted(
        ((gain(word), word) for word in eligible),
        key=lambda item: (-item[0], -candidates[item[1]].log_frequency, item[1]),
    )
    pool = ranked[:_TOP_CANDIDATES]
    scores = [score for score, _ in pool]
    words = [word for _, word in pool]
    highest = max(scores)
    weights = [math.exp((score - highest) / _TEMPERATURE) for score in scores]
    threshold = rng.random() * sum(weights)
    cumulative = 0.0
    for word, weight in zip(words, weights, strict=True):
        cumulative += weight
        if threshold <= cumulative:
            return word
    return words[-1]


def compose_baseline(
    config: BaselineConfig, index: WordIndex, rng: random.Random
) -> list[TextPassage]:
    """Compose config.baseline_parts shared form A passages with the coverage-efficient composer.

    Pure: returns TextPassage rows (kind='baseline', form='A', participant_id=None, part=i),
    with text over a-z + single spaces (no leading/trailing space) and bigram_counts the
    letter-letter counts of that text. Deterministic for a given rng and WordIndex. Coverage is
    shared across parts; the per-part word-use limit resets each part.
    """
    tracked = tuple(index.tracked_bigrams[: config.tracked_bigram_count])
    tracked_set = set(tracked)
    target = config.baseline_min_occurrences
    candidates: dict[str, _Candidate] = {}
    grouped: dict[str, list[str]] = {bigram: [] for bigram in tracked}
    for word in index.words:
        if not (_MIN_WORD_LEN <= len(word) <= _MAX_WORD_LEN):
            continue
        word_bg = word_bigrams(word)
        targets = tuple(bigram for bigram in word_bg if bigram in tracked_set)
        if not targets:
            continue
        candidates[word] = _Candidate(
            log_frequency=math.log(index.frequencies[word]), target_bigrams=targets
        )
        for bigram in set(targets):
            grouped[bigram].append(word)
    for bigram in tracked:
        grouped[bigram].sort(key=lambda word: (-candidates[word].log_frequency, word))
    by_target: dict[str, tuple[str, ...]] = {
        bigram: tuple(members) for bigram, members in grouped.items()
    }

    coverage: dict[str, int] = dict.fromkeys(tracked, 0)
    passages: list[TextPassage] = []
    for part in range(config.baseline_parts):
        used: dict[str, int] = {}
        chosen_words: list[str] = []
        length = 0
        while length < config.baseline_part_chars:
            source = _source_bigram(tracked, coverage, target, used, by_target, rng)
            if source is None:
                break
            eligible = _eligible(by_target[source], used)
            word = _choose_word(eligible, candidates, coverage, target, rng)
            used[word] = used.get(word, 0) + 1
            for bigram in candidates[word].target_bigrams:
                coverage[bigram] += 1
            length += len(word) + (1 if chosen_words else 0)
            chosen_words.append(word)
        text = " ".join(chosen_words)
        passages.append(
            TextPassage(
                kind="baseline",
                form="A",
                part=part,
                participant_id=None,
                text=text,
                bigram_counts=count_bigrams(text),
            )
        )
    return passages


def compose_retest(
    config: RetestConfig,
    index: WordIndex,
    participant_id: str,
    assigned_bigrams: Sequence[str],
    rng: random.Random,
    *,
    excluded_words: Collection[str] = (),
) -> list[TextPassage]:
    """Compose config.retest_parts per-participant form B passages (design doc 3.2, 3.5, 8.1, 16; T2.7).

    Pure: returns TextPassage rows (kind='retest', form='B', participant_id=participant_id, part=i)
    over a-z + single spaces (no leading/trailing space) with bigram_counts = count_bigrams(text).
    Guarantees at least config.retest_min_occurrences (40) combined occurrences across the parts for
    every bigram in assigned_bigrams, while strictly preferring words not in excluded_words (form A
    words) and falling back to excluded_words only when a source bigram has zero eligible non-form-A
    words left in the current part. Raises ValueError if participant_id or assigned_bigrams is empty
    or if any assigned bigram has no usable words of length 2..10 in index.
    """
    if not participant_id:
        raise ValueError("participant_id must not be empty")
    assigned = tuple(dict.fromkeys(assigned_bigrams))
    if not assigned:
        raise ValueError("assigned_bigrams must not be empty")

    top_tracked = tuple(index.tracked_bigrams[: config.tracked_bigram_count])
    tracked = tuple(dict.fromkeys((*top_tracked, *assigned)))
    tracked_set = set(tracked)
    assigned_set = set(assigned)
    excluded_set = frozenset(excluded_words)

    candidates: dict[str, _Candidate] = {}
    grouped_preferred: dict[str, list[str]] = {bigram: [] for bigram in tracked}
    grouped_fallback: dict[str, list[str]] = {bigram: [] for bigram in tracked}

    for word in index.words:
        if not (_MIN_WORD_LEN <= len(word) <= _MAX_WORD_LEN):
            continue
        word_bg = word_bigrams(word)
        targets = tuple(bigram for bigram in word_bg if bigram in tracked_set)
        if not targets:
            continue
        assigned_targets = tuple(bigram for bigram in targets if bigram in assigned_set)
        candidates[word] = _Candidate(
            log_frequency=math.log(index.frequencies[word]),
            target_bigrams=targets,
            assigned_bigrams=assigned_targets,
        )
        bucket = grouped_fallback if word in excluded_set else grouped_preferred
        for bigram in set(targets):
            bucket[bigram].append(word)

    for bigram in tracked:
        grouped_preferred[bigram].sort(key=lambda word: (-candidates[word].log_frequency, word))
        grouped_fallback[bigram].sort(key=lambda word: (-candidates[word].log_frequency, word))

    preferred: dict[str, tuple[str, ...]] = {
        bigram: tuple(members) for bigram, members in grouped_preferred.items()
    }
    fallback: dict[str, tuple[str, ...]] = {
        bigram: tuple(members) for bigram, members in grouped_fallback.items()
    }

    for bigram in assigned:
        if not preferred[bigram] and not fallback[bigram]:
            raise ValueError(f"assigned bigram {bigram!r} has no usable words in index")

    coverage: dict[str, int] = dict.fromkeys(tracked, 0)
    passages: list[TextPassage] = []

    for part in range(config.retest_parts):
        part_target = (
            config.retest_min_occurrences
            if part == config.retest_parts - 1
            else math.ceil(config.retest_min_occurrences * (part + 1) / config.retest_parts)
        )
        used: dict[str, int] = {}
        chosen_words: list[str] = []
        length = 0

        while True:
            under_assigned = [
                bigram
                for bigram in assigned
                if coverage[bigram] < part_target
                and _has_retest_eligible(preferred[bigram], fallback[bigram], used)
            ]
            if under_assigned:
                most = max(part_target - coverage[bigram] for bigram in under_assigned)
                tied = sorted(
                    bigram for bigram in under_assigned if part_target - coverage[bigram] == most
                )
                source = rng.choice(tied)
                eligible = _retest_eligible(preferred[source], fallback[source], used)
                word = _choose_word(
                    eligible,
                    candidates,
                    coverage,
                    part_target,
                    rng,
                    use_assigned_only=True,
                )
            elif length < config.retest_part_chars:
                # Prefer bigrams that still have non-form-A words available during filler,
                # falling back to form-A words only if every tracked bigram exhausted preferred.
                pref_available = [
                    bigram for bigram in tracked if _has_eligible(preferred[bigram], used)
                ]
                pool_bigrams = (
                    pref_available
                    if pref_available
                    else [
                        bigram
                        for bigram in tracked
                        if _has_retest_eligible(preferred[bigram], fallback[bigram], used)
                    ]
                )
                if not pool_bigrams:
                    break
                lowest = min(coverage[bigram] for bigram in pool_bigrams)
                tied = sorted(bigram for bigram in pool_bigrams if coverage[bigram] == lowest)
                source = rng.choice(tied)
                eligible = _retest_eligible(preferred[source], fallback[source], used)
                filler_target = max(coverage[source] + 1, config.retest_min_occurrences)
                word = _choose_word(
                    eligible,
                    candidates,
                    coverage,
                    filler_target,
                    rng,
                    use_assigned_only=False,
                )
            else:
                break

            used[word] = used.get(word, 0) + 1
            for bigram in candidates[word].target_bigrams:
                coverage[bigram] += 1
            length += len(word) + (1 if chosen_words else 0)
            chosen_words.append(word)

        text = " ".join(chosen_words)
        passages.append(
            TextPassage(
                kind="retest",
                form="B",
                part=part,
                participant_id=participant_id,
                text=text,
                bigram_counts=count_bigrams(text),
            )
        )
    return passages


def persist_baseline(
    session: Session, passages: list[TextPassage], *, replace: bool = False
) -> BaselinePersistResult:
    """Write the composed shared form A passages idempotently; commit. Statuses: see the dataclass.

    No existing shared form A rows -> insert ('created'). Existing rows byte-identical to the
    composed texts -> no write ('unchanged'). Different and replace is False -> BaselineTextsDiffer
    Error. Different and replace is True -> BaselinePassagesInUseError if any session_blocks row
    references a form A passage, else delete the old rows and insert the new ones ('replaced').
    """
    existing = list(
        session.exec(
            select(TextPassage)
            .where(
                col(TextPassage.kind) == "baseline",
                col(TextPassage.form) == "A",
                col(TextPassage.participant_id).is_(None),
            )
            .order_by(col(TextPassage.part))
        ).all()
    )
    composed_by_part = {passage.part: passage.text for passage in passages}
    if not existing:
        session.add_all(passages)
        session.commit()
        return BaselinePersistResult(status="created", parts=len(passages))
    if {passage.part: passage.text for passage in existing} == composed_by_part:
        return BaselinePersistResult(status="unchanged", parts=len(existing))
    if not replace:
        raise BaselineTextsDifferError("shared form A passages already exist and differ")
    existing_ids = [passage.id for passage in existing]
    referenced = session.exec(
        select(SessionBlock.id).where(col(SessionBlock.passage_id).in_(existing_ids))
    ).first()
    if referenced is not None:
        raise BaselinePassagesInUseError("a session block references a form A passage")
    for passage in existing:
        session.delete(passage)
    session.flush()
    session.add_all(passages)
    session.commit()
    return BaselinePersistResult(status="replaced", parts=len(passages))


def persist_retest(
    session: Session,
    participant_id: str,
    passages: list[TextPassage],
    *,
    replace: bool = False,
) -> RetestPersistResult:
    """Write a participant's composed form B passages idempotently; commit (T2.7).

    No existing form B rows for participant_id -> insert ('created'). Existing rows byte-identical
    to the composed texts -> no write ('unchanged'). Different and replace is False ->
    RetestTextsDifferError. Different and replace is True -> RetestPassagesInUseError if any
    session_blocks row references one of this participant's form B passages, else delete the old
    rows and insert the new ones ('replaced').
    """
    if session.get(Participant, participant_id) is None:
        raise ParticipantNotFoundError(participant_id)
    existing = list(
        session.exec(
            select(TextPassage)
            .where(
                col(TextPassage.kind) == "retest",
                col(TextPassage.form) == "B",
                col(TextPassage.participant_id) == participant_id,
            )
            .order_by(col(TextPassage.part))
        ).all()
    )
    composed_by_part = {passage.part: passage.text for passage in passages}
    if not existing:
        session.add_all(passages)
        session.commit()
        return RetestPersistResult(
            status="created", parts=len(passages), participant_id=participant_id
        )
    if {passage.part: passage.text for passage in existing} == composed_by_part:
        return RetestPersistResult(
            status="unchanged", parts=len(existing), participant_id=participant_id
        )
    if not replace:
        raise RetestTextsDifferError(
            f"form B passages for participant {participant_id!r} already exist and differ"
        )
    existing_ids = [passage.id for passage in existing]
    referenced = session.exec(
        select(SessionBlock.id).where(col(SessionBlock.passage_id).in_(existing_ids))
    ).first()
    if referenced is not None:
        raise RetestPassagesInUseError(
            f"a session block references a form B passage for participant {participant_id!r}"
        )
    for passage in existing:
        session.delete(passage)
    session.flush()
    session.add_all(passages)
    session.commit()
    return RetestPersistResult(
        status="replaced", parts=len(passages), participant_id=participant_id
    )


def compose_and_persist_retest(
    session: Session,
    participant_id: str,
    index: WordIndex,
    *,
    rng: random.Random | None = None,
    replace: bool = False,
) -> RetestPersistResult:
    """Load config, frozen assigned bigrams, and form A words; compose and persist form B (T2.7).

    Defaults rng to random.Random(f"{config.corpus_seed}:{participant_id}:B") (owner answer 4).
    """
    config = load_retest_config(session)
    assigned = load_assigned_bigrams(session, participant_id)
    form_a_words = load_form_a_words(session)
    effective_rng = (
        rng if rng is not None else random.Random(f"{config.corpus_seed}:{participant_id}:B")
    )
    passages = compose_retest(
        config,
        index,
        participant_id,
        assigned,
        effective_rng,
        excluded_words=form_a_words,
    )
    return persist_retest(session, participant_id, passages, replace=replace)
