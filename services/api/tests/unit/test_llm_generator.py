"""Unit tests for LLMGenerator, DrillCandidate fields, and validator integration (T3.2)."""

import pytest

from typist.corpus.build import build_corpus
from typist.corpus.word_index import WordIndex
from typist.generation.base import Arm, DrillGenerator, DrillSpec
from typist.generation.llm import FakeLLMRuntime, LLMGenerator, LLMOutput
from typist.generation.validator import RejectReason, ValidatorConfig, validate


@pytest.fixture(scope="module")
def index(tmp_path_factory: pytest.TempPathFactory) -> WordIndex:
    corpus_dir = tmp_path_factory.mktemp("corpus_llm")
    build_corpus(corpus_dir, word_count=20000, tracked_count=150)
    return WordIndex.load(corpus_dir)


@pytest.fixture
def validator_config() -> ValidatorConfig:
    return ValidatorConfig(
        min_length_chars=270,
        min_coverage=3,
        max_word_repeats=3,
        max_bigram_run=3,
        min_real_word_ratio=0.8,
    )


def test_llm_generator_implements_protocol(index: WordIndex, validator_config: ValidatorConfig) -> None:
    generator = LLMGenerator(index, validator_config, FakeLLMRuntime())
    assert isinstance(generator, DrillGenerator)
    assert generator.arm is Arm.LLM
    assert generator.version == "llm-v1"


def test_llm_generator_populates_candidate_fields(
    index: WordIndex, validator_config: ValidatorConfig
) -> None:
    canned_output = LLMOutput(
        text="the weather in the east is great this morning and everyone is staying there",
        tokens=15,
        tokens_per_sec=42.5,
        peak_memory_mb=820.0,
        gen_ms=35.2,
    )
    fake_runtime = FakeLLMRuntime(canned_outputs=[canned_output])
    generator = LLMGenerator(index, validator_config, fake_runtime)

    spec = DrillSpec(
        participant_id="p1",
        arm=Arm.LLM,
        target_bigrams=("th", "ea", "in", "st"),
        seed=12345,
    )
    candidate = generator.generate(spec)

    assert candidate.text == canned_output.text
    assert candidate.raw_output == canned_output.text
    assert candidate.generator_version == "llm-v1"
    assert candidate.seed == 12345
    assert candidate.model_id == "mlx-community/Llama-3.2-1B-Instruct-4bit"
    assert candidate.prompt_version == "v1"
    assert candidate.gen_ms == 35.2
    assert candidate.gen_tokens == 15
    assert candidate.tokens_per_sec == 42.5
    assert candidate.peak_memory_mb == 820.0


def test_valid_llm_candidate_passes_validator(
    index: WordIndex, validator_config: ValidatorConfig
) -> None:
    # Build text between 270 and 300 chars with coverage >= 3 for ("th", "ea", "in", "st"),
    # real words, repeating words <= 3 times each, bigram run <= 3
    words = [
        "the", "weather", "in", "east", "is", "great", "this", "morning",
        "everyone", "staying", "there", "their", "seats", "eating",
        "steak", "instead", "thinking", "about", "next", "step",
        "early", "spring", "season", "with", "fresh", "air", "blowing",
        "past", "station", "where", "trains", "start", "each", "day", "clean",
        "water", "path", "stone", "stream", "reach", "into", "deep", "earth",
        "under", "warm", "sunlight",
    ]
    text = " ".join(words)
    assert 270 <= len(text) <= 300

    fake_runtime = FakeLLMRuntime(canned_text=text)
    generator = LLMGenerator(index, validator_config, fake_runtime)

    spec = DrillSpec(
        participant_id="p1",
        arm=Arm.LLM,
        target_bigrams=("th", "ea", "in", "st"),
        seed=99,
        min_density=0.10,
        max_density=0.50,
    )
    candidate = generator.generate(spec)
    result = validate(candidate.text, spec, validator_config, index.words)
    assert result.accepted is True
    assert result.reasons == ()
    assert result.metrics.real_word_ratio >= 0.8


def test_invalid_real_word_ratio_trips_validator_gate(
    index: WordIndex, validator_config: ValidatorConfig
) -> None:
    # Pseudo-words containing targets that are not in index.words
    pseudowords = ["thxpseudoword", "eaxpseudoword", "inxpseudoword", "stxpseudoword"] * 8
    text = " ".join(pseudowords)
    assert len(text) >= 270

    fake_runtime = FakeLLMRuntime(canned_text=text)
    generator = LLMGenerator(index, validator_config, fake_runtime)

    spec = DrillSpec(
        participant_id="p1",
        arm=Arm.LLM,
        target_bigrams=("th", "ea", "in", "st"),
        seed=99,
    )
    candidate = generator.generate(spec)
    result = validate(candidate.text, spec, validator_config, index.words)
    assert result.accepted is False
    assert RejectReason.REAL_WORD_RATIO in result.reasons
