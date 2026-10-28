"""Model runtime protocol and MLX implementation for Arm.LLM (design doc 13.5; D09, D23).

Provides:
- LLMOutput: dataclass holding completion text and audit metrics (tokens, tokens_per_sec,
  peak_memory_mb, gen_ms).
- LLMRuntimeProtocol: protocol required by LLMGenerator.
- MLXRuntime: loads local Apple Silicon model snapshot offline via mlx-lm with lazy dynamic
  imports to preserve Linux CI compatibility.
- FakeLLMRuntime: configurable test runtime that generates deterministic outputs without models.
"""

import importlib
import os
import platform
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

DEFAULT_MODEL_ID = "mlx-community/Llama-3.2-1B-Instruct-4bit"
DEFAULT_MODEL_REVISION = "08231374eeacb049a0eade7922910865b8fce912"


class ModelNotDownloadedError(RuntimeError):
    """Raised when the requested model snapshot is missing from the local Hugging Face cache."""


@dataclass(frozen=True)
class LLMOutput:
    """Result of one model completion call with performance metrics."""

    text: str
    tokens: int
    tokens_per_sec: float
    peak_memory_mb: float
    gen_ms: float = 0.0


@runtime_checkable
class LLMRuntimeProtocol(Protocol):
    """Contract for LLM execution wrappers."""

    def complete(
        self,
        messages: Sequence[dict[str, str]],
        *,
        max_tokens: int = 160,
        temp: float = 0.8,
        top_p: float = 0.9,
        seed: int = 0,
    ) -> LLMOutput: ...


def is_apple_silicon() -> bool:
    """Return True if running on macOS on Apple Silicon (arm64)."""
    return sys.platform == "darwin" and platform.machine() == "arm64"


def configure_hub_env(*, offline: bool = True) -> None:
    """Configure Hugging Face Hub environment variables (D23)."""
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1" if offline else "0"


def gb_to_mb(gb: float) -> float:
    """Convert peak memory from GB to MB (GB * 1000.0), rounded to 1 decimal place."""
    return round(gb * 1000.0, 1)


def resolve_model_snapshot(model_id: str, revision: str) -> Path:
    """Resolve local cache snapshot path; raises ModelNotDownloadedError if not present."""
    configure_hub_env(offline=True)
    try:
        hub: Any = importlib.import_module("huggingface_hub")
        snapshot_download = hub.snapshot_download
    except ImportError as exc:
        raise RuntimeError("huggingface_hub is not installed; run with --extra mlx") from exc
    try:
        path = snapshot_download(
            repo_id=model_id,
            revision=revision,
            local_files_only=True,
        )
    except OSError as exc:
        raise ModelNotDownloadedError(
            f"model {model_id} at revision {revision} is not in the Hugging Face cache. "
            "Run `just mlx-smoke --download` once to fetch it."
        ) from exc
    return Path(path)


def is_model_cached(model_id: str, revision: str) -> bool:
    """Return True if the model snapshot exists in the local Hugging Face cache."""
    try:
        resolve_model_snapshot(model_id, revision)
        return True
    except (ModelNotDownloadedError, RuntimeError):
        return False


class MLXRuntime:
    """Apple Silicon neural generation runtime using mlx-lm."""

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        revision: str = DEFAULT_MODEL_REVISION,
    ) -> None:
        if not is_apple_silicon():
            raise RuntimeError("MLXRuntime requires macOS on Apple Silicon (arm64)")
        configure_hub_env(offline=True)
        self.model_id = model_id
        self.revision = revision
        self.model_dir = resolve_model_snapshot(model_id, revision)

        mlx_lm: Any = importlib.import_module("mlx_lm")
        self._model, self._tokenizer = mlx_lm.load(str(self.model_dir))

    def complete(
        self,
        messages: Sequence[dict[str, str]],
        *,
        max_tokens: int = 160,
        temp: float = 0.8,
        top_p: float = 0.9,
        seed: int = 0,
    ) -> LLMOutput:
        mx: Any = importlib.import_module("mlx.core")
        mlx_lm: Any = importlib.import_module("mlx_lm")
        sample_utils: Any = importlib.import_module("mlx_lm.sample_utils")

        mx.random.seed(seed)
        prompt = self._tokenizer.apply_chat_template(
            list(messages), add_generation_prompt=True, tokenize=False
        )
        sampler = sample_utils.make_sampler(temp=temp, top_p=top_p)

        start_time = time.perf_counter()
        text = ""
        last: Any = None
        for resp in mlx_lm.stream_generate(
            self._model, self._tokenizer, prompt, max_tokens=max_tokens, sampler=sampler
        ):
            text += resp.text
            last = resp
        elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        if last is None:
            return LLMOutput(
                text="",
                tokens=0,
                tokens_per_sec=0.0,
                peak_memory_mb=0.0,
                gen_ms=elapsed_ms,
            )

        return LLMOutput(
            text=text,
            tokens=int(last.generation_tokens),
            tokens_per_sec=round(float(last.generation_tps), 1),
            peak_memory_mb=gb_to_mb(float(last.peak_memory)),
            gen_ms=elapsed_ms,
        )


class FakeLLMRuntime:
    """Test runtime that emits canned or seeded outputs without models or MLX."""

    def __init__(
        self,
        canned_outputs: Sequence[LLMOutput] | None = None,
        canned_text: str | None = None,
        tokens_per_sec: float = 45.0,
        peak_memory_mb: float = 850.0,
    ) -> None:
        self._canned_outputs = list(canned_outputs) if canned_outputs is not None else None
        self._canned_text = canned_text
        self._tokens_per_sec = tokens_per_sec
        self._peak_memory_mb = peak_memory_mb
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        messages: Sequence[dict[str, str]],
        *,
        max_tokens: int = 160,
        temp: float = 0.8,
        top_p: float = 0.9,
        seed: int = 0,
    ) -> LLMOutput:
        self.calls.append(
            {
                "messages": messages,
                "max_tokens": max_tokens,
                "temp": temp,
                "top_p": top_p,
                "seed": seed,
            }
        )
        if self._canned_outputs:
            return self._canned_outputs.pop(0)
        text = (
            self._canned_text if self._canned_text is not None else f"fake output for seed {seed}"
        )
        tokens = min(max_tokens, len(text.split()))
        return LLMOutput(
            text=text,
            tokens=tokens,
            tokens_per_sec=self._tokens_per_sec,
            peak_memory_mb=self._peak_memory_mb,
            gen_ms=50.0,
        )
