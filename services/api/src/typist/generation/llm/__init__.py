"""LLM drill generator package for Arm.LLM (design doc 13.5; T3.2)."""

from typist.generation.llm.generator import LLMGenerator
from typist.generation.llm.postprocess import clean_llm_output
from typist.generation.llm.prompt import (
    PROMPT_VERSION_V1,
    build_prompt_v1_messages,
    format_target_bigrams,
)
from typist.generation.llm.runtime import (
    DEFAULT_MODEL_ID,
    DEFAULT_MODEL_REVISION,
    FakeLLMRuntime,
    LLMOutput,
    LLMRuntimeProtocol,
    MLXRuntime,
    ModelNotDownloadedError,
    configure_hub_env,
    gb_to_mb,
    is_apple_silicon,
    is_model_cached,
    resolve_model_snapshot,
)

__all__ = [
    "DEFAULT_MODEL_ID",
    "DEFAULT_MODEL_REVISION",
    "FakeLLMRuntime",
    "LLMGenerator",
    "LLMOutput",
    "LLMRuntimeProtocol",
    "MLXRuntime",
    "ModelNotDownloadedError",
    "PROMPT_VERSION_V1",
    "build_prompt_v1_messages",
    "clean_llm_output",
    "configure_hub_env",
    "format_target_bigrams",
    "gb_to_mb",
    "is_apple_silicon",
    "is_model_cached",
    "resolve_model_snapshot",
]
