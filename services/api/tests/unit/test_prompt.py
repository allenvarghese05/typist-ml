"""Unit tests for Prompt v1 formatting and messages (T3.2)."""

from typist.generation.llm.prompt import (
    PROMPT_V1_EXAMPLE_ASSISTANT,
    PROMPT_V1_EXAMPLE_USER,
    PROMPT_V1_SYSTEM,
    PROMPT_VERSION_V1,
    build_prompt_v1_messages,
    format_target_bigrams,
)


def test_format_target_bigrams() -> None:
    assert format_target_bigrams(("ck", "ow")) == "ck, ow"
    assert format_target_bigrams(("th", "ea", "in", "st")) == "th, ea, in, st"
    assert format_target_bigrams(("th", "er", "on")) == "th, er, on"
    assert format_target_bigrams(()) == ""


def test_build_prompt_v1_messages() -> None:
    messages = build_prompt_v1_messages(("th", "ea", "in", "st"))
    assert len(messages) == 4
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == PROMPT_V1_SYSTEM
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == PROMPT_V1_EXAMPLE_USER
    assert messages[2]["role"] == "assistant"
    assert messages[2]["content"] == PROMPT_V1_EXAMPLE_ASSISTANT
    assert messages[3]["role"] == "user"
    assert "pairs: th, ea, in, st." in messages[3]["content"]


def test_prompt_version_constant() -> None:
    assert PROMPT_VERSION_V1 == "v1"
