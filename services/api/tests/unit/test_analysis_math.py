"""Unit tests for analysis mathematical models, schemas, and statistics (T4.1)."""

import json

from typist.schemas.analysis import (
    BigramMatrix,
    DroppedBigram,
    ExcludedSession,
    ExclusionsReport,
    MatrixCell,
    ParticipantResults,
    SetOutcome,
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
