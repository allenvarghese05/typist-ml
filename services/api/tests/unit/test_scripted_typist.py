"""Unit tests for scripted keystroke generator (design doc 16; T2.10)."""

import random

from typist.schemas.events import KeystrokeEventIn
from typist.services.pipeline import script_keystrokes


def test_script_keystrokes_clean_typing_invariants() -> None:
    text = "the quick brown fox"
    events = script_keystrokes(text, error_rate=0.0)

    assert len(events) == len(text)
    for idx, ev in enumerate(events):
        assert ev.outcome == "correct"
        assert ev.first_attempt is True
        assert ev.seq == idx
        assert ev.key == text[idx]
        assert ev.target_index == idx
        assert ev.expected_char == text[idx]
        assert ev.dwell_ms == 50.0
        assert ev.t_up_ms == ev.t_down_ms + 50.0
        if idx == 0:
            assert ev.iki_ms is None
        else:
            assert ev.iki_ms == 100.0
            assert ev.t_down_ms > events[idx - 1].t_down_ms

        # Invariant check via pydantic
        ev._check_invariants()


def test_script_keystrokes_with_errors_invariants() -> None:
    text = "hello world"
    events = script_keystrokes(text, error_rate=1.0)

    # Each character should produce 3 events: wrong, backspace, correct
    assert len(events) == len(text) * 3

    # Check sequence monotonicity and no gaps
    for idx, ev in enumerate(events):
        assert ev.seq == idx
        ev._check_invariants()

    # Verify backspace events and corrected events
    for i in range(len(text)):
        err_ev = events[i * 3]
        bs_ev = events[i * 3 + 1]
        cor_ev = events[i * 3 + 2]

        assert err_ev.outcome == "error"
        assert err_ev.first_attempt is True
        assert err_ev.expected_char == text[i]
        assert err_ev.target_index == i

        assert bs_ev.outcome == "backspace"
        assert bs_ev.key == "Backspace"
        assert bs_ev.code == "Backspace"
        assert bs_ev.expected_char is None
        assert bs_ev.first_attempt is None
        assert bs_ev.target_index == max(0, i - 1)

        assert cor_ev.outcome == "correct"
        assert cor_ev.first_attempt is False
        assert cor_ev.key == text[i]
        assert cor_ev.expected_char == text[i]
        assert cor_ev.target_index == i


def test_script_keystrokes_deterministic_seeding() -> None:
    text = "typist ml experiment pipeline testing"
    events_a1 = script_keystrokes(text, error_rate=0.2, rng=random.Random(12345))
    events_a2 = script_keystrokes(text, error_rate=0.2, rng=random.Random(12345))
    events_b = script_keystrokes(text, error_rate=0.2, rng=random.Random(99999))

    assert [e.model_dump() for e in events_a1] == [e.model_dump() for e in events_a2]

    # Different seeds produce different event sequences (different error locations/counts)
    dumps_a = [e.model_dump() for e in events_a1]
    dumps_b = [e.model_dump() for e in events_b]
    assert dumps_a != dumps_b
