"""Prompt v1 templates and message construction for Arm.LLM (design doc 13.5).

Constructs the chat-formatted messages for Prompt v1 with few-shot example turn:
- System message specifying lowercase English words with single spaces and no punctuation.
- User few-shot turn requesting words containing 'ck, ow'.
- Assistant few-shot turn demonstrating the output without punctuation.
- User turn interpolating the drill's target bigrams separated by comma-space.
"""

from collections.abc import Mapping, Sequence
from typing import Final

PROMPT_VERSION_V1: Final[str] = "v1"

PROMPT_V1_SYSTEM: Final[str] = (
    "You write typing practice passages. Reply with one continuous paragraph of 60 to 66 "
    "lowercase English words separated by single spaces. Weave the provided keywords in the "
    "exact order given using short two or three letter connector words, never repeat any word "
    "more than twice, and output no punctuation, numbers, or quotes."
)

PROMPT_V1_EXAMPLE_USER: Final[str] = (
    "Write 62 common English words as natural connected phrases. Many words must contain "
    "these letter pairs: ea, st, ch, nd. Weave at least the first 28 of these keywords in "
    "order — early, coast, beach, wind, clean, stay, watch, sand, reach, stone, march, "
    "sound, steam, fast, rich, pond, clear, rest, porch, find, ocean, storm, lunch, land, "
    "leaf, west, much, hand, peak, best, each, kind, near, past, such, mind. Avoid repeating "
    "articles like the or a. Real words only."
)

PROMPT_V1_EXAMPLE_ASSISTANT: Final[str] = (
    "early birds by our coast cross one beach in cool wind to clean and stay or watch wet "
    "sand reach dark stone as we march at low sound near hot steam so fast into rich grass "
    "by my pond under clear sky for rest on this porch to find wide ocean storm clouds "
    "before lunch on dry land with green leaf buds out west and much warm hand work up high"
)

PROMPT_V1_USER_TEMPLATE: Final[str] = (
    "Write 62 common English words as natural connected phrases. Many words must contain "
    "these letter pairs: {bigrams}. You must include at least 3 words containing each pair.{hints} "
    "Avoid repeating articles like the or a. Real words only."
)


def format_target_bigrams(target_bigrams: Sequence[str]) -> str:
    """Format target bigrams as comma-space separated string (owner answer 4)."""
    return ", ".join(target_bigrams)


def _interleave_hints(
    target_bigrams: Sequence[str],
    bigram_word_hints: Mapping[str, Sequence[str]],
) -> list[str]:
    """Interleave hint words round-robin across target bigrams so truncation stays balanced."""
    lists = [list(words) for bg in target_bigrams if (words := bigram_word_hints.get(bg))]
    if not lists:
        return []
    max_len = max(len(lst) for lst in lists)
    interleaved: list[str] = []
    for idx in range(max_len):
        for lst in lists:
            if idx < len(lst):
                interleaved.append(lst[idx])
    return interleaved


def build_prompt_v1_messages(
    target_bigrams: Sequence[str],
    *,
    bigram_word_hints: Mapping[str, Sequence[str]] | None = None,
) -> list[dict[str, str]]:
    """Build the 4-message Prompt v1 payload for chat-templated models."""
    formatted = format_target_bigrams(target_bigrams)
    hint_clause = ""
    if bigram_word_hints:
        interleaved = _interleave_hints(target_bigrams, bigram_word_hints)
        if interleaved:
            min_keep = min(len(interleaved), max(16, 8 * len(target_bigrams)))
            hint_clause = (
                f" Weave at least the first {min_keep} of these keywords in order — "
                + ", ".join(interleaved)
                + "."
            )
    user_content = PROMPT_V1_USER_TEMPLATE.format(bigrams=formatted, hints=hint_clause)
    return [
        {"role": "system", "content": PROMPT_V1_SYSTEM},
        {"role": "user", "content": PROMPT_V1_EXAMPLE_USER},
        {"role": "assistant", "content": PROMPT_V1_EXAMPLE_ASSISTANT},
        {"role": "user", "content": user_content},
    ]
