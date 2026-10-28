"""The LLM drill generator: on-device neural language model generation (design doc 13.5).

LLMGenerator implements Arm.LLM (D03). Given a DrillSpec, it:
1. Constructs Prompt v1 messages interpolating spec.target_bigrams.
2. Invokes LLMRuntimeProtocol.complete() deterministically with spec.seed.
3. Post-processes output via clean_llm_output() (lowercased, non-letters replaced by spaces,
   collapsed spaces, word-boundary truncation <= spec.length_chars).
4. Emits a DrillCandidate populating raw_output, clean text, generator_version, seed,
   model_id, prompt_version, gen_ms, gen_tokens, tokens_per_sec, and peak_memory_mb.
"""

from typing import Final

from typist.corpus.word_index import WordIndex
from typist.generation.base import Arm, DrillCandidate, DrillSpec
from typist.generation.llm.postprocess import clean_llm_output
from typist.generation.llm.prompt import PROMPT_VERSION_V1, build_prompt_v1_messages
from typist.generation.llm.runtime import DEFAULT_MODEL_ID, LLMRuntimeProtocol
from typist.generation.validator import ValidatorConfig

_VERSION: Final[str] = "llm-v1"


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
        max_tokens: int = 160,
    ) -> None:
        self._index = index
        self._config = config
        self._runtime = runtime
        self._model_id = model_id
        self._prompt_version = prompt_version
        self._temperature = temperature
        self._top_p = top_p
        self._max_tokens = max_tokens

    def generate(self, spec: DrillSpec) -> DrillCandidate:
        """Generate one LLM candidate drill deterministically for spec.seed."""
        messages = build_prompt_v1_messages(spec.target_bigrams)
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
