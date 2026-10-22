"""Shared generation contracts: the arm enum, the drill request/response dataclasses and the
generator protocol every arm implements (design doc 7, 9.1; D03, D09, D10).

Pure type definitions only: no database, no file and no mlx-lm import, so this module imports on
Linux CI (CLAUDE.md: mlx-lm is Apple-Silicon-only; LLM-specific code lives in generation/llm/).
DrillSpec is the request the GenerationService builds per participant/arm (its target_bigrams come
from the frozen bigram_assignment rows, T2.2; empty for control). DrillCandidate is what a
generator returns before validation -- it carries the text and the reproducibility/timing fields
that map onto the drills/generation_attempts columns (section 8.1), but NO fairness metrics: the
`validate` function computes those, so a candidate can never report stale or self-measured numbers
(owner answer 1). DrillGenerator is the one protocol control/heuristic/markov/llm all satisfy
(9.1 "Every generator implements the same DrillGenerator protocol").
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class Arm(StrEnum):
    """The four generated arms (D03); mirrors models.drills.DRILL_ARMS. CONTROL has no targets."""

    CONTROL = "control"
    HEURISTIC = "heuristic"
    MARKOV = "markov"
    LLM = "llm"


@dataclass(frozen=True)
class DrillSpec:
    """One drill request (design doc 9.1). target_bigrams is empty for CONTROL; min_density and
    max_density are the d_min/d_max range the validator enforces for targeted arms; length_chars is
    the target length the generator aims for (the validator's floor is a separate config key). seed
    makes generation reproducible (determinism, 13.1)."""

    participant_id: str
    arm: Arm
    target_bigrams: tuple[str, ...]  # empty for CONTROL
    length_chars: int = 300
    min_density: float = 0.15
    max_density: float = 0.40
    seed: int = 0


@dataclass(frozen=True)
class DrillCandidate:
    """A generator's output before validation (owner answer 1). text is the cleaned a-z+space drill
    the generator hands to the validator; raw_output equals text for non-LLM arms and is the
    model's pre-clean output for the LLM arm. generator_version and seed are the reproducibility
    fields; model_id/prompt_version are LLM-only (None otherwise); gen_ms/gen_tokens/
    tokens_per_sec/peak_memory_mb are the LLM timing/memory metrics (None for non-LLM arms). Carries
    NO fairness metrics -- the validator computes those."""

    text: str
    raw_output: str
    generator_version: str
    seed: int
    model_id: str | None = None
    prompt_version: str | None = None
    gen_ms: float | None = None
    gen_tokens: int | None = None
    tokens_per_sec: float | None = None
    peak_memory_mb: float | None = None


@runtime_checkable
class DrillGenerator(Protocol):
    """The contract every arm implements (design doc 9.1). arm identifies the arm; version is the
    generator_version stamped onto drills/attempts; generate turns a spec into one candidate."""

    arm: Arm
    version: str

    def generate(self, spec: DrillSpec) -> DrillCandidate: ...
