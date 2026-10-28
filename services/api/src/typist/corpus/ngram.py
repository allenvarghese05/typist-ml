"""Order-3 character n-gram model trained from WordIndex (design doc 7, 13.4 step 1).

CharNGramModel is an in-memory character-level trigram model: given context (c_{i-2}, c_{i-1}), it
provides the weighted transition counts for c_i. Word start is represented by sentinel ('^', '^');
word end is represented by sentinel '$'. Padded characters for word 'the' are:
  ['^', '^', 't', 'h', 'e', '$']
Transitions:
  ('^', '^') -> 't'
  ('^', 't') -> 'h'
  ('t', 'h') -> 'e'
  ('h', 'e') -> '$'
Each word's transitions are weighted by sqrt(frequency) (13.4 step 1). Training takes < 30ms for
20,000 words. Pure Python 3.12: no external model files, no mlx-lm, runs identically on Linux CI.
"""

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
import math
from typing import Final

from typist.corpus.word_index import WordIndex

START_CHAR: Final[str] = "^"
END_CHAR: Final[str] = "$"
START_CONTEXT: Final[tuple[str, str]] = (START_CHAR, START_CHAR)


@dataclass(frozen=True)
class CharNGramModel:
    """Immutable order-3 character n-gram model with start and end sentinels."""

    transitions: dict[tuple[str, str], dict[str, float]]

    @classmethod
    def from_word_index(cls, index: WordIndex) -> "CharNGramModel":
        """Build a character trigram model from WordIndex words weighted by sqrt(frequency)."""
        counts: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for word in index.words:
            freq = index.frequencies.get(word, 0.0)
            if freq <= 0.0:
                continue
            weight = math.sqrt(freq)
            chars = [START_CHAR, START_CHAR, *word, END_CHAR]
            for i in range(2, len(chars)):
                ctx = (chars[i - 2], chars[i - 1])
                c = chars[i]
                counts[ctx][c] += weight
        # Convert to standard dict of dicts
        frozen_transitions: dict[tuple[str, str], dict[str, float]] = {
            ctx: dict(next_map) for ctx, next_map in counts.items()
        }
        return cls(transitions=frozen_transitions)

    def get_transitions(self, context: tuple[str, str]) -> Mapping[str, float]:
        """Return the next character weights for context, or an empty mapping if unknown."""
        return self.transitions.get(context, {})
