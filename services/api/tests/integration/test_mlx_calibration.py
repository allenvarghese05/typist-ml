"""Live model calibration test on Apple Silicon (CLAUDE.md, T3.4; design doc §16).

Marked with @pytest.mark.mlx and skips automatically off Apple Silicon or when the model
snapshot is not cached locally.
"""

import pytest

from typist.corpus.build import build_corpus
from typist.corpus.word_index import WordIndex
from typist.generation.calibration import (
    ACCEPTANCE_THRESHOLD,
    CALIBRATION_TARGET_SETS,
    run_arm_calibration,
)
from typist.generation.llm.generator import LLMGenerator
from typist.generation.llm.runtime import (
    DEFAULT_MODEL_ID,
    DEFAULT_MODEL_REVISION,
    MLXRuntime,
    is_apple_silicon,
    is_model_cached,
)
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
    corpus_dir = tmp_path_factory.mktemp("corpus_mlx_calib")
    build_corpus(corpus_dir, word_count=20000, tracked_count=150)
    return WordIndex.load(corpus_dir)


@pytest.mark.mlx
def test_llm_arm_live_calibration_on_apple_silicon(index: WordIndex) -> None:
    """Live LLM generator on Apple Silicon verifies live acceptance on sample calibration sets."""
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
