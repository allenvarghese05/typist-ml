"""Model integration test with real MLXRuntime on Apple Silicon (CLAUDE.md; T3.2).

Marked with @pytest.mark.mlx and skips automatically off Apple Silicon or when the model
snapshot is not in the local cache.
"""

import pytest

from typist.generation.llm import (
    DEFAULT_MODEL_ID,
    DEFAULT_MODEL_REVISION,
    MLXRuntime,
    is_apple_silicon,
    is_model_cached,
)


@pytest.mark.mlx
def test_real_mlx_runtime_completion() -> None:
    if not is_apple_silicon():
        pytest.skip("needs Apple Silicon")
    if not is_model_cached(DEFAULT_MODEL_ID, DEFAULT_MODEL_REVISION):
        pytest.skip("model snapshot not cached; run `just mlx-smoke --download` once")

    runtime = MLXRuntime(model_id=DEFAULT_MODEL_ID, revision=DEFAULT_MODEL_REVISION)
    messages = [
        {"role": "system", "content": "Reply with three common english words separated by space."},
        {"role": "user", "content": "hello"},
    ]
    out = runtime.complete(messages, max_tokens=20, seed=42)

    assert out.text != ""
    assert out.tokens > 0
    assert out.tokens_per_sec > 0.0
    assert out.peak_memory_mb > 100.0
    assert out.gen_ms > 0.0
