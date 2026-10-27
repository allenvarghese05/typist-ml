"""Unit tests for pure session_planner helpers: Latin square, block_order, labels, and phase resolution (T2.6)."""

import pytest

from typist.services.session_planner import (
    InvalidSessionPhaseError,
    block_label,
    encode_block_order,
    latin_square_arms,
    resolve_session_phase,
)


def test_latin_square_four_arms_rotates_daily_and_balances_positions() -> None:
    arms = ("control", "heuristic", "markov", "llm")
    rows = [latin_square_arms(arms, day) for day in range(4)]
    assert rows == [
        ("control", "heuristic", "markov", "llm"),
        ("heuristic", "markov", "llm", "control"),
        ("markov", "llm", "control", "heuristic"),
        ("llm", "control", "heuristic", "markov"),
    ]
    assert [encode_block_order(row) for row in rows] == ["CHML", "HMLC", "MLCH", "LCHM"]
    # Every arm appears once per row and once in each column (0..3) across 4 days.
    for row in rows:
        assert set(row) == set(arms)
    for col_idx in range(4):
        assert {rows[day][col_idx] for day in range(4)} == set(arms)
    # Day 4 wraps back to row 0; day 9 (10th practice day) wraps to row 1.
    assert latin_square_arms(arms, 4) == rows[0]
    assert latin_square_arms(arms, 9) == rows[1]


def test_latin_square_two_arms_cut_line_mode() -> None:
    arms = ("control", "heuristic")
    assert latin_square_arms(arms, 0) == ("control", "heuristic")
    assert latin_square_arms(arms, 1) == ("heuristic", "control")
    assert latin_square_arms(arms, 2) == ("control", "heuristic")
    assert encode_block_order(latin_square_arms(arms, 0)) == "CH"
    assert encode_block_order(latin_square_arms(arms, 1)) == "HC"


def test_latin_square_and_encode_block_order_reject_empty_inputs() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        latin_square_arms((), 0)
    with pytest.raises(ValueError, match="non-empty"):
        encode_block_order(())
    with pytest.raises(ValueError, match="non-empty"):
        encode_block_order(("control", ""))


def test_block_label_returns_one_based_blinded_labels() -> None:
    assert [block_label(i) for i in range(4)] == ["Block 1", "Block 2", "Block 3", "Block 4"]
    with pytest.raises(ValueError, match=">= 0"):
        block_label(-1)


def test_resolve_session_phase_maps_valid_statuses_and_rejects_invalid() -> None:
    with pytest.raises(InvalidSessionPhaseError, match="consent"):
        resolve_session_phase("enrolled")
    assert resolve_session_phase("baseline", "baseline") == "baseline"
    assert resolve_session_phase("assigned") == "practice"
    assert resolve_session_phase("practice", "practice") == "practice"
    assert resolve_session_phase("retest") == "retest"
    assert resolve_session_phase("retest", "retest") == "retest"

    for terminal in ("done", "withdrawn", "unknown"):
        with pytest.raises(InvalidSessionPhaseError):
            resolve_session_phase(terminal)

    with pytest.raises(InvalidSessionPhaseError, match="invalid session phase"):
        resolve_session_phase("practice", "not_a_phase")

    with pytest.raises(InvalidSessionPhaseError, match="conflicts"):
        resolve_session_phase("baseline", "practice")
