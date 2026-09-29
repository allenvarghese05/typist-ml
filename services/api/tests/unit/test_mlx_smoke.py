"""Tests for scripts/mlx_smoke.py (T0.5) that need no model and never import mlx.

The script is loaded from its path because services/api/scripts is not a package. The real model
run is owner-run on the MacBook (`just mlx-smoke`); these tests cover the pure parts, with a fake
generate function in place of the model (CLAUDE.md: tests use a fake runtime).
"""

import importlib.metadata
import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "mlx_smoke.py"
SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER_MODEL = "mlx-community/Qwen3-1.7B-4bit"


def mlx_modules() -> list[str]:
    """Names of loaded modules that belong to mlx or mlx-lm."""
    return sorted(
        name
        for name in sys.modules
        if name in {"mlx", "mlx_lm"} or name.startswith(("mlx.", "mlx_lm."))
    )


@pytest.fixture(scope="module")
def smoke() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mlx_smoke", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["mlx_smoke"] = module  # dataclasses look up their module here
    spec.loader.exec_module(module)
    return module


def sample(a: int, *, b: str = "x") -> None:
    """Signature fixture for test_signature_line."""


def test_loading_the_script_does_not_import_mlx(smoke: ModuleType) -> None:
    assert smoke.DEFAULT_MODEL_ID
    assert mlx_modules() == []


def test_api_and_cli_do_not_import_mlx() -> None:
    from typist import cli, main

    assert cli.app is not None
    assert main.create_app is not None
    assert mlx_modules() == []


def test_settings_match_the_design_doc_and_owner_answers(smoke: ModuleType) -> None:
    assert smoke.DEFAULT_MODEL_ID == "mlx-community/Llama-3.2-1B-Instruct-4bit"
    assert (smoke.TEMP, smoke.TOP_P, smoke.MAX_TOKENS, smoke.DEFAULT_SEED) == (0.8, 0.9, 40, 0)
    assert smoke.API_NAMES == (
        "mlx.core.random.seed",
        "mlx_lm.load",
        "mlx_lm.stream_generate",
        "mlx_lm.sample_utils.make_sampler",
    )
    assert smoke.RESPONSE_FIELDS == ("text", "generation_tokens", "generation_tps", "peak_memory")


def test_parse_args_defaults(smoke: ModuleType) -> None:
    args = smoke.parse_args(["--revision", SHA])
    assert args == smoke.SmokeArgs(
        model="mlx-community/Llama-3.2-1B-Instruct-4bit", revision=SHA, seed=0, download=False
    )


def test_parse_args_download_and_seed(smoke: ModuleType) -> None:
    args = smoke.parse_args(["--revision", SHA, "--seed", "7", "--download"])
    assert (args.seed, args.download) == (7, True)


@pytest.mark.parametrize("revision", ["main", "0123abc", "<NOT_A_SHA>", SHA.upper()])
def test_parse_args_rejects_a_revision_that_is_not_a_full_commit_sha(
    smoke: ModuleType, revision: str
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        smoke.parse_args(["--revision", revision])
    assert excinfo.value.code == 2


def test_parse_args_rejects_a_negative_seed(smoke: ModuleType) -> None:
    with pytest.raises(SystemExit) as excinfo:
        smoke.parse_args(["--revision", SHA, "--seed", "-1"])
    assert excinfo.value.code == 2


def test_parse_args_needs_a_revision_for_another_model(smoke: ModuleType) -> None:
    with pytest.raises(SystemExit) as excinfo:
        smoke.parse_args(["--model", OTHER_MODEL])
    assert excinfo.value.code == 2


def test_parse_args_accepts_another_model_with_a_revision(smoke: ModuleType) -> None:
    args = smoke.parse_args(["--model", OTHER_MODEL, "--revision", SHA])
    assert (args.model, args.revision) == (OTHER_MODEL, SHA)


@pytest.mark.parametrize(("offline", "expected"), [(True, "1"), (False, "0")])
def test_configure_hub_env(
    smoke: ModuleType, monkeypatch: pytest.MonkeyPatch, offline: bool, expected: str
) -> None:
    monkeypatch.setenv("HF_HUB_OFFLINE", "set-by-test")
    monkeypatch.setenv("HF_HUB_DISABLE_TELEMETRY", "set-by-test")
    smoke.configure_hub_env(offline=offline)
    assert os.environ["HF_HUB_OFFLINE"] == expected
    assert os.environ["HF_HUB_DISABLE_TELEMETRY"] == "1"


def test_installed_version(smoke: ModuleType) -> None:
    assert smoke.installed_version("pytest") == importlib.metadata.version("pytest")
    assert smoke.installed_version("no-such-distribution-t05") == "none"


def test_version_lines(smoke: ModuleType) -> None:
    lines = smoke.version_lines()
    assert lines[0].startswith("VERSION python 3.12.")
    assert lines[1].startswith("VERSION macos ")
    assert [line.split(" ")[1] for line in lines[2:]] == [
        "mlx-lm",
        "mlx",
        "mlx-metal",
        "transformers",
        "huggingface-hub",
    ]
    assert all(len(line.split(" ")) == 3 for line in lines)


def test_signature_line(smoke: ModuleType) -> None:
    assert smoke.signature_line("sample", sample) == (
        "SIGNATURE sample (a: int, *, b: str = 'x') -> None"
    )
    assert smoke.signature_line("number", 42) == "SIGNATURE number unavailable"


def test_gb_to_mb(smoke: ModuleType) -> None:
    assert smoke.gb_to_mb(0.8123) == 812.3
    assert smoke.gb_to_mb(0.0) == 0.0


@pytest.mark.parametrize(
    ("texts", "same"), [(("a b c", "a b c"), True), (("a b c", "a b d"), False)]
)
def test_run_twice_uses_the_callers_seed_and_compares_text(
    smoke: ModuleType, texts: tuple[str, str], same: bool
) -> None:
    seeds: list[int] = []

    def fake_generate(seed: int) -> object:  # stands in for the mlx-lm model
        seeds.append(seed)
        return smoke.GenerationResult(
            text=texts[len(seeds) - 1], tokens=5, tokens_per_sec=50.0, peak_memory_mb=800.0
        )

    report = smoke.run_twice(fake_generate, 7)
    assert seeds == [7, 7]
    assert [run.text for run in report.runs] == list(texts)
    assert report.same_text is same


def test_format_report(smoke: ModuleType) -> None:
    first = smoke.GenerationResult(
        text="the quick brown fox", tokens=12, tokens_per_sec=101.54, peak_memory_mb=812.3
    )
    second = smoke.GenerationResult(
        text="line one\nline two", tokens=40, tokens_per_sec=120.0, peak_memory_mb=815.0
    )
    report = smoke.SmokeReport(runs=(first, second), same_text=False)
    assert smoke.format_report(report, 3) == [
        "RUN 1 seed=3 tokens=12 tokens_per_sec=101.5 peak_memory_mb=812.3",
        'TEXT 1 "the quick brown fox"',
        "RUN 2 seed=3 tokens=40 tokens_per_sec=120.0 peak_memory_mb=815.0",
        'TEXT 2 "line one\\nline two"',
        "SAME_TEXT no",
    ]


def test_main_refuses_off_apple_silicon(
    smoke: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    assert smoke.main(["--revision", SHA]) == 2
    assert "needs macOS on Apple Silicon" in capsys.readouterr().out
    assert "HF_HUB_OFFLINE" not in os.environ
    assert mlx_modules() == []
