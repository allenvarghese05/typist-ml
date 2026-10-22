"""The single fairness gate for every generated drill (design doc 9.1, 13.1; D13, D16).

validate is a pure function: it measures one candidate text against its DrillSpec and a
ValidatorConfig, collects EVERY failing rule (never stops at the first; the rejection-rate report
needs the full taxonomy, section 8.1), and returns the recorded fairness metrics alongside the
verdict. It never mutates text (cleaning is the generator's job, owner answer 6) and never raises
on generator output (owner answer 9). It reuses the one project bigram definition
(count_bigrams/word_bigrams; CLAUDE.md, D13) and so can run on Linux CI (no mlx-lm). The density
bounds come from the spec (min_density/max_density); the length floor, coverage/repeat limits and
the real-word-ratio threshold come from config, never as literals (section 17.1). Density and
coverage are skipped when the spec has no targets (control; owner answer 4). The real-word ratio is
recorded for every arm but gates only the LLM arm (13.1). load_validator_config reads the six keys
from experiment_config, following assignment.py's loader pattern.
"""

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum

from sqlmodel import Session

from typist.corpus.word_index import count_bigrams, word_bigrams
from typist.generation.base import Arm, DrillSpec
from typist.models import ExperimentConfig


class RejectReason(StrEnum):
    """The reason tokens stored in generation_attempts.reject_reasons (owner answer 2). The order
    here is the order reasons appear in a ValidationResult."""

    TOO_SHORT = "too_short"
    BAD_CHARSET = "bad_charset"
    DENSITY_LOW = "density_low"
    DENSITY_HIGH = "density_high"
    COVERAGE = "coverage"
    WORD_REPEAT = "word_repeat"
    BIGRAM_REPEAT = "bigram_repeat"
    REAL_WORD_RATIO = "real_word_ratio"


class MissingConfigError(LookupError):
    """An experiment_config key the validator needs is absent (run migrations)."""


@dataclass(frozen=True)
class ValidatorConfig:
    """The experiment_config values the validator needs (owner answer 5; migration 0006). The
    density bounds are NOT here -- they live on the DrillSpec."""

    min_length_chars: int
    min_coverage: int
    max_word_repeats: int
    max_bigram_run: int
    min_real_word_ratio: float


@dataclass(frozen=True)
class DrillMetrics:
    """The measured metrics for one candidate (owner answer 2). target_density, mean_word_len and
    real_word_ratio are recorded on drills; length_chars/coverage/max_word_count/bigram_run drive
    the rules. For a targetless spec target_density is 0.0 and coverage is empty."""

    length_chars: int
    target_density: float
    mean_word_len: float
    real_word_ratio: float
    coverage: dict[str, int]
    max_word_count: int
    bigram_run: int


@dataclass(frozen=True)
class ValidationResult:
    """The validator's verdict (owner answer 2). accepted is True iff reasons is empty; reasons is
    in RejectReason definition order; metrics is always populated."""

    accepted: bool
    reasons: tuple[RejectReason, ...]
    metrics: DrillMetrics


_VALIDATOR_CONFIG_KEYS = (
    "drill_min_length_chars",
    "drill_min_coverage",
    "drill_max_word_repeats",
    "drill_max_bigram_run",
    "drill_min_real_word_ratio",
)


def _charset_ok(text: str) -> bool:
    """True iff text is non-empty, is only a-z and single spaces, and has no leading/trailing or
    doubled space (13.1 "Lowercase a to z and single spaces only"; owner answer 6)."""
    if not text:
        return False
    if text[0] == " " or text[-1] == " " or "  " in text:
        return False
    return all("a" <= char <= "z" or char == " " for char in text)


def _longest_bigram_run(text: str) -> int:
    """The longest run of the same bigram at consecutive letter positions within one word, counting
    the same bigram starting at every other position (owner answer 7). "thth" -> 2, "ththth" -> 3;
    never across a space. 0 when no word has a bigram."""
    longest = 0
    for word in text.split(" "):
        bigrams = word_bigrams(word)
        for start in range(len(bigrams)):
            run = 1
            index = start
            while index + 2 < len(bigrams) and bigrams[index + 2] == bigrams[start]:
                run += 1
                index += 2
            longest = max(longest, run)
    return longest


def _metrics(
    text: str, spec: DrillSpec, known_words: Collection[str]
) -> DrillMetrics:
    """Measure one candidate. Density is Σ(target bigram occurrences) / all letter-letter bigrams
    (owner answer 4), 0.0 when there are no targets or no bigrams. mean_word_len and real_word_ratio
    are over the space-split tokens (0.0 for empty text). Uses count_bigrams/word_bigrams only."""
    counts = count_bigrams(text)
    total = sum(counts.values())
    coverage = {bigram: counts.get(bigram, 0) for bigram in spec.target_bigrams}
    target_occurrences = sum(coverage.values())
    density = (
        target_occurrences / total if spec.target_bigrams and total > 0 else 0.0
    )
    tokens = text.split(" ")
    mean_word_len = sum(len(token) for token in tokens) / len(tokens) if tokens else 0.0
    real_word_ratio = (
        sum(1 for token in tokens if token in known_words) / len(tokens)
        if tokens
        else 0.0
    )
    max_word_count = max((tokens.count(token) for token in set(tokens)), default=0)
    return DrillMetrics(
        length_chars=len(text),
        target_density=density,
        mean_word_len=mean_word_len,
        real_word_ratio=real_word_ratio,
        coverage=coverage,
        max_word_count=max_word_count,
        bigram_run=_longest_bigram_run(text),
    )


def validate(
    text: str,
    spec: DrillSpec,
    config: ValidatorConfig,
    known_words: Collection[str],
) -> ValidationResult:
    """Measure text and collect every failing rule (never stop at the first; owner answer 2).

    Rules (13.1, D16): too_short when len(text) < config.min_length_chars; bad_charset when text is
    empty or has anything but a-z and single spaces, or a leading/trailing/doubled space; for a
    targeted spec, density_low/density_high when the single density is below spec.min_density or
    above spec.max_density (bounds inclusive), and coverage when any target occurs fewer than
    config.min_coverage times; word_repeat when any token occurs more than config.max_word_repeats
    times; bigram_repeat when the longest bigram run reaches config.max_bigram_run (owner answer 7);
    real_word_ratio only for Arm.LLM when the ratio is below config.min_real_word_ratio. Density and
    coverage are skipped when spec.target_bigrams is empty (owner answer 4/8). Pure: no DB, never
    raises. known_words is any membership collection (the service passes WordIndex.words).
    """
    metrics = _metrics(text, spec, known_words)
    reasons: list[RejectReason] = []
    if metrics.length_chars < config.min_length_chars:
        reasons.append(RejectReason.TOO_SHORT)
    if not _charset_ok(text):
        reasons.append(RejectReason.BAD_CHARSET)
    if spec.target_bigrams:
        if metrics.target_density < spec.min_density:
            reasons.append(RejectReason.DENSITY_LOW)
        if metrics.target_density > spec.max_density:
            reasons.append(RejectReason.DENSITY_HIGH)
        if any(count < config.min_coverage for count in metrics.coverage.values()):
            reasons.append(RejectReason.COVERAGE)
    if metrics.max_word_count > config.max_word_repeats:
        reasons.append(RejectReason.WORD_REPEAT)
    if metrics.bigram_run >= config.max_bigram_run:
        reasons.append(RejectReason.BIGRAM_REPEAT)
    if spec.arm is Arm.LLM and metrics.real_word_ratio < config.min_real_word_ratio:
        reasons.append(RejectReason.REAL_WORD_RATIO)
    return ValidationResult(
        accepted=not reasons, reasons=tuple(reasons), metrics=metrics
    )


def load_validator_config(session: Session) -> ValidatorConfig:
    """Read the five validator keys from experiment_config; raise MissingConfigError if any is
    absent (run migrations). Four are integers; drill_min_real_word_ratio is a float. (The sixth
    seeded key, drill_length_chars, is read by the GenerationService for DrillSpec.length_chars, not
    by the validator.)"""
    values: dict[str, str] = {}
    for key in _VALIDATOR_CONFIG_KEYS:
        row = session.get(ExperimentConfig, key)
        if row is None:
            raise MissingConfigError(key)
        values[key] = row.value
    return ValidatorConfig(
        min_length_chars=int(values["drill_min_length_chars"]),
        min_coverage=int(values["drill_min_coverage"]),
        max_word_repeats=int(values["drill_max_word_repeats"]),
        max_bigram_run=int(values["drill_max_bigram_run"]),
        min_real_word_ratio=float(values["drill_min_real_word_ratio"]),
    )
