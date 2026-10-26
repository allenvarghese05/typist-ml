"""compose_baseline and compose_retest: determinism, >= 40 coverage, and form-A word exclusion (pure)."""

import random
from collections import Counter, defaultdict

import pytest

from typist.corpus.build import build_corpus
from typist.corpus.word_index import WordIndex
from typist.services.test_composer import (
    BaselineConfig,
    RetestConfig,
    compose_baseline,
    compose_retest,
)

# Small, fast parameters: enough words and bigrams to exercise every rule without the full build.
CONFIG = BaselineConfig(
    tracked_bigram_count=50,
    baseline_min_occurrences=15,
    baseline_parts=2,
    baseline_part_chars=600,
    corpus_seed=20261019,
)

RETEST_CONFIG = RetestConfig(
    tracked_bigram_count=50,
    retest_min_occurrences=40,
    retest_parts=2,
    retest_part_chars=1800,
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


def test_retest_covers_assigned_bigrams_at_40_and_avoids_form_a_words(
    index: WordIndex,
) -> None:
    form_a = compose_baseline(CONFIG, index, random.Random(CONFIG.corpus_seed))
    form_a_words = {word for passage in form_a for word in passage.text.split(" ")}
    assigned = index.tracked_bigrams[:16]

    form_b = compose_retest(
        RETEST_CONFIG,
        index,
        "p-retest-01",
        assigned,
        random.Random(f"{RETEST_CONFIG.corpus_seed}:p-retest-01:B"),
        excluded_words=form_a_words,
    )
    assert len(form_b) == 2
    assert [p.part for p in form_b] == [0, 1]

    combined: dict[str, int] = defaultdict(int)
    form_b_words: set[str] = set()
    for passage in form_b:
        assert passage.kind == "retest"
        assert passage.form == "B"
        assert passage.participant_id == "p-retest-01"
        assert passage.text == passage.text.strip()
        assert "  " not in passage.text
        assert all(ch == " " or "a" <= ch <= "z" for ch in passage.text)
        assert len(passage.text) >= RETEST_CONFIG.retest_part_chars
        words = passage.text.split(" ")
        assert all(2 <= len(word) <= 10 for word in words)
        assert all(count <= 2 for count in Counter(words).values())
        assert passage.bigram_counts == _recount(passage.text)
        form_b_words.update(words)
        for bg, count in passage.bigram_counts.items():
            combined[bg] += count

    for bigram in assigned:
        assert combined[bigram] >= 40, (bigram, combined[bigram])
        assert form_b[0].bigram_counts.get(bigram, 0) >= 20

    # With a 5,000-word vocabulary, non-form-A words easily cover all 16 bigrams without reusing
    # a single word from form A.
    assert form_b_words.isdisjoint(form_a_words)


def test_retest_is_deterministic_and_varies_by_participant_seed(index: WordIndex) -> None:
    assigned = index.tracked_bigrams[:12]
    run_1 = compose_retest(RETEST_CONFIG, index, "p-01", assigned, random.Random("20261019:p-01:B"))
    run_2 = compose_retest(RETEST_CONFIG, index, "p-01", assigned, random.Random("20261019:p-01:B"))
    other = compose_retest(RETEST_CONFIG, index, "p-02", assigned, random.Random("20261019:p-02:B"))
    assert [p.text for p in run_1] == [p.text for p in run_2]
    assert [p.text for p in run_1] != [p.text for p in other]


def test_retest_falls_back_to_form_a_words_only_when_non_form_a_words_exhausted() -> None:
    # Tiny synthetic vocabulary for bigram 'qq': 2 non-form-A words ('qqaa', 'qqbb') can only
    # provide 2 * 2 = 4 occurrences per part (8 across 2 parts). To reach 12 occurrences across
    # 2 parts, the composer must use 'qqaa'/'qqbb' first and then fall back to the form-A word
    # 'qqcc'. For bigram 'zz', enough non-form-A words exist ('zzaa', 'zzbb', 'zzcc', 'zzdd') so
    # the form-A word 'zzee' must never be used.
    words = ("qqcc", "qqaa", "qqbb", "zzee", "zzaa", "zzbb", "zzcc", "zzdd")
    tiny_index = WordIndex(
        words=words,
        frequencies={w: 1.0 for w in words},
        tracked_bigrams=("qq", "zz"),
        by_bigram={
            "qq": ("qqcc", "qqaa", "qqbb"),
            "zz": ("zzee", "zzaa", "zzbb", "zzcc", "zzdd"),
        },
    )
    tiny_config = RetestConfig(
        tracked_bigram_count=2,
        retest_min_occurrences=12,
        retest_parts=2,
        retest_part_chars=40,
        corpus_seed=1,
    )
    passages = compose_retest(
        tiny_config,
        tiny_index,
        "p-fallback",
        ("qq", "zz"),
        random.Random(42),
        excluded_words={"qqcc", "zzee"},
    )
    combined_qq = sum(p.bigram_counts.get("qq", 0) for p in passages)
    combined_zz = sum(p.bigram_counts.get("zz", 0) for p in passages)
    assert combined_qq >= 12
    assert combined_zz >= 12
    used_words = {w for p in passages for w in p.text.split(" ")}
    assert "qqcc" in used_words  # needed as fallback once qqaa and qqbb hit 2 uses/part
    assert "zzee" not in used_words  # never used because zzaa..zzdd sufficed


def test_retest_rejects_invalid_arguments(index: WordIndex) -> None:
    with pytest.raises(ValueError, match="participant_id"):
        compose_retest(RETEST_CONFIG, index, "", ("th",), random.Random(1))
    with pytest.raises(ValueError, match="assigned_bigrams"):
        compose_retest(RETEST_CONFIG, index, "p-01", (), random.Random(1))
    with pytest.raises(ValueError, match="no usable words"):
        compose_retest(RETEST_CONFIG, index, "p-01", ("qx",), random.Random(1))
