"""Unit tests for LLM runtime abstractions, FakeLLMRuntime, and import safety (T3.2)."""

import sys
from unittest.mock import patch

import pytest

from typist.generation.llm.runtime import (
    FakeLLMRuntime,
    LLMOutput,
    LLMRuntimeProtocol,
    MLXRuntime,
    ModelNotDownloadedError,
    gb_to_mb,
)


def test_runtime_module_import_does_not_import_mlx() -> None:
    loaded_mlx = [
        m for m in sys.modules if m in {"mlx", "mlx_lm"} or m.startswith(("mlx.", "mlx_lm."))
    ]
    assert loaded_mlx == []


def test_gb_to_mb() -> None:
    assert gb_to_mb(0.8123) == 812.3
    assert gb_to_mb(1.5) == 1500.0


def test_fake_runtime_implements_protocol() -> None:
    fake = FakeLLMRuntime(canned_text="hello world")
    assert isinstance(fake, LLMRuntimeProtocol)

    output = fake.complete([{"role": "user", "content": "hi"}], seed=42)
    assert isinstance(output, LLMOutput)
    assert output.text == "hello world"
    assert output.tokens == 2
    assert output.tokens_per_sec == 45.0
    assert output.peak_memory_mb == 850.0
    assert output.gen_ms == 50.0
    assert len(fake.calls) == 1
    assert fake.calls[0]["seed"] == 42


def test_fake_runtime_canned_queue() -> None:
    out1 = LLMOutput(text="first", tokens=1, tokens_per_sec=40.0, peak_memory_mb=800.0, gen_ms=30.0)
    out2 = LLMOutput(text="second", tokens=1, tokens_per_sec=42.0, peak_memory_mb=810.0, gen_ms=32.0)
    fake = FakeLLMRuntime(canned_outputs=[out1, out2])

    assert fake.complete([], seed=1).text == "first"
    assert fake.complete([], seed=2).text == "second"


def test_mlx_runtime_fails_on_non_mac(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="requires macOS on Apple Silicon"):
        MLXRuntime()


def test_mlx_runtime_missing_snapshot_raises_model_not_downloaded_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    with patch(
        "typist.generation.llm.runtime.resolve_model_snapshot",
        side_effect=ModelNotDownloadedError("not found"),
    ):
        with pytest.raises(ModelNotDownloadedError):
            MLXRuntime()
