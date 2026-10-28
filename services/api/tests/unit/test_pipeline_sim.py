"""Unit tests for scripted keystroke generation (design doc 16; T2.10)."""

from typist.models import KeystrokeEvent
from typist.schemas.events import KeystrokeEventIn
from typist.services.attribution import attribute_block
from typist.services.pipeline_sim import generate_scripted_keystrokes


def test_generate_scripted_keystrokes_empty() -> None:
    events = generate_scripted_keystrokes("")
    assert events == []


def test_generate_scripted_keystrokes_invariants() -> None:
    target = "the quick brown fox jumps over the lazy dog"
    events = generate_scripted_keystrokes(target, error_rate=0.25, seed=123)

    assert len(events) > len(target)  # Due to errors and backspaces

    for idx, ev in enumerate(events):
        assert ev.seq == idx
        KeystrokeEventIn.model_validate(ev)

        assert ev.dwell_ms is not None
        assert 20.0 <= ev.dwell_ms <= 300.0
        assert ev.t_up_ms == round(ev.t_down_ms + ev.dwell_ms, 2)

        if idx > 0:
            assert ev.t_down_ms > events[idx - 1].t_down_ms
            assert ev.iki_ms is not None
            assert ev.iki_ms > 0

        if ev.outcome == "backspace":
            assert ev.key == "Backspace"
            assert ev.code == "Backspace"
            assert ev.expected_char is None
            assert ev.first_attempt is None
        else:
            assert ev.expected_char is not None
            assert ev.first_attempt is not None
            assert ev.outcome in ("correct", "error")


def test_generate_scripted_keystrokes_attribution() -> None:
    target = "the the the the the the the the the"

    # Clean typing: 0 errors
    clean_events = generate_scripted_keystrokes(target, error_rate=0.0, seed=42)
    clean_rows = [KeystrokeEvent(block_id="test_clean", **e.model_dump()) for e in clean_events]
    clean_stats = {s.bigram: s for s in attribute_block(target, clean_rows)}
    assert "th" in clean_stats
    assert clean_stats["th"].attempts == 9
    assert clean_stats["th"].errors == 0

    # With moderate errors injected: errors must be attributed per D14
    err_events = generate_scripted_keystrokes(target, error_rate=0.3, seed=42)
    err_rows = [KeystrokeEvent(block_id="test_err", **e.model_dump()) for e in err_events]
    err_stats = {s.bigram: s for s in attribute_block(target, err_rows)}
    # An error on 'h' following a correct 't' attributes 1 attempt and 1 error to 'th'
    assert "th" in err_stats
    assert err_stats["th"].errors > 0
