"""The LLM drill generator: on-device neural language model generation (design doc 13.5).

LLMGenerator implements Arm.LLM (D03). Given a DrillSpec, it:
1. Constructs Prompt v1 messages interpolating spec.target_bigrams.
2. Invokes LLMRuntimeProtocol.complete() deterministically with spec.seed.
3. Post-processes output via clean_llm_output() (lowercased, non-letters replaced by spaces,
   collapsed spaces, word-boundary truncation <= spec.length_chars).
4. Emits a DrillCandidate populating raw_output, clean text, generator_version, seed,
   model_id, prompt_version, gen_ms, gen_tokens, tokens_per_sec, and peak_memory_mb.
"""

import random
from typing import Final

from typist.corpus.word_index import WordIndex
from typist.generation.base import Arm, DrillCandidate, DrillSpec
from typist.generation.llm.postprocess import clean_llm_output
from typist.generation.llm.prompt import PROMPT_VERSION_V1, build_prompt_v1_messages
from typist.generation.llm.runtime import DEFAULT_MODEL_ID, LLMRuntimeProtocol
from typist.generation.validator import ValidatorConfig

_VERSION: Final[str] = "llm-v1"

_BLOCKED_WORDS: Final[frozenset[str]] = frozenset(
    {
        "asshole",
        "assholes",
        "bitch",
        "bitches",
        "cock",
        "cocks",
        "cunt",
        "cunts",
        "dick",
        "dicks",
        "douche",
        "fuck",
        "fucker",
        "fuckers",
        "fucking",
        "fuckin",
        "nigger",
        "niggers",
        "nigga",
        "piss",
        "shit",
        "shits",
        "shitter",
        "slut",
        "sluts",
        "whore",
        "whores",
    }
)


def _is_clean_hint_word(word: str) -> bool:
    """Filter out profanity / vulgarities so RLHF models do not trigger safety truncation."""
    low = word.lower()
    if any(low.startswith(prefix) for prefix in ("fuck", "shit", "bitch", "cunt", "nigg")):
        return False
    return low not in _BLOCKED_WORDS


class LLMGenerator:
    """The 13.5 neural language model drill generator for Arm.LLM."""

    arm = Arm.LLM
    version = _VERSION

    def __init__(
        self,
        index: WordIndex,
        config: ValidatorConfig,
        runtime: LLMRuntimeProtocol,
        model_id: str = DEFAULT_MODEL_ID,
        prompt_version: str = PROMPT_VERSION_V1,
        temperature: float = 0.8,
        top_p: float = 0.9,
        max_tokens: int = 180,
    ) -> None:
        self._index = index
        self._config = config
        self._runtime = runtime
        self._model_id = model_id
        self._prompt_version = prompt_version
        self._temperature = temperature
        self._top_p = top_p
        self._max_tokens = max_tokens

    def _sample_bigram_hints(self, spec: DrillSpec) -> dict[str, tuple[str, ...]]:
        """Sample up to 10 compact dictionary words per target bigram using spec.seed."""
        rng = random.Random(spec.seed)
        hints: dict[str, tuple[str, ...]] = {}
        used: set[str] = set()
        for bigram in spec.target_bigrams:
            pool = [
                w
                for w in self._index.words_containing(bigram)[:60]
                if 3 <= len(w) <= 7 and w not in used and _is_clean_hint_word(w)
            ]
            if len(pool) < 10:
                pool = [
                    w
                    for w in self._index.words_containing(bigram)[:120]
                    if 3 <= len(w) <= 8 and w not in used and _is_clean_hint_word(w)
                ]
            if not pool:
                continue
            k = min(10, len(pool))
            chosen = tuple(rng.sample(pool, k))
            used.update(chosen)
            hints[bigram] = chosen
        return hints

    def generate(self, spec: DrillSpec) -> DrillCandidate:
        """Generate one LLM candidate drill deterministically for spec.seed."""
        hints = self._sample_bigram_hints(spec)
        messages = build_prompt_v1_messages(spec.target_bigrams, bigram_word_hints=hints)
        output = self._runtime.complete(
            messages,
            max_tokens=self._max_tokens,
            temp=self._temperature,
            top_p=self._top_p,
            seed=spec.seed,
        )
        cleaned_text = clean_llm_output(output.text, max_chars=spec.length_chars)
        return DrillCandidate(
            text=cleaned_text,
            raw_output=output.text,
            generator_version=self.version,
            seed=spec.seed,
            model_id=self._model_id,
            prompt_version=self._prompt_version,
            gen_ms=output.gen_ms,
            gen_tokens=output.tokens,
            tokens_per_sec=output.tokens_per_sec,
            peak_memory_mb=output.peak_memory_mb,
        )
