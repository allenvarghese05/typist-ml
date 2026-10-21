"""session_stats pure functions: WPM/accuracy NULL rules, block elapsed, and sample pooling (T1.9)."""

from statistics import median

from typist.models import KeystrokeEvent
from typist.services.attribution import BigramSamples
from typist.services.session_stats import (
    BlockMetrics,
    block_elapsed_ms,
    merge_bigram_samples,
    session_metrics,
)


def _row(seq: int, t_down_ms: float) -> KeystrokeEvent:
    return KeystrokeEvent(
        block_id="b",
        seq=seq,
        key="a",
        code="KeyA",
        t_down_ms=t_down_ms,
        target_index=seq,
        expected_char="a",
        outcome="correct",
        first_attempt=True,
        handler_ms=0.0,
        dispatch_lag_ms=0.0,
    )


def test_block_elapsed_is_last_press_minus_first_press_by_seq() -> None:
    rows = [_row(2, 31851.0), _row(0, 1851.0), _row(1, 5000.0)]
    assert block_elapsed_ms(rows) == 30000.0


def test_block_elapsed_is_zero_for_fewer_than_two_rows() -> None:
    assert block_elapsed_ms([]) == 0.0
    assert block_elapsed_ms([_row(0, 100.0)]) == 0.0


def test_wpm_and_accuracy_on_the_golden_single_block_numbers() -> None:
    metrics = session_metrics(
        [BlockMetrics(correct_first_attempts=55, first_attempts=64, elapsed_ms=30000.0)]
    )
    assert metrics.wpm == 22.0
    assert metrics.accuracy == 0.859375


def test_wpm_sums_elapsed_across_blocks() -> None:
    metrics = session_metrics(
        [
            BlockMetrics(correct_first_attempts=5, first_attempts=5, elapsed_ms=1000.0),
            BlockMetrics(correct_first_attempts=5, first_attempts=5, elapsed_ms=1000.0),
        ]
    )
    assert metrics.wpm == 60.0
    assert metrics.accuracy == 1.0


def test_accuracy_is_none_with_zero_first_attempts() -> None:
    metrics = session_metrics(
        [BlockMetrics(correct_first_attempts=0, first_attempts=0, elapsed_ms=5000.0)]
    )
    assert metrics.accuracy is None
    assert metrics.wpm is None  # zero correct too


def test_wpm_is_none_with_zero_elapsed() -> None:
    metrics = session_metrics(
        [BlockMetrics(correct_first_attempts=10, first_attempts=12, elapsed_ms=0.0)]
    )
    assert metrics.wpm is None
    assert metrics.accuracy == 10 / 12


def test_wpm_is_none_with_zero_correct_first_attempts() -> None:
    metrics = session_metrics(
        [BlockMetrics(correct_first_attempts=0, first_attempts=8, elapsed_ms=5000.0)]
    )
    assert metrics.wpm is None
    assert metrics.accuracy == 0.0


def test_merge_pools_samples_then_one_median_not_median_of_medians() -> None:
    block0 = {"ab": BigramSamples("ab", attempts=3, errors=0, iki_samples=(100.0, 200.0, 300.0))}
    block1 = {"ab": BigramSamples("ab", attempts=1, errors=0, iki_samples=(1000.0,))}
    pooled = merge_bigram_samples([block0, block1])
    assert pooled["ab"].attempts == 4
    assert pooled["ab"].errors == 0
    assert pooled["ab"].iki_samples == (100.0, 200.0, 300.0, 1000.0)
    assert median(pooled["ab"].iki_samples) == 250.0
    median_of_medians = (median(block0["ab"].iki_samples) + median(block1["ab"].iki_samples)) / 2
    assert median_of_medians == 600.0
    assert median(pooled["ab"].iki_samples) != median_of_medians


def test_merge_unions_bigrams_and_sums_errors() -> None:
    block0 = {"ab": BigramSamples("ab", attempts=2, errors=1, iki_samples=(100.0,))}
    block1 = {"cd": BigramSamples("cd", attempts=1, errors=1, iki_samples=())}
    pooled = merge_bigram_samples([block0, block1])
    assert set(pooled) == {"ab", "cd"}
    assert pooled["cd"].attempts == 1
    assert pooled["cd"].errors == 1
    assert pooled["cd"].iki_samples == ()
