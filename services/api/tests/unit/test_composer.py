"""compose_baseline: determinism and the 13.3 / owner-answer-8 composition rules (pure)."""

import random
from collections import Counter

import pytest

from typist.corpus.build import build_corpus
from typist.corpus.word_index import WordIndex
from typist.services.test_composer import BaselineConfig, compose_baseline

# Small, fast parameters: enough words and bigrams to exercise every rule without the full build.
CONFIG = BaselineConfig(
    tracked_bigram_count=50,
    baseline_min_occurrences=15,
    baseline_parts=2,
    baseline_part_chars=600,
    corpus_seed=20261019,
)


@pytest.fixture(scope="module")
def index(tmp_path_factory: pytest.TempPathFactory) -> WordIndex:
    corpus_dir = tmp_path_factory.mktemp("corpus")
    build_corpus(corpus_dir, word_count=5000, tracked_count=50)
    return WordIndex.load(corpus_dir)


def _recount(text: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for token in text.split(" "):
        for i in range(len(token) - 1):
            if token[i].isalpha() and token[i + 1].isalpha():
                counts[token[i : i + 2]] += 1
    return dict(counts)


def test_same_seed_gives_identical_texts(index: WordIndex) -> None:
    a = compose_baseline(CONFIG, index, random.Random(CONFIG.corpus_seed))
    b = compose_baseline(CONFIG, index, random.Random(CONFIG.corpus_seed))
    assert [p.text for p in a] == [p.text for p in b]


def test_different_seed_gives_different_text(index: WordIndex) -> None:
    a = compose_baseline(CONFIG, index, random.Random(1))
    b = compose_baseline(CONFIG, index, random.Random(2))
    assert [p.text for p in a] != [p.text for p in b]


def test_passages_are_shared_form_a_with_distinct_parts(index: WordIndex) -> None:
    passages = compose_baseline(CONFIG, index, random.Random(CONFIG.corpus_seed))
    assert len(passages) == 2
    assert [p.part for p in passages] == [0, 1]
    for passage in passages:
        assert passage.kind == "baseline"
        assert passage.form == "A"
        assert passage.participant_id is None


def test_text_charset_and_spacing(index: WordIndex) -> None:
    for passage in compose_baseline(CONFIG, index, random.Random(CONFIG.corpus_seed)):
        text = passage.text
        assert text == text.strip()
        assert "  " not in text
        assert all(ch == " " or "a" <= ch <= "z" for ch in text)


def test_words_are_two_to_ten_letters_and_at_most_twice_per_part(index: WordIndex) -> None:
    for passage in compose_baseline(CONFIG, index, random.Random(CONFIG.corpus_seed)):
        words = passage.text.split(" ")
        assert all(2 <= len(word) <= 10 for word in words)
        assert all(count <= 2 for count in Counter(words).values())


def test_bigram_counts_equal_an_independent_recount(index: WordIndex) -> None:
    for passage in compose_baseline(CONFIG, index, random.Random(CONFIG.corpus_seed)):
        assert passage.bigram_counts == _recount(passage.text)


def test_each_part_reaches_the_budget_by_at_most_one_word(index: WordIndex) -> None:
    for passage in compose_baseline(CONFIG, index, random.Random(CONFIG.corpus_seed)):
        words = passage.text.split(" ")
        assert len(passage.text) >= CONFIG.baseline_part_chars
        without_last = " ".join(words[:-1])
        assert len(without_last) < CONFIG.baseline_part_chars
