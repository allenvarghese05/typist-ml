"""Unit tests for CharNGramModel (T3.1, design doc 13.4 step 1)."""

from pathlib import Path
import pytest

from typist.corpus.build import build_corpus
from typist.corpus.ngram import END_CHAR, START_CHAR, START_CONTEXT, CharNGramModel
from typist.corpus.word_index import WordIndex


@pytest.fixture(scope="module")
def index(tmp_path_factory: pytest.TempPathFactory) -> WordIndex:
    corpus_dir = tmp_path_factory.mktemp("corpus_ngram")
    build_corpus(corpus_dir, word_count=1000, tracked_count=50)
    return WordIndex.load(corpus_dir)


def test_ngram_trains_successfully_and_has_start_context(index: WordIndex) -> None:
    model = CharNGramModel.from_word_index(index)
    transitions = model.get_transitions(START_CONTEXT)
    assert len(transitions) > 0
    # Start context transitions must only emit letters (no end marker '$' directly at start)
    assert all("a" <= char <= "z" for char in transitions)
    assert END_CHAR not in transitions


def test_ngram_end_char_is_present_in_terminal_contexts(index: WordIndex) -> None:
    model = CharNGramModel.from_word_index(index)
    # Collect all characters transitioning to END_CHAR
    has_end = any(END_CHAR in next_map for next_map in model.transitions.values())
    assert has_end


def test_ngram_returns_empty_mapping_on_unknown_context(index: WordIndex) -> None:
    model = CharNGramModel.from_word_index(index)
    assert model.get_transitions(("!", "?")) == {}


def test_ngram_weights_are_positive(index: WordIndex) -> None:
    model = CharNGramModel.from_word_index(index)
    for ctx, next_map in model.transitions.items():
        assert len(ctx) == 2
        for char, weight in next_map.items():
            assert weight > 0.0
