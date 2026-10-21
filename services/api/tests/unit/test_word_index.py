"""count_bigrams (letter-letter only) and a Hypothesis property over the a-z + space charset."""

from hypothesis import given
from hypothesis import strategies as st

from typist.corpus.word_index import count_bigrams


def test_count_bigrams_within_tokens_only() -> None:
    assert count_bigrams("to go") == {"to": 1, "go": 1}
    assert count_bigrams("the cat") == {"th": 1, "he": 1, "ca": 1, "at": 1}
    assert count_bigrams("letter") == {"le": 1, "et": 1, "tt": 1, "te": 1, "er": 1}
    assert count_bigrams("") == {}
    assert count_bigrams("a") == {}


@given(text=st.text(alphabet="abc ", min_size=0, max_size=30))
def test_count_bigrams_keys_are_two_letters_and_never_cross_a_space(text: str) -> None:
    counts = count_bigrams(text)
    for key in counts:
        assert len(key) == 2
        assert " " not in key
        assert all("a" <= ch <= "z" for ch in key)
    # Totals equal an independent within-token recount.
    expected = 0
    for token in text.split(" "):
        expected += sum(
            1 for i in range(len(token) - 1) if token[i].isalpha() and token[i + 1].isalpha()
        )
    assert sum(counts.values()) == expected
