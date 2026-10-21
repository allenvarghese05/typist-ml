"""Load the corpus artifacts and expose the bigram definition shared across the project (T1.8).

count_bigrams is the single letter-letter bigram count for text: it splits on single spaces and
counts only adjacent a-z pairs within a token, never across a space (D13; design doc 12.3). It
matches typist.services.attribution's letter rule and the seed fixture ("the cat" ->
{"th":1,"he":1,"ca":1,"at":1}). WordIndex loads words.json and top_bigrams.json (written by
corpus/build.py) and provides the words, their frequencies, the ranked tracked bigrams and a
bigram -> words index. The order-3 n-gram model (design doc 13.4) is not built here; it is T3.1.
"""

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

WORDS_FILENAME = "words.json"
TOP_BIGRAMS_FILENAME = "top_bigrams.json"


def count_bigrams(text: str) -> dict[str, int]:
    """Return the count of each letter-letter bigram in text (within tokens, never across a space).

    Splits on single spaces; for each token counts adjacent positions where both characters are
    a-z. Space-crossing pairs are never counted, and any non a-z character breaks a pair (D13).
    A bigram with zero count is simply absent (never a JSON null, per the JSONText contract).
    """
    counts: dict[str, int] = {}
    for token in text.split(" "):
        for i in range(len(token) - 1):
            first, second = token[i], token[i + 1]
            if "a" <= first <= "z" and "a" <= second <= "z":
                bigram = first + second
                counts[bigram] = counts.get(bigram, 0) + 1
    return counts


def word_bigrams(word: str) -> list[str]:
    """Return the list of adjacent 2-character slices of word (its letter bigrams, with repeats)."""
    return [word[i : i + 2] for i in range(len(word) - 1)]


@dataclass(frozen=True)
class WordIndex:
    """The corpus in memory: words in rank order, their frequencies, tracked bigrams, and a
    bigram -> words index. Built by WordIndex.load from the two JSON artifacts. Immutable."""

    words: tuple[str, ...]
    frequencies: dict[str, float]
    tracked_bigrams: tuple[str, ...]
    by_bigram: dict[str, tuple[str, ...]]

    @classmethod
    def load(cls, corpus_dir: Path) -> "WordIndex":
        """Load words.json and top_bigrams.json from corpus_dir and build the bigram index.

        Raises FileNotFoundError if either artifact is missing (the caller tells the user to run
        `typist corpus build`). The bigram index maps every letter bigram that appears in any word
        to the tuple of words that contain it, in the words' rank order.
        """
        words_data: Any = json.loads((corpus_dir / WORDS_FILENAME).read_text(encoding="utf-8"))
        bigrams_data: Any = json.loads(
            (corpus_dir / TOP_BIGRAMS_FILENAME).read_text(encoding="utf-8")
        )
        words = tuple(str(entry[0]) for entry in words_data["words"])
        frequencies = {str(entry[0]): float(entry[1]) for entry in words_data["words"]}
        tracked_bigrams = tuple(str(entry[0]) for entry in bigrams_data["bigrams"])
        grouped: dict[str, list[str]] = defaultdict(list)
        for word in words:
            for bigram in set(word_bigrams(word)):
                grouped[bigram].append(word)
        by_bigram = {bigram: tuple(members) for bigram, members in grouped.items()}
        return cls(
            words=words,
            frequencies=frequencies,
            tracked_bigrams=tracked_bigrams,
            by_bigram=by_bigram,
        )

    def words_containing(self, bigram: str) -> tuple[str, ...]:
        """Return the words (rank order) that contain bigram, or an empty tuple if none do."""
        return self.by_bigram.get(bigram, ())
