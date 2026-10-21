"""A Hypothesis helper that builds a well-formed keystroke stream for one target (T1.7).

It walks the target the way TextCursor/KeystrokeRecorder do (first attempt per position, Backspace
rows with null expected_char/first_attempt, contiguous seq from 0, non-decreasing t_down_ms,
arbitrary after_pause). It is used only by the property test; it is not imported into src/ and never
ports TextCursor (owner answer 5). "Well-formed" means every position has at most one first-attempt
row, which is exactly what makes the attempts-vs-letter-pairs invariant provable.
"""

from collections.abc import Callable
from typing import Any, Final

from hypothesis import strategies as st

from typist.models import KeystrokeEvent

TARGET_ALPHABET: Final = "abc "
_WRONG_FOR: Final = {"a": "b", "b": "c", "c": "a", " ": "a"}


def targets() -> st.SearchStrategy[str]:
    """Targets over a small [a-z ] alphabet, including empty and single-char (D13 charset)."""
    return st.text(alphabet=TARGET_ALPHABET, min_size=0, max_size=12)


def letter_pair_positions(target: str) -> int:
    """Number of positions j in 1..len-1 where target[j-1] and target[j] are both a-z letters."""
    return sum(
        1
        for j in range(1, len(target))
        if target[j - 1].islower() and target[j].islower() and target[j - 1].isalpha()
    )


def build_stream(draw: Callable[..., Any], target: str) -> list[KeystrokeEvent]:
    """Draw a well-formed keystroke stream for target: a list of KeystrokeEvent rows.

    Each step draws correct / wrong / backspace (backspace only when index > 0). A printable key
    compares with target[index], records target_index = index, and advances; the row is a first
    attempt iff no earlier printable key recorded that index. A backspace steps index back (clamped
    at 0) and records the new index with null expected_char/first_attempt. seq is contiguous from 0;
    t_down_ms strictly increases by a drawn positive delta; after_pause is drawn freely. The block
    may be left unfinished (attribution tolerates a missing tail).
    """
    n_actions = draw(st.integers(min_value=0, max_value=24))
    rows: list[KeystrokeEvent] = []
    index = 0
    t_down = float(draw(st.integers(min_value=0, max_value=100)))
    recorded: set[int] = set()
    for _ in range(n_actions):
        if index >= len(target):
            break
        choices = ["correct", "wrong"]
        if index > 0:
            choices.append("backspace")
        kind = draw(st.sampled_from(choices))
        after_pause = draw(st.booleans())
        t_down += float(draw(st.integers(min_value=1, max_value=4000)))
        seq = len(rows)
        if kind == "backspace":
            index = max(index - 1, 0)
            rows.append(
                KeystrokeEvent(
                    block_id="prop",
                    seq=seq,
                    key="Backspace",
                    code="Backspace",
                    t_down_ms=t_down,
                    target_index=index,
                    expected_char=None,
                    outcome="backspace",
                    first_attempt=None,
                    after_pause=after_pause,
                    handler_ms=0.5,
                    dispatch_lag_ms=1.25,
                )
            )
            continue
        expected = target[index]
        if kind == "correct":
            typed = expected
            outcome = "correct"
        else:
            typed = _WRONG_FOR[expected]
            outcome = "error"
        first_attempt = index not in recorded
        recorded.add(index)
        rows.append(
            KeystrokeEvent(
                block_id="prop",
                seq=seq,
                key=typed,
                code=f"Key{typed.upper()}" if typed != " " else "Space",
                t_down_ms=t_down,
                target_index=index,
                expected_char=expected,
                outcome=outcome,
                first_attempt=first_attempt,
                after_pause=after_pause,
                handler_ms=0.5,
                dispatch_lag_ms=1.25,
            )
        )
        index += 1
    return rows
