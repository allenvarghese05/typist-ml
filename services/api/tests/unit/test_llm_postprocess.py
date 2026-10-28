"""Unit tests for clean_llm_output (T3.2)."""

from typist.generation.llm.postprocess import clean_llm_output


def test_clean_llm_output_lowercases_and_removes_punctuation() -> None:
    raw = "Here are your words: Back, know, Clock! Snow, check... Brown (quick) #123."
    cleaned = clean_llm_output(raw, max_chars=300)
    assert cleaned == "here are your words back know clock snow check brown quick"


def test_clean_llm_output_collapses_whitespace() -> None:
    raw = "  first   \t\n  second \n\n  third  "
    cleaned = clean_llm_output(raw, max_chars=300)
    assert cleaned == "first second third"


def test_clean_llm_output_truncates_at_word_boundary() -> None:
    # Each word is 4 chars + 1 space = 5 chars. 10 words = 49 chars.
    raw = "word " * 20
    cleaned = clean_llm_output(raw, max_chars=49)
    assert len(cleaned) == 49
    assert cleaned == " ".join(["word"] * 10)


def test_clean_llm_output_does_not_slice_words_in_half() -> None:
    raw = "short words that will be cut before the last word"
    cleaned = clean_llm_output(raw, max_chars=20)
    # "short words that" is 16 chars; adding " will" would be 21 chars (> 20)
    assert cleaned == "short words that"
    assert len(cleaned) <= 20


def test_clean_llm_output_empty_or_punctuation_only() -> None:
    assert clean_llm_output("") == ""
    assert clean_llm_output("... !!! ??? 12345 --") == ""


def test_clean_llm_output_preserves_non_dictionary_words_for_validator() -> None:
    raw = "pseudoword validword anothervalidword"
    cleaned = clean_llm_output(raw, max_chars=300)
    assert cleaned == "pseudoword validword anothervalidword"
