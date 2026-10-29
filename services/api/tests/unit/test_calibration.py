"""Unit tests for density calibration and targeted arm acceptance (T3.4; design doc §16).

Verifies that:
1. CALIBRATION_TARGET_SETS are drawn strictly from index.tracked_bigrams.
2. DrillSpec defaults are min_density=0.10, max_density=0.40.
3. Arm.HEURISTIC accepts >= 80% of drills within 5 attempts across the calibration suite.
4. Arm.MARKOV accepts >= 80% of drills within 5 attempts across the calibration suite.
5. Arm.LLM reference bake-off summary achieves >= 80% acceptance under the calibrated bounds.
6. Arm.LLM with FakeLLMRuntime integrates cleanly with run_arm_calibration.
7. Arm.LLM live model generation (marked @pytest.mark.mlx) clears >= 80% when executed on Apple Silicon.
"""

import pytest

from typist.corpus.build import build_corpus
from typist.corpus.word_index import WordIndex
from typist.generation.base import Arm, DrillSpec
from typist.generation.calibration import (
    ACCEPTANCE_THRESHOLD,
    CALIBRATED_D_MAX,
    CALIBRATED_D_MIN,
    CALIBRATION_TARGET_SETS,
    run_arm_calibration,
)
from typist.generation.heuristic import HeuristicGenerator
from typist.generation.llm.bakeoff import REFERENCE_LLAMA_SUMMARY
from typist.generation.llm.generator import LLMGenerator
from typist.generation.llm.runtime import FakeLLMRuntime
from typist.generation.markov import MarkovGenerator
from typist.generation.validator import ValidatorConfig

_DEFAULT_CONFIG = ValidatorConfig(
    min_length_chars=270,
    min_coverage=3,
    max_word_repeats=3,
    max_bigram_run=3,
    min_real_word_ratio=0.8,
)


@pytest.fixture(scope="module")
def index(tmp_path_factory: pytest.TempPathFactory) -> WordIndex:
    corpus_dir = tmp_path_factory.mktemp("corpus_calib")
    build_corpus(corpus_dir, word_count=20000, tracked_count=150)
    return WordIndex.load(corpus_dir)


def test_calibration_target_sets_structure_and_tracking(index: WordIndex) -> None:
    """CALIBRATION_TARGET_SETS has 10 sets drawn strictly from index.tracked_bigrams."""
    assert len(CALIBRATION_TARGET_SETS) == 10
    tracked_set = frozenset(index.tracked_bigrams)

    # First 6 are 4-target sets
    for i in range(6):
        target_set = CALIBRATION_TARGET_SETS[i]
        assert len(target_set) == 4, f"Set {i} should have 4 targets"
        for bg in target_set:
            assert bg in tracked_set, f"Bigram {bg} in set {i} is not tracked"

    # Last 4 are 3-target fallback sets
    for i in range(6, 10):
        target_set = CALIBRATION_TARGET_SETS[i]
        assert len(target_set) == 3, f"Set {i} should have 3 targets"
        for bg in target_set:
            assert bg in tracked_set, f"Bigram {bg} in set {i} is not tracked"


def test_drill_spec_default_density_bounds() -> None:
    """DrillSpec defaults to min_density=0.10 and max_density=0.40."""
    spec = DrillSpec(participant_id="p1", arm=Arm.HEURISTIC, target_bigrams=("th", "he"))
    assert spec.min_density == CALIBRATED_D_MIN
    assert spec.max_density == CALIBRATED_D_MAX
    assert spec.min_density == 0.10
    assert spec.max_density == 0.40


def test_heuristic_arm_meets_acceptance_criterion(index: WordIndex) -> None:
    """HeuristicGenerator accepts >= 80% of drills within 5 attempts."""
    heuristic = HeuristicGenerator(index, _DEFAULT_CONFIG, pool_size=5000)
    summary = run_arm_calibration(
        generator=heuristic,
        target_sets=CALIBRATION_TARGET_SETS,
        config=_DEFAULT_CONFIG,
        known_words=frozenset(index.words),
        drills_per_set=5,
        max_attempts=5,
    )
    assert summary.meets_acceptance_threshold is True
    assert summary.acceptance_rate >= ACCEPTANCE_THRESHOLD
    assert summary.acceptance_rate >= 0.80
    assert CALIBRATED_D_MIN <= summary.mean_density <= CALIBRATED_D_MAX


def test_markov_arm_meets_acceptance_criterion(index: WordIndex) -> None:
    """MarkovGenerator (beta=10.0) accepts >= 80% of drills within 5 attempts."""
    markov = MarkovGenerator(index, _DEFAULT_CONFIG, beta=10.0)
    summary = run_arm_calibration(
        generator=markov,
        target_sets=CALIBRATION_TARGET_SETS,
        config=_DEFAULT_CONFIG,
        known_words=frozenset(index.words),
        drills_per_set=5,
        max_attempts=5,
    )
    assert summary.meets_acceptance_threshold is True
    assert summary.acceptance_rate >= ACCEPTANCE_THRESHOLD
    assert summary.acceptance_rate >= 0.80
    assert CALIBRATED_D_MIN <= summary.mean_density <= CALIBRATED_D_MAX


def test_llm_arm_meets_acceptance_criterion_reference() -> None:
    """Arm.LLM satisfies the >= 80% acceptance criterion via benchmark summary (T3.4 owner answer 5)."""
    assert REFERENCE_LLAMA_SUMMARY.acceptance_rate >= ACCEPTANCE_THRESHOLD
    assert REFERENCE_LLAMA_SUMMARY.acceptance_rate == 0.845
    # The reference summary was evaluated under [0.15, 0.40].
    # Under [0.10, 0.40], acceptance is monotonically non-decreasing because
    # [0.15, 0.40] is a strict subset of [0.10, 0.40] and 0 drills exceeded 0.40.
    assert REFERENCE_LLAMA_SUMMARY.mean_density is not None
    assert CALIBRATED_D_MIN <= REFERENCE_LLAMA_SUMMARY.mean_density <= CALIBRATED_D_MAX


def test_llm_arm_with_fake_runtime(index: WordIndex) -> None:
    """LLMGenerator integrates cleanly with run_arm_calibration using FakeLLMRuntime."""
    # Canonical 278-char valid text (targets th, ea, in, st; density ~0.235, words repeat <= 2)
    canned_text = (
        "the weather in east is great this morning everyone staying there their "
        "seats eating steak instead thinking about next step early spring season "
        "with fresh air blowing past station where trains start each day clean "
        "water path stone stream reach into deep earth under warm sunlight"
    )
    runtime = FakeLLMRuntime(canned_text=canned_text)
    llm = LLMGenerator(index, _DEFAULT_CONFIG, runtime=runtime)

    # Run on a mini calibration set matching the canned text's targets
    mini_sets = (("th", "ea", "in", "st"),)
    summary = run_arm_calibration(
        generator=llm,
        target_sets=mini_sets,
        config=_DEFAULT_CONFIG,
        known_words=frozenset(index.words),
        drills_per_set=2,
        max_attempts=1,
    )
    assert summary.total_drills == 2
    assert summary.accepted_drills == 2
    assert summary.acceptance_rate == 1.0
    assert CALIBRATED_D_MIN <= summary.mean_density <= CALIBRATED_D_MAX


@pytest.mark.mlx
def test_llm_arm_live_calibration_on_apple_silicon(index: WordIndex) -> None:
    """Live LLM generator on Apple Silicon verifies live acceptance on sample calibration sets."""
    from typist.generation.llm.runtime import (
        DEFAULT_MODEL_ID,
        DEFAULT_MODEL_REVISION,
        MLXRuntime,
        is_apple_silicon,
        is_model_cached,
    )

    if not is_apple_silicon() or not is_model_cached(DEFAULT_MODEL_ID, DEFAULT_MODEL_REVISION):
        pytest.skip("MLX model weights not cached locally")

    runtime = MLXRuntime()
    llm = LLMGenerator(index, _DEFAULT_CONFIG, runtime=runtime)
    # Evaluate 2 drills each on 2 calibration sets
    sample_sets = (CALIBRATION_TARGET_SETS[0], CALIBRATION_TARGET_SETS[6])
    summary = run_arm_calibration(
        generator=llm,
        target_sets=sample_sets,
        config=_DEFAULT_CONFIG,
        known_words=frozenset(index.words),
        drills_per_set=2,
        max_attempts=5,
    )
    assert summary.acceptance_rate >= ACCEPTANCE_THRESHOLD
