"""Calibration module for density bounds and targeted arm acceptance (design doc 13.1, 16; D30; T3.4).

Defines the 10 canonical calibration target bigram sets (realistic 4-target sets and 3-target fallback
sets drawn strictly from index.tracked_bigrams per §3.4 and owner answer 1), the calibrated density bounds
[0.10, 0.40], acceptance threshold (0.80), attempt and summary records, and the evaluation runner.
"""

import math
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Final

from typist.generation.base import Arm, DrillCandidate, DrillGenerator, DrillSpec
from typist.generation.service import derive_drill_seed
from typist.generation.validator import (
    ValidationResult,
    ValidatorConfig,
    validate,
)

# Canonical 10 calibration target sets drawn strictly from tracked bigrams (T3.4 owner answer 1).
# Sets 0-5: Realistic 4-target sets spanning common, upper-mid, mid, and lower-mid tracked pairs,
# mimicking snake-split assignments per §3.4.
# Sets 6-9: Representative 3-target fallback sets (§3.4 step 4).
CALIBRATION_TARGET_SETS: Final[tuple[tuple[str, ...], ...]] = (
    ("th", "at", "nd", "is"),  # Set 0: 4-target common snake set 1 (ranks 1, 8, 9, 16)
    ("he", "on", "or", "it"),  # Set 1: 4-target common snake set 2 (ranks 2, 7, 10, 15)
    ("in", "re", "ti", "al"),  # Set 2: 4-target common snake set 3 (ranks 3, 6, 11, 14)
    ("er", "to", "en", "ar"),  # Set 3: 4-target upper-mid snake set (ranks 5, 12, 13, 20)
    ("nd", "is", "es", "ed"),  # Set 4: 4-target mid snake set (ranks 9, 16, 17, 24)
    ("te", "me", "se", "co"),  # Set 5: 4-target lower-mid snake set (ranks 18, 23, 26, 31)
    ("th", "at", "nd"),        # Set 6: 3-target common fallback set 1
    ("he", "on", "or"),        # Set 7: 3-target common fallback set 2
    ("er", "to", "en"),        # Set 8: 3-target upper-mid fallback set
    ("nd", "is", "es"),        # Set 9: 3-target mid fallback set
)

CALIBRATED_D_MIN: Final[float] = 0.10
CALIBRATED_D_MAX: Final[float] = 0.40
ACCEPTANCE_THRESHOLD: Final[float] = 0.80
DEFAULT_CALIBRATION_DRILLS_PER_SET: Final[int] = 10
DEFAULT_CALIBRATION_MAX_ATTEMPTS: Final[int] = 5
CALIBRATION_ASSIGNMENT_SEED: Final[int] = 20261021
CALIBRATION_PARTICIPANT_ID: Final[str] = "p-calibration"


@dataclass(frozen=True)
class CalibrationAttemptRecord:
    """Record of a single attempt during calibration evaluation."""

    attempt: int
    seed: int
    candidate: DrillCandidate
    result: ValidationResult


@dataclass(frozen=True)
class CalibrationDrillRecord:
    """Record of a drill evaluation across up to max_attempts attempts."""

    arm: Arm
    target_bigrams: tuple[str, ...]
    drill_number: int
    accepted: bool
    attempts_used: int
    final_attempt: CalibrationAttemptRecord
    attempts: tuple[CalibrationAttemptRecord, ...]


@dataclass(frozen=True)
class ArmCalibrationSummary:
    """Summary metrics of an arm's evaluation across calibration target sets."""

    arm: Arm
    total_drills: int
    accepted_drills: int
    acceptance_rate: float
    first_attempt_accepted: int
    first_attempt_acceptance_rate: float
    attempts_per_accepted_drill: float
    mean_density: float
    density_std: float
    meets_acceptance_threshold: bool
    drills: tuple[CalibrationDrillRecord, ...]


def evaluate_calibration_drill(
    generator: DrillGenerator,
    target_bigrams: tuple[str, ...],
    drill_number: int,
    config: ValidatorConfig,
    known_words: Collection[str],
    *,
    max_attempts: int = DEFAULT_CALIBRATION_MAX_ATTEMPTS,
    min_density: float = CALIBRATED_D_MIN,
    max_density: float = CALIBRATED_D_MAX,
    assignment_seed: int = CALIBRATION_ASSIGNMENT_SEED,
    participant_id: str = CALIBRATION_PARTICIPANT_ID,
) -> CalibrationDrillRecord:
    """Evaluate one drill across up to max_attempts attempts using deterministic seeds."""
    attempts: list[CalibrationAttemptRecord] = []
    accepted = False
    for attempt in range(1, max_attempts + 1):
        seed = derive_drill_seed(
            assignment_seed=assignment_seed,
            participant_id=participant_id,
            arm=generator.arm,
            drill_number=drill_number,
            attempt=attempt,
        )
        spec = DrillSpec(
            participant_id=participant_id,
            arm=generator.arm,
            target_bigrams=target_bigrams,
            min_density=min_density,
            max_density=max_density,
            seed=seed,
        )
        candidate = generator.generate(spec)
        result = validate(candidate.text, spec, config, known_words)
        record = CalibrationAttemptRecord(
            attempt=attempt,
            seed=seed,
            candidate=candidate,
            result=result,
        )
        attempts.append(record)
        if result.accepted:
            accepted = True
            break

    return CalibrationDrillRecord(
        arm=generator.arm,
        target_bigrams=target_bigrams,
        drill_number=drill_number,
        accepted=accepted,
        attempts_used=len(attempts),
        final_attempt=attempts[-1],
        attempts=tuple(attempts),
    )


def run_arm_calibration(
    generator: DrillGenerator,
    target_sets: Sequence[tuple[str, ...]] = CALIBRATION_TARGET_SETS,
    config: ValidatorConfig | None = None,
    known_words: Collection[str] | None = None,
    *,
    drills_per_set: int = DEFAULT_CALIBRATION_DRILLS_PER_SET,
    max_attempts: int = DEFAULT_CALIBRATION_MAX_ATTEMPTS,
    min_density: float = CALIBRATED_D_MIN,
    max_density: float = CALIBRATED_D_MAX,
    assignment_seed: int = CALIBRATION_ASSIGNMENT_SEED,
    participant_id: str = CALIBRATION_PARTICIPANT_ID,
) -> ArmCalibrationSummary:
    """Run full calibration evaluation for an arm across all target sets."""
    if config is None:
        config = ValidatorConfig(
            min_length_chars=270,
            min_coverage=3,
            max_word_repeats=3,
            max_bigram_run=3,
            min_real_word_ratio=0.8,
        )
    if known_words is None:
        known_words = frozenset()

    drill_records: list[CalibrationDrillRecord] = []
    drill_counter = 0

    for target_set in target_sets:
        for _ in range(drills_per_set):
            drill_record = evaluate_calibration_drill(
                generator=generator,
                target_bigrams=target_set,
                drill_number=drill_counter,
                config=config,
                known_words=known_words,
                max_attempts=max_attempts,
                min_density=min_density,
                max_density=max_density,
                assignment_seed=assignment_seed,
                participant_id=participant_id,
            )
            drill_records.append(drill_record)
            drill_counter += 1

    total_drills = len(drill_records)
    accepted_records = [d for d in drill_records if d.accepted]
    accepted_drills = len(accepted_records)
    acceptance_rate = accepted_drills / total_drills if total_drills > 0 else 0.0

    first_attempt_accepted = sum(1 for d in accepted_records if d.attempts_used == 1)
    first_attempt_acceptance_rate = (
        first_attempt_accepted / total_drills if total_drills > 0 else 0.0
    )

    total_attempts_for_accepted = sum(d.attempts_used for d in accepted_records)
    attempts_per_accepted_drill = (
        total_attempts_for_accepted / accepted_drills if accepted_drills > 0 else float("inf")
    )

    accepted_densities = [
        d.final_attempt.result.metrics.target_density for d in accepted_records
    ]
    if accepted_densities:
        mean_density = sum(accepted_densities) / len(accepted_densities)
        var_density = sum((x - mean_density) ** 2 for x in accepted_densities) / len(
            accepted_densities
        )
        density_std = math.sqrt(var_density)
    else:
        mean_density = 0.0
        density_std = 0.0

    meets_acceptance_threshold = acceptance_rate >= ACCEPTANCE_THRESHOLD

    return ArmCalibrationSummary(
        arm=generator.arm,
        total_drills=total_drills,
        accepted_drills=accepted_drills,
        acceptance_rate=acceptance_rate,
        first_attempt_accepted=first_attempt_accepted,
        first_attempt_acceptance_rate=first_attempt_acceptance_rate,
        attempts_per_accepted_drill=attempts_per_accepted_drill,
        mean_density=mean_density,
        density_std=density_std,
        meets_acceptance_threshold=meets_acceptance_threshold,
        drills=tuple(drill_records),
    )
