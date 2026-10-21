"""corpus/build.py: artifact shape, deterministic bytes, and the frequency-weighted ranking."""

from pathlib import Path

from typist.corpus.build import build_corpus
from typist.corpus.word_index import TOP_BIGRAMS_FILENAME, WORDS_FILENAME, WordIndex

EXPECTED_TOP20 = [
    "th",
    "he",
    "in",
    "an",
    "er",
    "re",
    "on",
    "at",
    "nd",
    "or",
    "ou",
    "to",
    "en",
    "ng",
    "it",
    "is",
    "es",
    "st",
    "ha",
    "ar",
]


def test_build_writes_both_artifacts_with_the_right_shape(tmp_path: Path) -> None:
    build_corpus(tmp_path, word_count=2000, tracked_count=50)
    index = WordIndex.load(tmp_path)
    assert (tmp_path / WORDS_FILENAME).exists()
    assert (tmp_path / TOP_BIGRAMS_FILENAME).exists()
    assert len(index.words) == 2000
    assert len(index.tracked_bigrams) == 50
    assert all(w.isascii() and w.isalpha() for w in index.words)
    assert all(index.frequencies[w] > 0.0 for w in index.words)


def test_tracked_bigram_ranking_matches_the_frozen_prefix(tmp_path: Path) -> None:
    build_corpus(tmp_path, word_count=20000, tracked_count=150)
    index = WordIndex.load(tmp_path)
    assert list(index.tracked_bigrams[:20]) == EXPECTED_TOP20
    assert len(index.tracked_bigrams) == 150


def test_build_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "a"
    second = tmp_path / "b"
    build_corpus(first, word_count=2000, tracked_count=50)
    build_corpus(second, word_count=2000, tracked_count=50)
    for name in (WORDS_FILENAME, TOP_BIGRAMS_FILENAME):
        assert (first / name).read_bytes() == (second / name).read_bytes()
