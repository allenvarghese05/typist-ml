"""Unit tests for analysis mathematical models, schemas, and statistics (T4.1)."""

import json

import pytest

from typist.schemas.analysis import (
    ParticipantResults,
    SetOutcome,
)
from typist.services.analysis import (
    bootstrap_iki_effect,
    compute_beta_interval,
    compute_median_and_iqr,
    sample_posterior_effects,
)


def test_schemas_defaults_and_backward_compatibility() -> None:
    """Verify that minimal dict instantiation matches schemas and round-trips via JSON."""
    set_data = {
        "set_label": "A",
        "arm": "control",
        "bigrams": ["th", "er"],
        "baseline_attempts": 100,
        "baseline_errors": 5,
        "baseline_error_rate": 0.05,
        "retest_attempts": 100,
        "retest_errors": 4,
        "retest_error_rate": 0.04,
    }
    set_outcome = SetOutcome.model_validate(set_data)
    assert set_outcome.retained_bigrams == []
    assert set_outcome.dropped_bigrams == []
    assert set_outcome.baseline_beta_ci_lower is None
    assert set_outcome.baseline_iki_n == 0

    results_data = {
        "participant_id": "p-123",
        "alias": "alice",
        "status": "done",
        "baseline_wpm": 60.0,
        "retest_wpm": 65.0,
        "sets": [set_data],
    }
    results = ParticipantResults.model_validate(results_data)
    assert results.is_builder is False
    assert results.is_blinded is False
    assert results.posterior_draws == 100_000
    assert results.bootstrap_resamples == 10_000
    assert results.seed == 20261030
    assert results.exclusions is None

    # Round trip JSON
    dumped = results.model_dump_json()
    loaded = json.loads(dumped)
    assert loaded["participant_id"] == "p-123"
    assert loaded["sets"][0]["set_label"] == "A"


def test_beta_interval_hand_computed_zero_errors() -> None:
    """Input: errors=0, attempts=10. Posterior is Beta(0.5, 10.5).

    Hand-computed / exact scipy.stats.beta.ppf([0.025, 0.975], 0.5, 10.5) yields (0.000048, 0.217196).
    """
    ci = compute_beta_interval(0, 10)
    assert ci is not None
    assert ci == (0.000048, 0.217196)


def test_beta_interval_hand_computed_all_errors() -> None:
    """Input: errors=10, attempts=10. Posterior is Beta(10.5, 0.5).

    Exact scipy.stats.beta.ppf([0.025, 0.975], 10.5, 0.5) yields (0.782804, 0.999952).
    """
    ci = compute_beta_interval(10, 10)
    assert ci is not None
    assert ci == (0.782804, 0.999952)


def test_beta_interval_zero_attempts_returns_none() -> None:
    """Input: errors=0, attempts=0. Output: None."""
    assert compute_beta_interval(0, 0) is None


def test_beta_interval_invalid_errors_raises() -> None:
    """Negative errors or errors > attempts raises ValueError."""
    with pytest.raises(ValueError):
        compute_beta_interval(-1, 10)
    with pytest.raises(ValueError):
        compute_beta_interval(11, 10)


def test_sample_posterior_effects_deterministic() -> None:
    """Input: base=(10, 100), ret=(2, 100), ctl_base=(10, 100), ctl_ret=(10, 100). Seed 20261030.

    d(s) approx -0.08, d(ctl) approx 0.0 => E(s) approx -0.08.
    Exact values with seed 20261030: median_effect is -0.078966 and share_below_zero is 0.9302.
    Assert abs(summary.median_effect - (-0.078966)) < 0.0001, summary.share_below_zero == 0.9302, and summary.share_below_zero > 0.90.
    """
    res = sample_posterior_effects(
        base_errors=10,
        base_attempts=100,
        ret_errors=2,
        ret_attempts=100,
        ctl_base_errors=10,
        ctl_base_attempts=100,
        ctl_ret_errors=10,
        ctl_ret_attempts=100,
        seed=20261030,
    )
    assert res is not None
    assert abs(res.median_effect - (-0.078966)) < 0.0001
    assert res.share_below_zero == 0.9302
    assert res.share_below_zero > 0.90
    assert res.ci_lower < res.median_effect < res.ci_upper


def test_compute_median_and_iqr_hand_computed() -> None:
    """Odd and even array medians, percentiles, and IQR."""
    odd_timing = compute_median_and_iqr([100.0, 150.0, 200.0])
    assert odd_timing == (150.0, 125.0, 175.0, 50.0)

    even_timing = compute_median_and_iqr([100.0, 120.0, 180.0, 200.0])
    assert even_timing == (150.0, 115.0, 185.0, 70.0)

    assert compute_median_and_iqr([]) is None


def test_bootstrap_iki_effect_deterministic() -> None:
    """Arm drops by 50ms, control drops by 0ms => F(s) = -50.0ms."""
    arm_base = [200.0, 210.0, 190.0]
    arm_ret = [150.0, 160.0, 140.0]
    ctl_base = [200.0, 210.0, 190.0]
    ctl_ret = [200.0, 210.0, 190.0]

    summary = bootstrap_iki_effect(
        arm_base,
        arm_ret,
        ctl_base,
        ctl_ret,
        seed=20261030,
    )
    assert summary is not None
    assert summary.median_effect == -50.0
    assert summary.ci_lower <= -50.0 <= summary.ci_upper
