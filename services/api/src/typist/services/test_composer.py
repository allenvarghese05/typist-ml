"""Compose the baseline (form A) texts and write them to text_passages (design doc 13.3; T1.8).

compose_baseline is the pure, seeded, coverage-efficient 13.3 composer (plan O1a): each step
sources candidates from a tracked bigram still under baseline_min_occurrences (largest deficit
first, ties broken by the caller's random generator; falling back to the lowest-coverage bigram
once all are satisfied), scores eligible words by their deficit-weighted still-under-target bigram
contribution per unit length (log-frequency a mild tie-break), softmax-samples one of the top 50,
and repeats until each part reaches its character budget (13.3). Coverage is shared across the two
parts so part 1 keeps lifting whatever part 0 left lowest; the "at most twice" word-use limit
resets per part (owner answer 8). It
returns TextPassage rows and touches no database. persist_baseline is the only DB writer: it is
idempotent and refuses to overwrite a form A passage a session block already references
(owner answer 7). frozen_at enforcement is T3.5.
"""

import math
import random
from dataclasses import dataclass

from sqlmodel import Session, col, select

from typist.corpus.word_index import WordIndex, count_bigrams, word_bigrams
from typist.models import ExperimentConfig, SessionBlock, TextPassage

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


@dataclass(frozen=True)
class BaselineConfig:
    """The experiment_config values the baseline composer needs (all integers)."""

    tracked_bigram_count: int
    baseline_min_occurrences: int
    baseline_parts: int
    baseline_part_chars: int
    corpus_seed: int


class MissingConfigError(LookupError):
    """An experiment_config key the baseline composer needs is absent (run migrations)."""


class BaselineTextsDifferError(RuntimeError):
    """Shared form A passages already exist and differ from the composed texts (need --replace)."""


class BaselinePassagesInUseError(RuntimeError):
    """A session block references a form A passage, so it must not be replaced (freeze guard)."""


@dataclass(frozen=True)
class BaselinePersistResult:
    """Outcome of persist_baseline: status is 'created', 'unchanged' or 'replaced'."""

    status: str
    parts: int


@dataclass(frozen=True)
class _Candidate:
    """A usable word: its log wordfreq frequency and tracked bigrams (with multiplicity)."""

    log_frequency: float
    target_bigrams: tuple[str, ...]


def load_baseline_config(session: Session) -> BaselineConfig:
    """Read the five baseline keys from experiment_config; raise MissingConfigError if any is absent."""
    values: dict[str, int] = {}
    for key in _BASELINE_CONFIG_KEYS:
        row = session.get(ExperimentConfig, key)
        if row is None:
            raise MissingConfigError(key)
        values[key] = int(row.value)
    return BaselineConfig(**values)


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
) -> str:
    """Deficit-weighted, per-unit-length selection among eligible (plan O1a; 13.3 step 4).

    Each word's gain is the sum over its tracked bigrams of max(target - coverage[b], 0), divided
    by len(word) + 1 (per unit length including the following space). Words are ranked by gain
    descending, then log-frequency descending (a mild tie-break), then the word ascending; one of
    the top _TOP_CANDIDATES is softmax-sampled with temperature _TEMPERATURE using rng.
    """

    def gain(word: str) -> float:
        contribution = sum(
            max(target - coverage[bigram], 0) for bigram in candidates[word].target_bigrams
        )
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
