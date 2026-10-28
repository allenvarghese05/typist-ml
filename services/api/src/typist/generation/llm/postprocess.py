"""Post-processing for LLM generated text (design doc 13.5; owner answers 1 and 2).

Transforms raw model text into valid typing practice candidate text:
1. Lowercase ASCII conversion.
2. Any character outside [a-z] is replaced with a space (stripping punctuation, digits, quotes).
3. Consecutive whitespace is collapsed to single spaces and stripped from ends.
4. Truncates cleanly at a word boundary to max_chars (default 300).
5. Leaves words intact so validator.validate() measures real_word_ratio and applies the gate.
"""

import re
from typing import Final

_NON_AZ_PATTERN: Final[re.Pattern[str]] = re.compile(r"[^a-z]+")


def clean_llm_output(raw_output: str, max_chars: int = 300) -> str:
    """Clean and truncate raw LLM output at a word boundary up to max_chars.

    Returns lowercase words separated by single spaces. Does not drop non-dictionary words;
    the validator evaluates real_word_ratio against WordIndex.words.
    """
    lowered = raw_output.lower()
    spaced = _NON_AZ_PATTERN.sub(" ", lowered).strip()
    if not spaced:
        return ""
    words = spaced.split()
    selected: list[str] = []
    length = 0
    for word in words:
        addition = len(word) + (1 if selected else 0)
        if length + addition > max_chars:
            break
        selected.append(word)
        length += addition
    return " ".join(selected)
