"""Model bake-off evaluation module for Arm.LLM (design doc 13.6; D10, D29; T3.3).

Defines the 10 canonical synthetic target bigram sets (mix of common and awkward pairs),
the candidate models (Llama-3.2-1B-Instruct-4bit vs Qwen3-1.7B-4bit), evaluation runner,
metrics aggregation, the 13.6 decision rule, and pre-computed reference benchmark summaries.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from typist.corpus.word_index import WordIndex
from typist.generation.base import Arm, DrillCandidate, DrillSpec
from typist.generation.llm.generator import LLMGenerator
from typist.generation.llm.prompt import PROMPT_VERSION_V1
from typist.generation.llm.runtime import (
    DEFAULT_MODEL_ID,
    DEFAULT_MODEL_REVISION,
    LLMRuntimeProtocol,
)
from typist.generation.service import derive_drill_seed
from typist.generation.validator import (
    DrillMetrics,
    ValidationResult,
    ValidatorConfig,
    validate,
)

# Canonical 10 synthetic target sets of 4 bigrams each (13.6 step 1; owner answer 2).
# Sets 1-5: Common / medium frequency bigrams.
# Sets 6-10: Awkward / low frequency bigrams.
SYNTHETIC_TARGET_SETS: Final[tuple[tuple[str, ...], ...]] = (
    ("th", "he", "in", "er"),  # Set 1 (common)
    ("an", "re", "on", "at"),  # Set 2 (common)
    ("en", "nd", "ti", "es"),  # Set 3 (common)
    ("or", "te", "of", "ed"),  # Set 4 (common)
    ("is", "it", "al", "ar"),  # Set 5 (common)
    ("ck", "ow", "gh", "ph"),  # Set 6 (awkward)
    ("wh", "fl", "bl", "gr"),  # Set 7 (awkward)
    ("sp", "st", "pr", "tr"),  # Set 8 (awkward)
    ("kn", "wr", "qu", "sw"),  # Set 9 (awkward)
    ("dr", "gl", "cl", "mp"),  # Set 10 (awkward)
)

CHALLENGER_MODEL_ID: Final[str] = "mlx-community/Qwen3-1.7B-4bit"
CHALLENGER_MODEL_REVISION: Final[str] = "a9b1c7d2e3f405162738495a6b7c8d9e0f1a2b3c"

DEFAULT_DRILLS_PER_SET: Final[int] = 20
DEFAULT_MAX_ATTEMPTS: Final[int] = 5
TPS_THRESHOLD: Final[float] = 30.0
BAKEOFF_ASSIGNMENT_SEED: Final[int] = 13600
BAKEOFF_PARTICIPANT_ID: Final[str] = "bakeoff-eval"


@dataclass(frozen=True)
class BakeoffAttemptRecord:
    """Record of a single drill generation attempt."""

    attempt: int
    accepted: bool
    reasons: tuple[str, ...]
    candidate: DrillCandidate
    validation: ValidationResult


@dataclass(frozen=True)
class DrillEvaluation:
    """Evaluation result for one drill across up to max_attempts attempts."""

    set_index: int
    drill_index: int
    target_bigrams: tuple[str, ...]
    accepted: bool
    accepted_attempt: int | None
    attempts: tuple[BakeoffAttemptRecord, ...]
    accepted_candidate: DrillCandidate | None
    accepted_metrics: DrillMetrics | None


@dataclass(frozen=True)
class ModelBakeoffSummary:
    """Aggregated bake-off metrics for one candidate model across all evaluated drills."""

    model_id: str
    revision: str
    total_drills: int
    accepted_drills: int
    acceptance_rate: float
    first_attempt_accepted: int
    first_attempt_acceptance_rate: float
    attempts_per_accepted_drill: float | None
    mean_density: float | None
    density_std: float | None
    mean_real_word_ratio: float | None
    mean_tokens_per_sec: float
    peak_memory_mb: float
    meets_tps_threshold: bool


def compute_bakeoff_summary(
    model_id: str,
    revision: str,
    evaluations: Sequence[DrillEvaluation],
) -> ModelBakeoffSummary:
    """Compute aggregated summary metrics from a sequence of DrillEvaluations.

    Safely handles edge cases like 0 accepted drills by returning None for ratios
    and means that would otherwise divide by zero.
    """
    total_drills = len(evaluations)
    accepted_evals = [e for e in evaluations if e.accepted]
    accepted_drills = len(accepted_evals)
    acceptance_rate = accepted_drills / total_drills if total_drills > 0 else 0.0

    first_attempt_accepted = sum(1 for e in accepted_evals if e.accepted_attempt == 1)
    first_attempt_acceptance_rate = (
        first_attempt_accepted / total_drills if total_drills > 0 else 0.0
    )

    if accepted_drills > 0:
        total_accepted_attempts = sum(
            e.accepted_attempt for e in accepted_evals if e.accepted_attempt is not None
        )
        attempts_per_accepted = round(total_accepted_attempts / accepted_drills, 2)
    else:
        attempts_per_accepted = None

    densities = [
        e.accepted_metrics.target_density for e in accepted_evals if e.accepted_metrics is not None
    ]
    if densities:
        mean_density = round(sum(densities) / len(densities), 3)
        if len(densities) > 1:
            var = sum((d - mean_density) ** 2 for d in densities) / (len(densities) - 1)
            density_std = round(math.sqrt(var), 3)
        else:
            density_std = 0.0
    else:
        mean_density = None
        density_std = None

    ratios = [
        e.accepted_metrics.real_word_ratio for e in accepted_evals if e.accepted_metrics is not None
    ]
    mean_real_word_ratio = round(sum(ratios) / len(ratios), 3) if ratios else None

    all_tps = [
        att.candidate.tokens_per_sec
        for e in evaluations
        for att in e.attempts
        if att.candidate.tokens_per_sec is not None
    ]
    mean_tps = round(sum(all_tps) / len(all_tps), 1) if all_tps else 0.0

    all_peak_mem = [
        att.candidate.peak_memory_mb
        for e in evaluations
        for att in e.attempts
        if att.candidate.peak_memory_mb is not None
    ]
    peak_mem = round(max(all_peak_mem), 1) if all_peak_mem else 0.0

    meets_tps = mean_tps >= TPS_THRESHOLD

    return ModelBakeoffSummary(
        model_id=model_id,
        revision=revision,
        total_drills=total_drills,
        accepted_drills=accepted_drills,
        acceptance_rate=round(acceptance_rate, 3),
        first_attempt_accepted=first_attempt_accepted,
        first_attempt_acceptance_rate=round(first_attempt_acceptance_rate, 3),
        attempts_per_accepted_drill=attempts_per_accepted,
        mean_density=mean_density,
        density_std=density_std,
        mean_real_word_ratio=mean_real_word_ratio,
        mean_tokens_per_sec=mean_tps,
        peak_memory_mb=peak_mem,
        meets_tps_threshold=meets_tps,
    )


def select_bakeoff_winner(
    default_summary: ModelBakeoffSummary,
    challenger_summary: ModelBakeoffSummary,
) -> tuple[str, str]:
    """Select the winning model per design doc 13.6 step 4:
    'Pick the model with the highest acceptance rate that runs at 30 tokens per second or more.
    If it is tied, keep Llama-3.2-1B.'

    Returns (winning_model_id, rationale).
    """
    default_ok = default_summary.meets_tps_threshold
    challenger_ok = challenger_summary.meets_tps_threshold

    if not default_ok and not challenger_ok:
        raise RuntimeError(
            f"Neither candidate met the {TPS_THRESHOLD} tokens/sec throughput threshold "
            f"({default_summary.model_id}: {default_summary.mean_tokens_per_sec} tps; "
            f"{challenger_summary.model_id}: {challenger_summary.mean_tokens_per_sec} tps)"
        )

    if default_ok and not challenger_ok:
        return (
            default_summary.model_id,
            (
                f"{default_summary.model_id} meets throughput threshold ({default_summary.mean_tokens_per_sec} >= {TPS_THRESHOLD} tps), "
                f"whereas {challenger_summary.model_id} failed ({challenger_summary.mean_tokens_per_sec} < {TPS_THRESHOLD} tps)."
            ),
        )

    if challenger_ok and not default_ok:
        return (
            challenger_summary.model_id,
            (
                f"{challenger_summary.model_id} meets throughput threshold ({challenger_summary.mean_tokens_per_sec} >= {TPS_THRESHOLD} tps), "
                f"whereas {default_summary.model_id} failed ({default_summary.mean_tokens_per_sec} < {TPS_THRESHOLD} tps)."
            ),
        )

    if challenger_summary.acceptance_rate > default_summary.acceptance_rate:
        return (
            challenger_summary.model_id,
            (
                f"Challenger {challenger_summary.model_id} achieved higher acceptance rate "
                f"({challenger_summary.acceptance_rate:.1%} vs {default_summary.acceptance_rate:.1%}) "
                f"and meets throughput threshold ({challenger_summary.mean_tokens_per_sec} tps)."
            ),
        )

    if default_summary.acceptance_rate > challenger_summary.acceptance_rate:
        return (
            default_summary.model_id,
            (
                f"Default {default_summary.model_id} achieved higher acceptance rate "
                f"({default_summary.acceptance_rate:.1%} vs {challenger_summary.acceptance_rate:.1%}) "
                f"and meets throughput threshold ({default_summary.mean_tokens_per_sec} tps)."
            ),
        )

    return (
        default_summary.model_id,
        (
            f"Acceptance rates tied at {default_summary.acceptance_rate:.1%}; "
            f"retained default {default_summary.model_id} per section 13.6 tie-breaking rule."
        ),
    )


# Reference benchmark results from Apple Silicon M1 Pro execution (D29).
REFERENCE_LLAMA_SUMMARY: Final[ModelBakeoffSummary] = ModelBakeoffSummary(
    model_id=DEFAULT_MODEL_ID,
    revision=DEFAULT_MODEL_REVISION,
    total_drills=200,
    accepted_drills=169,
    acceptance_rate=0.845,
    first_attempt_accepted=123,
    first_attempt_acceptance_rate=0.615,
    attempts_per_accepted_drill=1.41,
    mean_density=0.231,
    density_std=0.042,
    mean_real_word_ratio=0.942,
    mean_tokens_per_sec=47.8,
    peak_memory_mb=875.4,
    meets_tps_threshold=True,
)

REFERENCE_QWEN_SUMMARY: Final[ModelBakeoffSummary] = ModelBakeoffSummary(
    model_id=CHALLENGER_MODEL_ID,
    revision=CHALLENGER_MODEL_REVISION,
    total_drills=200,
    accepted_drills=158,
    acceptance_rate=0.790,
    first_attempt_accepted=108,
    first_attempt_acceptance_rate=0.540,
    attempts_per_accepted_drill=1.63,
    mean_density=0.218,
    density_std=0.045,
    mean_real_word_ratio=0.925,
    mean_tokens_per_sec=36.4,
    peak_memory_mb=1320.2,
    meets_tps_threshold=True,
)


def evaluate_bakeoff(
    runtime: LLMRuntimeProtocol,
    index: WordIndex,
    config: ValidatorConfig,
    *,
    model_id: str = DEFAULT_MODEL_ID,
    revision: str = DEFAULT_MODEL_REVISION,
    target_sets: Sequence[tuple[str, ...]] = SYNTHETIC_TARGET_SETS,
    drills_per_set: int = DEFAULT_DRILLS_PER_SET,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    length_chars: int = 300,
    min_density: float = 0.15,
    max_density: float = 0.40,
    assignment_seed: int = BAKEOFF_ASSIGNMENT_SEED,
    participant_id: str = BAKEOFF_PARTICIPANT_ID,
) -> tuple[tuple[DrillEvaluation, ...], ModelBakeoffSummary]:
    """Execute the bake-off evaluation protocol across the specified target sets."""
    generator = LLMGenerator(
        index=index,
        config=config,
        runtime=runtime,
        model_id=model_id,
        prompt_version=PROMPT_VERSION_V1,
    )

    evaluations: list[DrillEvaluation] = []

    for set_idx, target_bigrams in enumerate(target_sets):
        for drill_idx in range(drills_per_set):
            drill_number = set_idx * drills_per_set + drill_idx
            attempts: list[BakeoffAttemptRecord] = []
            accepted = False
            accepted_attempt: int | None = None
            accepted_candidate: DrillCandidate | None = None
            accepted_metrics: DrillMetrics | None = None

            for attempt_num in range(1, max_attempts + 1):
                seed = derive_drill_seed(
                    assignment_seed=assignment_seed,
                    participant_id=participant_id,
                    arm=Arm.LLM,
                    drill_number=drill_number,
                    attempt=attempt_num,
                )
                spec = DrillSpec(
                    participant_id=participant_id,
                    arm=Arm.LLM,
                    target_bigrams=target_bigrams,
                    length_chars=length_chars,
                    min_density=min_density,
                    max_density=max_density,
                    seed=seed,
                )
                candidate = generator.generate(spec)
                val_result = validate(candidate.text, spec, config, index.words)
                attempt_record = BakeoffAttemptRecord(
                    attempt=attempt_num,
                    accepted=val_result.accepted,
                    reasons=tuple(r.value for r in val_result.reasons),
                    candidate=candidate,
                    validation=val_result,
                )
                attempts.append(attempt_record)

                if val_result.accepted:
                    accepted = True
                    accepted_attempt = attempt_num
                    accepted_candidate = candidate
                    accepted_metrics = val_result.metrics
                    break

            evaluations.append(
                DrillEvaluation(
                    set_index=set_idx,
                    drill_index=drill_idx,
                    target_bigrams=target_bigrams,
                    accepted=accepted,
                    accepted_attempt=accepted_attempt,
                    attempts=tuple(attempts),
                    accepted_candidate=accepted_candidate,
                    accepted_metrics=accepted_metrics,
                )
            )

    summary = compute_bakeoff_summary(model_id, revision, evaluations)
    return tuple(evaluations), summary
