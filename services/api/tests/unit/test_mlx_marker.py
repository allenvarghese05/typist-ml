"""The mlx marker: tests that load a model run only on Apple Silicon (CLAUDE.md)."""

import platform
import sys
from pathlib import Path

import pytest

CONFTEST = Path(__file__).resolve().parents[1] / "conftest.py"
MLX_TEST = """
import pytest


@pytest.mark.mlx
def test_needs_model():
    assert True
"""


def test_mlx_tests_are_skipped_off_apple_silicon(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    pytester.makeconftest(CONFTEST.read_text())
    pytester.makepyfile(test_model=MLX_TEST)
    result = pytester.runpytest_inprocess("--strict-markers", "-rs")
    result.assert_outcomes(skipped=1)
    result.stdout.fnmatch_lines(["*needs mlx-lm on Apple Silicon*"])


def test_mlx_tests_run_on_apple_silicon(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(platform, "machine", lambda: "arm64")
    pytester.makeconftest(CONFTEST.read_text())
    pytester.makepyfile(test_model=MLX_TEST)
    result = pytester.runpytest_inprocess("--strict-markers")
    result.assert_outcomes(passed=1)
