"""Prompt v1 templates and message construction for Arm.LLM (design doc 13.5).

Constructs the chat-formatted messages for Prompt v1 with few-shot example turn:
- System message specifying lowercase English words with single spaces and no punctuation.
- User few-shot turn requesting words containing 'ck, ow'.
- Assistant few-shot turn demonstrating the output without punctuation.
- User turn interpolating the drill's target bigrams separated by comma-space.
"""

from collections.abc import Sequence
from typing import Final

PROMPT_VERSION_V1: Final[str] = "v1"

PROMPT_V1_SYSTEM: Final[str] = (
    "You write typing practice text. Reply with one line of lowercase English words "
    "separated by single spaces. No punctuation, numbers, quotes or explanations."
)

PROMPT_V1_EXAMPLE_USER: Final[str] = (
    "Write 60 common English words. Many words must contain these letter pairs: ck, ow. "
    "Each pair should appear at least 3 times. Real words only."
)

PROMPT_V1_EXAMPLE_ASSISTANT: Final[str] = (
    "back know clock snow check brown quick below track show neck grow"
)

PROMPT_V1_USER_TEMPLATE: Final[str] = (
    "Write 60 common English words. Many words must contain these letter pairs: {bigrams}. "
    "Each pair should appear at least 3 times. Real words only."
)


def format_target_bigrams(target_bigrams: Sequence[str]) -> str:
    """Format target bigrams as comma-space separated string (owner answer 4)."""
    return ", ".join(target_bigrams)


def build_prompt_v1_messages(target_bigrams: Sequence[str]) -> list[dict[str, str]]:
    """Build the 4-message Prompt v1 payload for chat-templated models."""
    formatted = format_target_bigrams(target_bigrams)
    user_content = PROMPT_V1_USER_TEMPLATE.format(bigrams=formatted)
    return [
        {"role": "system", "content": PROMPT_V1_SYSTEM},
        {"role": "user", "content": PROMPT_V1_EXAMPLE_USER},
        {"role": "assistant", "content": PROMPT_V1_EXAMPLE_ASSISTANT},
        {"role": "user", "content": user_content},
    ]
