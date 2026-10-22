"""Validator unit tests: one failing case per RejectReason, an accepted drill, control, multi-reason
collection, determinism, empty text, the run examples and the density boundaries (T2.3). Every
metric is hand-computed and verified against count_bigrams."""

import pytest

from typist.generation.base import Arm, DrillSpec
from typist.generation.validator import (
    RejectReason,
    ValidatorConfig,
    validate,
)

# Migration-0006 defaults; tests override only what they must (mostly the length floor).
_DEFAULT_CONFIG = ValidatorConfig(
    min_length_chars=270,
    min_coverage=3,
    max_word_repeats=3,
    max_bigram_run=3,
    min_real_word_ratio=0.8,
)


def _config(**overrides: object) -> ValidatorConfig:
    values = {
        "min_length_chars": _DEFAULT_CONFIG.min_length_chars,
        "min_coverage": _DEFAULT_CONFIG.min_coverage,
        "max_word_repeats": _DEFAULT_CONFIG.max_word_repeats,
        "max_bigram_run": _DEFAULT_CONFIG.max_bigram_run,
        "min_real_word_ratio": _DEFAULT_CONFIG.min_real_word_ratio,
    }
    values.update(overrides)
    return ValidatorConfig(**values)  # type: ignore[arg-type]


def _spec(arm: Arm, targets: tuple[str, ...], *, min_density: float = 0.15,
          max_density: float = 0.40) -> DrillSpec:
    return DrillSpec(
        participant_id="p1",
        arm=arm,
        target_bigrams=targets,
        min_density=min_density,
        max_density=max_density,
        seed=7,
    )


def test_too_short() -> None:
    spec = _spec(Arm.CONTROL, ())
    result = validate("hello world", spec, _config(), frozenset({"hello", "world"}))
    assert result.reasons == (RejectReason.TOO_SHORT,)
    assert result.metrics.length_chars == 11
    assert result.accepted is False


@pytest.mark.parametrize(
    "text",
    ["hello wor1d", "hello, world", " hello", "hello ", "hello  world"],
)
def test_bad_charset(text: str) -> None:
    spec = _spec(Arm.CONTROL, ())
    result = validate(text, spec, _config(min_length_chars=1), frozenset())
    assert result.reasons == (RejectReason.BAD_CHARSET,)


def test_density_low() -> None:
    # "math"x3 (th:3) + a 22-letter non-th filler: th=3 over total=30 -> 0.10 < 0.15; coverage ok.
    text = "math math math abcdefghijklmnopqrstuv"
    spec = _spec(Arm.HEURISTIC, ("th",))
    result = validate(text, spec, _config(min_length_chars=1), frozenset())
    assert result.reasons == (RejectReason.DENSITY_LOW,)
    assert result.metrics.target_density == pytest.approx(0.10)
    assert result.metrics.coverage == {"th": 3}


def test_density_high() -> None:
    # 9 distinct th-words (th:9) + "abc": th=9 over total=20 -> 0.45 > 0.40; coverage ok.
    text = "tha thb thc thd the thf thg thh thi abc"
    spec = _spec(Arm.HEURISTIC, ("th",))
    result = validate(text, spec, _config(min_length_chars=1), frozenset())
    assert result.reasons == (RejectReason.DENSITY_HIGH,)
    assert result.metrics.target_density == pytest.approx(0.45)


def test_coverage() -> None:
    # ck=5, ow=2 (ow < 3) -> coverage; density 7/35 = 0.20 is in range so no density reason.
    text = "cka ckb ckc ckd cke owa owb abdefghijklmnpqrstuvwx"
    spec = _spec(Arm.HEURISTIC, ("ck", "ow"))
    result = validate(text, spec, _config(min_length_chars=1), frozenset())
    assert result.reasons == (RejectReason.COVERAGE,)
    assert result.metrics.coverage == {"ck": 5, "ow": 2}
    assert result.metrics.target_density == pytest.approx(0.20)


def test_word_repeat() -> None:
    # "the" 4 times (> 3) on a control spec (density/coverage skipped).
    spec = _spec(Arm.CONTROL, ())
    result = validate("the the the the", spec, _config(min_length_chars=1), frozenset({"the"}))
    assert result.reasons == (RejectReason.WORD_REPEAT,)
    assert result.metrics.max_word_count == 4


def test_bigram_repeat() -> None:
    # "ththth": th at positions 0,2,4 -> run 3 (owner answer 7) -> reject.
    spec = _spec(Arm.CONTROL, ())
    result = validate("ththth", spec, _config(min_length_chars=1), frozenset())
    assert result.reasons == (RejectReason.BIGRAM_REPEAT,)
    assert result.metrics.bigram_run == 3


def test_real_word_ratio() -> None:
    # LLM gate: 1 of 3 tokens is a known word -> ratio 0.333 < 0.8. Targetless spec skips density.
    spec = _spec(Arm.LLM, ())
    result = validate("qwrt vbnm hello", spec, _config(min_length_chars=1), frozenset({"hello"}))
    assert result.reasons == (RejectReason.REAL_WORD_RATIO,)
    assert result.metrics.real_word_ratio == pytest.approx(1 / 3)


def test_real_word_ratio_recorded_but_not_gated_for_markov() -> None:
    # Same low ratio on a targetless markov spec: recorded, never a reason (only LLM is gated).
    spec = _spec(Arm.MARKOV, ())
    result = validate("qwrt vbnm hello", spec, _config(min_length_chars=1), frozenset({"hello"}))
    assert result.reasons == ()
    assert result.metrics.real_word_ratio == pytest.approx(1 / 3)


def test_accepted_drill() -> None:
    # "math"x3 + "abcdefghijkl": th=3 over 20 = 0.15 (== d_min) with widened spec; all rules pass.
    text = "math math math abcdefghijkl"
    spec = _spec(Arm.HEURISTIC, ("th",), min_density=0.10, max_density=0.50)
    result = validate(text, spec, _config(min_length_chars=1), frozenset({"math"}))
    assert result.accepted is True
    assert result.reasons == ()
    assert result.metrics.target_density == pytest.approx(0.15)
    assert result.metrics.mean_word_len == pytest.approx(6.0)
    assert result.metrics.real_word_ratio == pytest.approx(0.75)


def test_control_passes_with_empty_targets() -> None:
    spec = _spec(Arm.CONTROL, ())
    result = validate(
        "hello world foo bar", spec, _config(min_length_chars=5), frozenset({"hello", "world", "foo", "bar"})
    )
    assert result.accepted is True
    assert result.reasons == ()
    assert result.metrics.target_density == 0.0
    assert result.metrics.coverage == {}


def test_control_rejected_for_word_repeat() -> None:
    spec = _spec(Arm.CONTROL, ())
    result = validate("the the the the", spec, _config(min_length_chars=1), frozenset({"the"}))
    assert result.reasons == (RejectReason.WORD_REPEAT,)


def test_multiple_reasons_are_all_collected() -> None:
    # "aa"x4: word_repeat (4>3); th=0 over total=4 -> density_low; th coverage 0 -> coverage.
    spec = _spec(Arm.HEURISTIC, ("th",))
    result = validate("aa aa aa aa", spec, _config(min_length_chars=1), frozenset())
    assert result.reasons == (
        RejectReason.DENSITY_LOW,
        RejectReason.COVERAGE,
        RejectReason.WORD_REPEAT,
    )


def test_determinism_same_inputs_give_equal_results() -> None:
    spec = _spec(Arm.HEURISTIC, ("th",), min_density=0.10, max_density=0.50)
    args = ("math math math abcdefghijkl", spec, _config(min_length_chars=1), frozenset({"math"}))
    first = validate(*args)
    second = validate(*args)
    assert first == second


def test_empty_text_is_too_short_and_bad_charset() -> None:
    spec = _spec(Arm.CONTROL, ())
    result = validate("", spec, _config(), frozenset())
    assert result.reasons == (RejectReason.TOO_SHORT, RejectReason.BAD_CHARSET)
    assert result.metrics.target_density == 0.0
    assert result.metrics.bigram_run == 0


def test_whitespace_only_text_is_too_short_and_bad_charset() -> None:
    spec = _spec(Arm.CONTROL, ())
    result = validate("   ", spec, _config(), frozenset())
    assert result.reasons == (RejectReason.TOO_SHORT, RejectReason.BAD_CHARSET)


def test_bigram_run_examples() -> None:
    spec = _spec(Arm.CONTROL, ())
    config = _config(min_length_chars=1)
    run2 = validate("thth", spec, config, frozenset())
    assert run2.metrics.bigram_run == 2
    assert RejectReason.BIGRAM_REPEAT not in run2.reasons
    run3 = validate("ththth", spec, config, frozenset())
    assert run3.metrics.bigram_run == 3
    assert RejectReason.BIGRAM_REPEAT in run3.reasons
    across = validate("th th th", spec, config, frozenset())
    assert across.metrics.bigram_run == 1
    assert RejectReason.BIGRAM_REPEAT not in across.reasons


def test_density_boundaries_are_inclusive() -> None:
    # Exactly d_min (0.15) accepted and exactly d_max (0.40) accepted.
    at_min = validate(
        "math math math abcdefghijkl",
        _spec(Arm.HEURISTIC, ("th",), min_density=0.15, max_density=0.40),
        _config(min_length_chars=1),
        frozenset({"math"}),
    )
    assert at_min.metrics.target_density == pytest.approx(0.15)
    assert RejectReason.DENSITY_LOW not in at_min.reasons
    at_max = validate(
        "tha thb thc thd the thf thg thh abcde",
        _spec(Arm.HEURISTIC, ("th",), min_density=0.15, max_density=0.40),
        _config(min_length_chars=1),
        frozenset(),
    )
    assert at_max.metrics.target_density == pytest.approx(0.40)
    assert RejectReason.DENSITY_HIGH not in at_max.reasons
