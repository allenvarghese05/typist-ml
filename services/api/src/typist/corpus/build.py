"""Build the corpus artifacts from wordfreq (design doc 13.1-13.3; D17): deterministic JSON.

top_words takes the most frequent pure a-z words; rank_tracked_bigrams ranks letter-letter
bigrams by frequency-weighted occurrence (owner answer 6). build_corpus writes words.json and
top_bigrams.json to corpus_dir atomically (write to a .tmp sibling, then os.replace), so a run
never leaves a half-written file and re-running yields byte-identical artifacts (13.1
determinism). The order-3 n-gram model (13.4) is T3.1, not built here.
"""

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from wordfreq import top_n_list, word_frequency

from typist.corpus.word_index import TOP_BIGRAMS_FILENAME, WORDS_FILENAME, word_bigrams

# Candidates to scan before filtering: wordfreq's list includes non a-z tokens, so scan a
# multiple of the target count and stop once enough pure a-z words are collected.
_SCAN_FACTOR = 3


def top_words(word_count: int) -> list[tuple[str, float]]:
    """Return the word_count most frequent pure a-z words as (word, frequency), in rank order.

    Scans wordfreq's English list (most frequent first), keeping words that are pure ASCII
    letters (a-z after wordfreq's lowercasing) with a positive frequency, until word_count are
    collected. Deterministic for a pinned wordfreq (D17).
    """
    collected: list[tuple[str, float]] = []
    for word in top_n_list("en", word_count * _SCAN_FACTOR):
        if word.isascii() and word.isalpha():
            frequency = word_frequency(word, "en")
            if frequency > 0.0:
                collected.append((word, frequency))
                if len(collected) >= word_count:
                    break
    return collected


def rank_tracked_bigrams(
    words: list[tuple[str, float]], tracked_count: int
) -> list[tuple[str, float]]:
    """Rank letter-letter bigrams by frequency-weighted occurrence; return the top tracked_count.

    Each bigram's weight is the sum, over the words that contain it, of word_frequency times the
    number of times it occurs in the word. Ranked by weight descending, ties broken by the
    bigram ascending (so the ranking is total and deterministic). Returns (bigram, weight).
    """
    weights: dict[str, float] = defaultdict(float)
    for word, frequency in words:
        for bigram in word_bigrams(word):
            weights[bigram] += frequency
    ranked = sorted(weights.items(), key=lambda item: (-item[1], item[0]))
    return ranked[:tracked_count]


def _write_json_atomic(path: Path, payload: Any) -> None:
    """Write payload as JSON to path atomically: write path.tmp then os.replace onto path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    os.replace(tmp, path)


def build_corpus(corpus_dir: Path, *, word_count: int, tracked_count: int) -> None:
    """Build words.json and top_bigrams.json into corpus_dir (atomic, deterministic).

    words.json: {"corpus_word_count": N, "words": [[word, frequency], ...]} in rank order.
    top_bigrams.json: {"tracked_bigram_count": M, "bigrams": [[bigram, weight], ...]} ranked.
    """
    words = top_words(word_count)
    bigrams = rank_tracked_bigrams(words, tracked_count)
    _write_json_atomic(
        corpus_dir / WORDS_FILENAME,
        {"corpus_word_count": word_count, "words": [[w, f] for w, f in words]},
    )
    _write_json_atomic(
        corpus_dir / TOP_BIGRAMS_FILENAME,
        {"tracked_bigram_count": tracked_count, "bigrams": [[b, w] for b, w in bigrams]},
    )
