"""Control and heuristic generators: 50 seeds each pass the validator; deterministic by seed; the
heuristic stays inside the density range; clean charset and the 2-use cap (T2.4). The corpus is
built once per module (build_corpus, offline, ~0.2 s)."""

import random

import pytest

from typist.corpus.build import build_corpus
from typist.corpus.word_index import WordIndex
from typist.generation.base import Arm, DrillGenerator, DrillSpec
from typist.generation.control import ControlGenerator
from typist.generation.heuristic import HeuristicGenerator
from typist.generation.validator import ValidatorConfig, validate

_POOL_SIZE = 5000
_SEEDS = range(50)

# Migration-0006 validator defaults (the real gate the acceptance runs against).
_DEFAULT_CONFIG = ValidatorConfig(
    min_length_chars=270,
    min_coverage=3,
    max_word_repeats=3,
    max_bigram_run=3,
    min_real_word_ratio=0.8,
)


@pytest.fixture(scope="module")
def index(tmp_path_factory: pytest.TempPathFactory) -> WordIndex:
    corpus_dir = tmp_path_factory.mktemp("corpus")
    build_corpus(corpus_dir, word_count=20000, tracked_count=150)
    return WordIndex.load(corpus_dir)


@pytest.fixture(scope="module")
def control(index: WordIndex) -> ControlGenerator:
    return ControlGenerator(index, _DEFAULT_CONFIG, _POOL_SIZE)


@pytest.fixture(scope="module")
def heuristic(index: WordIndex) -> HeuristicGenerator:
    return HeuristicGenerator(index, _DEFAULT_CONFIG, _POOL_SIZE)


def _control_spec(seed: int) -> DrillSpec:
    return DrillSpec(participant_id="p1", arm=Arm.CONTROL, target_bigrams=(), seed=seed)


def _heuristic_spec(targets: tuple[str, ...], seed: int) -> DrillSpec:
    return DrillSpec(
        participant_id="p1", arm=Arm.HEURISTIC, target_bigrams=targets, seed=seed
    )


def _common(index: WordIndex) -> tuple[str, ...]:
    return tuple(index.tracked_bigrams[:4])


def _rare(index: WordIndex) -> tuple[str, ...]:
    return tuple(index.tracked_bigrams[-4:])


def _three(index: WordIndex) -> tuple[str, ...]:
    return tuple(index.tracked_bigrams[:3])


def test_generators_satisfy_the_protocol(
    control: ControlGenerator, heuristic: HeuristicGenerator
) -> None:
    assert isinstance(control, DrillGenerator)
    assert isinstance(heuristic, DrillGenerator)
    assert control.arm is Arm.CONTROL
    assert heuristic.arm is Arm.HEURISTIC
    assert control.version == "control-v1"
    assert heuristic.version == "heuristic-v1"


def test_control_fifty_seeds_each_pass_the_validator(
    index: WordIndex, control: ControlGenerator
) -> None:
    for seed in _SEEDS:
        spec = _control_spec(seed)
        candidate = control.generate(spec)
        result = validate(candidate.text, spec, _DEFAULT_CONFIG, frozenset(index.words))
        assert result.accepted, (seed, result.reasons)


@pytest.mark.parametrize("which", ["common", "rare", "three"])
def test_heuristic_fifty_seeds_each_pass_the_validator(
    index: WordIndex, heuristic: HeuristicGenerator, which: str
) -> None:
    targets = {"common": _common, "rare": _rare, "three": _three}[which](index)
    for seed in _SEEDS:
        spec = _heuristic_spec(targets, seed)
        candidate = heuristic.generate(spec)
        result = validate(candidate.text, spec, _DEFAULT_CONFIG, frozenset(index.words))
        assert result.accepted, (which, targets, seed, result.reasons)


@pytest.mark.parametrize("which", ["common", "rare", "three"])
def test_heuristic_density_is_explicitly_within_bounds(
    index: WordIndex, heuristic: HeuristicGenerator, which: str
) -> None:
    targets = {"common": _common, "rare": _rare, "three": _three}[which](index)
    for seed in _SEEDS:
        spec = _heuristic_spec(targets, seed)
        candidate = heuristic.generate(spec)
        result = validate(candidate.text, spec, _DEFAULT_CONFIG, frozenset(index.words))
        assert spec.min_density <= result.metrics.target_density <= spec.max_density, (
            which,
            seed,
            result.metrics.target_density,
        )


@pytest.mark.parametrize("which", ["common", "rare", "three"])
def test_heuristic_covers_every_target_at_least_three_times(
    index: WordIndex, heuristic: HeuristicGenerator, which: str
) -> None:
    targets = {"common": _common, "rare": _rare, "three": _three}[which](index)
    for seed in _SEEDS:
        spec = _heuristic_spec(targets, seed)
        candidate = heuristic.generate(spec)
        result = validate(candidate.text, spec, _DEFAULT_CONFIG, frozenset(index.words))
        assert all(count >= 3 for count in result.metrics.coverage.values()), (
            which,
            seed,
            result.metrics.coverage,
        )


def test_control_is_deterministic_by_seed(control: ControlGenerator) -> None:
    first = control.generate(_control_spec(7))
    second = control.generate(_control_spec(7))
    other = control.generate(_control_spec(8))
    assert first.text == second.text
    assert first.text != other.text


def test_heuristic_is_deterministic_by_seed(
    index: WordIndex, heuristic: HeuristicGenerator
) -> None:
    targets = _common(index)
    first = heuristic.generate(_heuristic_spec(targets, 7))
    second = heuristic.generate(_heuristic_spec(targets, 7))
    other = heuristic.generate(_heuristic_spec(targets, 8))
    assert first.text == second.text
    assert first.text != other.text


def test_candidate_fields_are_set_for_non_llm_arms(
    index: WordIndex, control: ControlGenerator, heuristic: HeuristicGenerator
) -> None:
    control_candidate = control.generate(_control_spec(3))
    heuristic_candidate = heuristic.generate(_heuristic_spec(_common(index), 3))
    for candidate, version, seed in (
        (control_candidate, "control-v1", 3),
        (heuristic_candidate, "heuristic-v1", 3),
    ):
        assert candidate.text == candidate.raw_output
        assert candidate.generator_version == version
        assert candidate.seed == seed
        assert candidate.model_id is None
        assert candidate.prompt_version is None
        assert candidate.gen_ms is None


@pytest.mark.parametrize("which", ["common", "rare", "three"])
def test_text_charset_and_spacing(
    index: WordIndex, control: ControlGenerator, heuristic: HeuristicGenerator, which: str
) -> None:
    targets = {"common": _common, "rare": _rare, "three": _three}[which](index)
    texts = [control.generate(_control_spec(seed)).text for seed in range(3)]
    texts += [heuristic.generate(_heuristic_spec(targets, seed)).text for seed in range(3)]
    for text in texts:
        assert text != ""
        assert text == text.strip()
        assert "  " not in text
        assert all(char == " " or "a" <= char <= "z" for char in text)


@pytest.mark.parametrize("which", ["common", "rare", "three"])
def test_no_word_is_used_more_than_twice(
    index: WordIndex, control: ControlGenerator, heuristic: HeuristicGenerator, which: str
) -> None:
    from collections import Counter

    targets = {"common": _common, "rare": _rare, "three": _three}[which](index)
    texts = [control.generate(_control_spec(seed)).text for seed in range(3)]
    texts += [heuristic.generate(_heuristic_spec(targets, seed)).text for seed in range(3)]
    for text in texts:
        assert all(count <= 2 for count in Counter(text.split(" ")).values())
