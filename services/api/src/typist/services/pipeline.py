"""Scripted keystroke generator and dev-only pipeline test runner (design doc 16; T2.10)."""

import random
from typing import Final

from typist.schemas.events import KeystrokeEventIn

DEFAULT_TYPING_IKI_MS: Final[float] = 100.0
DEFAULT_TYPING_DWELL_MS: Final[float] = 50.0
_PRINTABLE_SUBSTITUTES: Final[dict[str, str]] = {
    "a": "b",
    "b": "c",
    "c": "d",
    "d": "e",
    "e": "f",
    "f": "g",
    "g": "h",
    "h": "i",
    "i": "j",
    "j": "k",
    "k": "l",
    "l": "m",
    "m": "n",
    "n": "o",
    "o": "p",
    "p": "q",
    "q": "r",
    "r": "s",
    "s": "t",
    "t": "u",
    "u": "v",
    "v": "w",
    "w": "x",
    "x": "y",
    "y": "z",
    "z": "a",
    " ": "e",
}


def _char_to_code(char: str) -> str:
    if char == " ":
        return "Space"
    return f"Key{char.upper()}"


def script_keystrokes(
    target_text: str,
    *,
    error_rate: float = 0.05,
    rng: random.Random | None = None,
    start_time_ms: float = 0.0,
    iki_ms: float = DEFAULT_TYPING_IKI_MS,
    dwell_ms: float = DEFAULT_TYPING_DWELL_MS,
) -> list[KeystrokeEventIn]:
    """Generate a well-formed list of KeystrokeEventIn rows typing through target_text.

    Simulates realistic human-like typing:
    - Monotonically increasing t_down_ms advancing by iki_ms per key event.
    - Constant positive dwell_ms with t_up_ms = t_down_ms + dwell_ms (0% missing keyups).
    - When an error is injected (with probability error_rate on alphabetic chars):
      1. Types an incorrect char (outcome='error', first_attempt=True).
      2. Types 'Backspace' (outcome='backspace', expected_char=None, first_attempt=None,
         target_index=max(0, i - 1) per D25).
      3. Types the correct char (outcome='correct', first_attempt=False).
    - seq strictly increases starting from 0 with no gaps.
    - All generated rows strictly pass KeystrokeEventIn._check_invariants.
    """
    effective_rng = rng if rng is not None else random.Random(42)
    events: list[KeystrokeEventIn] = []
    current_t = start_time_ms
    prev_down_t: float | None = None

    for i, expected in enumerate(target_text):
        should_error = (
            error_rate > 0.0 and expected in _PRINTABLE_SUBSTITUTES and effective_rng.random() < error_rate
        )
        if should_error:
            # 1. Error keystroke
            wrong_key = _PRINTABLE_SUBSTITUTES[expected]
            iki = None if prev_down_t is None else (current_t - prev_down_t)
            events.append(
                KeystrokeEventIn(
                    seq=len(events),
                    key=wrong_key,
                    code=_char_to_code(wrong_key),
                    t_down_ms=current_t,
                    t_up_ms=current_t + dwell_ms,
                    dwell_ms=dwell_ms,
                    iki_ms=iki,
                    target_index=i,
                    expected_char=expected,
                    outcome="error",
                    first_attempt=True,
                    after_pause=False,
                    handler_ms=0.1,
                    dispatch_lag_ms=0.1,
                )
            )
            prev_down_t = current_t
            current_t += iki_ms

            # 2. Backspace
            backspace_target_index = max(0, i - 1)
            iki = current_t - prev_down_t
            events.append(
                KeystrokeEventIn(
                    seq=len(events),
                    key="Backspace",
                    code="Backspace",
                    t_down_ms=current_t,
                    t_up_ms=current_t + dwell_ms,
                    dwell_ms=dwell_ms,
                    iki_ms=iki,
                    target_index=backspace_target_index,
                    expected_char=None,
                    outcome="backspace",
                    first_attempt=None,
                    after_pause=False,
                    handler_ms=0.1,
                    dispatch_lag_ms=0.1,
                )
            )
            prev_down_t = current_t
            current_t += iki_ms

            # 3. Corrected keystroke
            iki = current_t - prev_down_t
            events.append(
                KeystrokeEventIn(
                    seq=len(events),
                    key=expected,
                    code=_char_to_code(expected),
                    t_down_ms=current_t,
                    t_up_ms=current_t + dwell_ms,
                    dwell_ms=dwell_ms,
                    iki_ms=iki,
                    target_index=i,
                    expected_char=expected,
                    outcome="correct",
                    first_attempt=False,
                    after_pause=False,
                    handler_ms=0.1,
                    dispatch_lag_ms=0.1,
                )
            )
            prev_down_t = current_t
            current_t += iki_ms
        else:
            # Clean typing
            iki = None if prev_down_t is None else (current_t - prev_down_t)
            events.append(
                KeystrokeEventIn(
                    seq=len(events),
                    key=expected,
                    code=_char_to_code(expected),
                    t_down_ms=current_t,
                    t_up_ms=current_t + dwell_ms,
                    dwell_ms=dwell_ms,
                    iki_ms=iki,
                    target_index=i,
                    expected_char=expected,
                    outcome="correct",
                    first_attempt=True,
                    after_pause=False,
                    handler_ms=0.1,
                    dispatch_lag_ms=0.1,
                )
            )
            prev_down_t = current_t
            current_t += iki_ms

    return events
