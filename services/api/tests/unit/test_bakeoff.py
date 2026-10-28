"""Unit tests for the Arm.LLM model bake-off (design doc 13.6; D10, D29; T3.3)."""

from pathlib import Path

import pytest

from typist.corpus.build import build_corpus
from typist.corpus.word_index import WordIndex
from typist.generation.base import DrillCandidate
from typist.generation.llm.bakeoff import (
    CHALLENGER_MODEL_ID,
    CHALLENGER_MODEL_REVISION,
    REFERENCE_LLAMA_SUMMARY,
    REFERENCE_QWEN_SUMMARY,
    SYNTHETIC_TARGET_SETS,
    BakeoffAttemptRecord,
    DrillEvaluation,
    ModelBakeoffSummary,
    compute_bakeoff_summary,
    evaluate_bakeoff,
    select_bakeoff_winner,
)
from typist.generation.llm.runtime import (
    DEFAULT_MODEL_ID,
    DEFAULT_MODEL_REVISION,
    FakeLLMRuntime,
)
from typist.generation.validator import (
    DrillMetrics,
    RejectReason,
    ValidationResult,
    ValidatorConfig,
)


@pytest.fixture(scope="module")
def index(tmp_path_factory: pytest.TempPathFactory) -> WordIndex:
    corpus_dir = tmp_path_factory.mktemp("corpus_bakeoff")
    build_corpus(corpus_dir, word_count=5000, tracked_count=100)
    return WordIndex.load(corpus_dir)


@pytest.fixture
def validator_config() -> ValidatorConfig:
    return ValidatorConfig(
        min_length_chars=20,
        min_coverage=1,
        max_word_repeats=5,
        max_bigram_run=3,
        min_real_word_ratio=0.7,
    )


def test_synthetic_target_sets() -> None:
    assert len(SYNTHETIC_TARGET_SETS) == 10
    for _s_idx, target_set in enumerate(SYNTHETIC_TARGET_SETS):
        assert len(target_set) == 4
        for bigram in target_set:
            assert len(bigram) == 2
            assert bigram.isalpha() and bigram.islower()

    # Sets 1-5: common bigrams
    assert SYNTHETIC_TARGET_SETS[0] == ("th", "he", "in", "er")
    assert SYNTHETIC_TARGET_SETS[4] == ("is", "it", "al", "ar")

    # Sets 6-10: awkward bigrams
    assert SYNTHETIC_TARGET_SETS[5] == ("ck", "ow", "gh", "ph")
    assert SYNTHETIC_TARGET_SETS[9] == ("dr", "gl", "cl", "mp")


def _make_candidate(
    text: str = "sample text",
    tps: float = 40.0,
    mem: float = 800.0,
) -> DrillCandidate:
    return DrillCandidate(
        text=text,
        raw_output=text,
        generator_version="llm-v1",
        seed=1,
        tokens_per_sec=tps,
        peak_memory_mb=mem,
    )


def _make_val_result(
    accepted: bool,
    reasons: list[RejectReason] | None = None,
    density: float = 0.25,
    real_word: float = 0.95,
) -> ValidationResult:
    reasons_tuple = tuple(reasons or [])
    metrics = DrillMetrics(
        length_chars=50,
        target_density=density,
        mean_word_len=5.0,
        real_word_ratio=real_word,
        coverage={"th": 2, "he": 2},
        max_word_count=1,
        bigram_run=1,
    )
    return ValidationResult(
        accepted=accepted,
        reasons=reasons_tuple,
        metrics=metrics,
    )


def test_compute_bakeoff_summary_all_accepted() -> None:
    evaluations = [
        DrillEvaluation(
            set_index=0,
            drill_index=i,
            target_bigrams=("th", "he", "in", "er"),
            accepted=True,
            accepted_attempt=1,
            attempts=(
                BakeoffAttemptRecord(
                    attempt=1,
                    accepted=True,
                    reasons=(),
                    candidate=_make_candidate(tps=45.0, mem=850.0),
                    validation=_make_val_result(accepted=True, density=0.20 + i * 0.02),
                ),
            ),
            accepted_candidate=_make_candidate(tps=45.0, mem=850.0),
            accepted_metrics=_make_val_result(
                accepted=True, density=0.20 + i * 0.02
            ).metrics,
        )
        for i in range(5)
    ]

    summary = compute_bakeoff_summary("model-a", "rev-a", evaluations)
    assert summary.total_drills == 5
    assert summary.accepted_drills == 5
    assert summary.acceptance_rate == 1.0
    assert summary.first_attempt_accepted == 5
    assert summary.first_attempt_acceptance_rate == 1.0
    assert summary.attempts_per_accepted_drill == 1.0
    assert summary.mean_density == pytest.approx(0.24, abs=0.01)
    assert summary.density_std is not None and summary.density_std > 0
    assert summary.mean_real_word_ratio == 0.95
    assert summary.mean_tokens_per_sec == 45.0
    assert summary.peak_memory_mb == 850.0
    assert summary.meets_tps_threshold is True


def test_compute_bakeoff_summary_mixed_retries() -> None:
    # Drill 1: accepted on attempt 1
    att1 = BakeoffAttemptRecord(
        attempt=1,
        accepted=True,
        reasons=(),
        candidate=_make_candidate(tps=40.0, mem=800.0),
        validation=_make_val_result(accepted=True, density=0.22, real_word=0.92),
    )
    e1 = DrillEvaluation(
        set_index=0,
        drill_index=0,
        target_bigrams=("th", "he", "in", "er"),
        accepted=True,
        accepted_attempt=1,
        attempts=(att1,),
        accepted_candidate=att1.candidate,
        accepted_metrics=att1.validation.metrics,
    )

    # Drill 2: rejected attempts 1, 2; accepted on attempt 3
    rej1 = BakeoffAttemptRecord(
        attempt=1,
        accepted=False,
        reasons=(RejectReason.DENSITY_LOW.value,),
        candidate=_make_candidate(tps=42.0, mem=810.0),
        validation=_make_val_result(accepted=False, reasons=[RejectReason.DENSITY_LOW]),
    )
    rej2 = BakeoffAttemptRecord(
        attempt=2,
        accepted=False,
        reasons=(RejectReason.COVERAGE.value,),
        candidate=_make_candidate(tps=38.0, mem=815.0),
        validation=_make_val_result(accepted=False, reasons=[RejectReason.COVERAGE]),
    )
    pass3 = BakeoffAttemptRecord(
        attempt=3,
        accepted=True,
        reasons=(),
        candidate=_make_candidate(tps=40.0, mem=820.0),
        validation=_make_val_result(accepted=True, density=0.28, real_word=0.96),
    )
    e2 = DrillEvaluation(
        set_index=0,
        drill_index=1,
        target_bigrams=("th", "he", "in", "er"),
        accepted=True,
        accepted_attempt=3,
        attempts=(rej1, rej2, pass3),
        accepted_candidate=pass3.candidate,
        accepted_metrics=pass3.validation.metrics,
    )

    # Drill 3: rejected across all 5 attempts
    rej_attempts = tuple(
        BakeoffAttemptRecord(
            attempt=att,
            accepted=False,
            reasons=(RejectReason.REAL_WORD_RATIO.value,),
            candidate=_make_candidate(tps=39.0, mem=805.0),
            validation=_make_val_result(
                accepted=False, reasons=[RejectReason.REAL_WORD_RATIO]
            ),
        )
        for att in range(1, 6)
    )
    e3 = DrillEvaluation(
        set_index=0,
        drill_index=2,
        target_bigrams=("th", "he", "in", "er"),
        accepted=False,
        accepted_attempt=None,
        attempts=rej_attempts,
        accepted_candidate=None,
        accepted_metrics=None,
    )

    summary = compute_bakeoff_summary("model-a", "rev-a", [e1, e2, e3])
    assert summary.total_drills == 3
    assert summary.accepted_drills == 2
    assert summary.acceptance_rate == round(2 / 3, 3)
    assert summary.first_attempt_accepted == 1
    assert summary.first_attempt_acceptance_rate == round(1 / 3, 3)
    # Total accepted attempts: 1 + 3 = 4 across 2 accepted drills -> 2.0
    assert summary.attempts_per_accepted_drill == 2.0
    assert summary.mean_density == round((0.22 + 0.28) / 2, 3)
    assert summary.mean_real_word_ratio == round((0.92 + 0.96) / 2, 3)


def test_compute_bakeoff_summary_zero_accepted_edge_case() -> None:
    # 5 drills all rejected across attempts
    evaluations = [
        DrillEvaluation(
            set_index=5,
            drill_index=i,
            target_bigrams=("ck", "ow", "gh", "ph"),
            accepted=False,
            accepted_attempt=None,
            attempts=(
                BakeoffAttemptRecord(
                    attempt=1,
                    accepted=False,
                    reasons=(RejectReason.REAL_WORD_RATIO.value,),
                    candidate=_make_candidate(),
                    validation=_make_val_result(
                        accepted=False, reasons=[RejectReason.REAL_WORD_RATIO]
                    ),
                ),
            ),
            accepted_candidate=None,
            accepted_metrics=None,
        )
        for i in range(5)
    ]

    summary = compute_bakeoff_summary("model-a", "rev-a", evaluations)
    assert summary.total_drills == 5
    assert summary.accepted_drills == 0
    assert summary.acceptance_rate == 0.0
    assert summary.first_attempt_accepted == 0
    assert summary.first_attempt_acceptance_rate == 0.0
    assert summary.attempts_per_accepted_drill is None
    assert summary.mean_density is None
    assert summary.density_std is None
    assert summary.mean_real_word_ratio is None


def test_select_bakeoff_winner_rules() -> None:
    base = ModelBakeoffSummary(
        model_id=DEFAULT_MODEL_ID,
        revision=DEFAULT_MODEL_REVISION,
        total_drills=200,
        accepted_drills=160,
        acceptance_rate=0.80,
        first_attempt_accepted=120,
        first_attempt_acceptance_rate=0.60,
        attempts_per_accepted_drill=1.5,
        mean_density=0.23,
        density_std=0.04,
        mean_real_word_ratio=0.94,
        mean_tokens_per_sec=45.0,
        peak_memory_mb=850.0,
        meets_tps_threshold=True,
    )

    challenger_higher = ModelBakeoffSummary(
        model_id=CHALLENGER_MODEL_ID,
        revision=CHALLENGER_MODEL_REVISION,
        total_drills=200,
        accepted_drills=170,
        acceptance_rate=0.85,
        first_attempt_accepted=130,
        first_attempt_acceptance_rate=0.65,
        attempts_per_accepted_drill=1.4,
        mean_density=0.24,
        density_std=0.04,
        mean_real_word_ratio=0.95,
        mean_tokens_per_sec=35.0,
        peak_memory_mb=1200.0,
        meets_tps_threshold=True,
    )

    # 1. Clear challenger win
    winner, reason = select_bakeoff_winner(base, challenger_higher)
    assert winner == CHALLENGER_MODEL_ID
    assert "higher acceptance rate" in reason

    # 2. Clear default win
    challenger_lower = ModelBakeoffSummary(
        model_id=CHALLENGER_MODEL_ID,
        revision=CHALLENGER_MODEL_REVISION,
        total_drills=200,
        accepted_drills=150,
        acceptance_rate=0.75,
        first_attempt_accepted=110,
        first_attempt_acceptance_rate=0.55,
        attempts_per_accepted_drill=1.6,
        mean_density=0.22,
        density_std=0.04,
        mean_real_word_ratio=0.93,
        mean_tokens_per_sec=35.0,
        peak_memory_mb=1200.0,
        meets_tps_threshold=True,
    )
    winner, reason = select_bakeoff_winner(base, challenger_lower)
    assert winner == DEFAULT_MODEL_ID
    assert "higher acceptance rate" in reason

    # 3. Tie keeps default (Llama-3.2-1B)
    challenger_tied = ModelBakeoffSummary(
        model_id=CHALLENGER_MODEL_ID,
        revision=CHALLENGER_MODEL_REVISION,
        total_drills=200,
        accepted_drills=160,
        acceptance_rate=0.80,
        first_attempt_accepted=120,
        first_attempt_acceptance_rate=0.60,
        attempts_per_accepted_drill=1.5,
        mean_density=0.23,
        density_std=0.04,
        mean_real_word_ratio=0.94,
        mean_tokens_per_sec=35.0,
        peak_memory_mb=1200.0,
        meets_tps_threshold=True,
    )
    winner, reason = select_bakeoff_winner(base, challenger_tied)
    assert winner == DEFAULT_MODEL_ID
    assert "tied" in reason

    # 4. Challenger has higher acceptance but fails TPS threshold
    challenger_slow = ModelBakeoffSummary(
        model_id=CHALLENGER_MODEL_ID,
        revision=CHALLENGER_MODEL_REVISION,
        total_drills=200,
        accepted_drills=180,
        acceptance_rate=0.90,
        first_attempt_accepted=140,
        first_attempt_acceptance_rate=0.70,
        attempts_per_accepted_drill=1.3,
        mean_density=0.25,
        density_std=0.03,
        mean_real_word_ratio=0.96,
        mean_tokens_per_sec=24.0,
        peak_memory_mb=1200.0,
        meets_tps_threshold=False,
    )
    winner, reason = select_bakeoff_winner(base, challenger_slow)
    assert winner == DEFAULT_MODEL_ID
    assert "meets throughput threshold" in reason

    # 5. Both fail TPS threshold -> raises RuntimeError
    base_slow = ModelBakeoffSummary(
        model_id=DEFAULT_MODEL_ID,
        revision=DEFAULT_MODEL_REVISION,
        total_drills=200,
        accepted_drills=160,
        acceptance_rate=0.80,
        first_attempt_accepted=120,
        first_attempt_acceptance_rate=0.60,
        attempts_per_accepted_drill=1.5,
        mean_density=0.23,
        density_std=0.04,
        mean_real_word_ratio=0.94,
        mean_tokens_per_sec=22.0,
        peak_memory_mb=850.0,
        meets_tps_threshold=False,
    )
    with pytest.raises(RuntimeError, match="Neither candidate met"):
        select_bakeoff_winner(base_slow, challenger_slow)


def test_evaluate_bakeoff_with_fake_runtime(
    index: WordIndex, validator_config: ValidatorConfig
) -> None:
    # Canned output containing the target bigrams so it gets accepted
    canned_text = (
        "the weather in east is great today this morning everyone is there thinking about season "
        "another round of weather in the east and north with great enthusiasm"
    )
    fake_runtime = FakeLLMRuntime(
        canned_text=canned_text,
        tokens_per_sec=42.0,
        peak_memory_mb=820.0,
    )

    evals, summary = evaluate_bakeoff(
        runtime=fake_runtime,
        index=index,
        config=validator_config,
        target_sets=SYNTHETIC_TARGET_SETS[:2],
        drills_per_set=2,
        max_attempts=2,
        length_chars=80,
        min_density=0.05,
        max_density=0.50,
    )

    assert len(evals) == 4
    assert summary.total_drills == 4
    assert summary.mean_tokens_per_sec == 42.0
    assert summary.peak_memory_mb == 820.0
    assert summary.meets_tps_threshold is True
    for e in evals:
        assert len(e.attempts) >= 1


def test_adr_d29_consistency() -> None:
    adr_path = (
        Path(__file__).resolve().parents[4]
        / "docs"
        / "decisions"
        / "D29-model-bakeoff-choice.md"
    )
    assert adr_path.exists(), f"ADR file missing at {adr_path}"

    content = adr_path.read_text(encoding="utf-8")

    # Status & metadata
    assert "- Status: accepted" in content
    assert f"`{REFERENCE_LLAMA_SUMMARY.model_id}`" in content
    assert f"`{REFERENCE_LLAMA_SUMMARY.revision}`" in content
    assert f"`{REFERENCE_QWEN_SUMMARY.model_id}`" in content
    assert f"`{REFERENCE_QWEN_SUMMARY.revision}`" in content

    # Llama reference metrics
    assert f"**{REFERENCE_LLAMA_SUMMARY.acceptance_rate * 100:.1f}%**" in content
    assert f"**{REFERENCE_LLAMA_SUMMARY.first_attempt_acceptance_rate * 100:.1f}%**" in content
    assert f"**{REFERENCE_LLAMA_SUMMARY.attempts_per_accepted_drill:.2f}**" in content
    assert f"{REFERENCE_LLAMA_SUMMARY.mean_density:.3f} ± {REFERENCE_LLAMA_SUMMARY.density_std:.3f}" in content
    assert f"**{REFERENCE_LLAMA_SUMMARY.mean_tokens_per_sec:.1f} tokens/s**" in content
    assert f"**{REFERENCE_LLAMA_SUMMARY.peak_memory_mb:.1f} MB**" in content

    # Qwen reference metrics
    assert f"{REFERENCE_QWEN_SUMMARY.acceptance_rate * 100:.1f}%" in content
    assert f"{REFERENCE_QWEN_SUMMARY.first_attempt_acceptance_rate * 100:.1f}%" in content
    assert f"{REFERENCE_QWEN_SUMMARY.attempts_per_accepted_drill:.2f}" in content
    assert f"{REFERENCE_QWEN_SUMMARY.mean_density:.3f} ± {REFERENCE_QWEN_SUMMARY.density_std:.3f}" in content
    assert f"{REFERENCE_QWEN_SUMMARY.mean_tokens_per_sec:.1f} tokens/s" in content
    assert f"{REFERENCE_QWEN_SUMMARY.peak_memory_mb:.1f} MB" in content

