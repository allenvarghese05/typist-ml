"""Unit tests for README claims traceability and honesty constraints (T4.4; §15.3)."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session
from typer.testing import CliRunner

from typist.api.routers.admin import get_word_index
from typist.cli import app
from typist.config import REPO_ROOT, get_settings
from typist.corpus.build import build_corpus
from typist.corpus.word_index import WordIndex
from typist.db import create_db_engine
from typist.generation.llm.runtime import LLMOutput
from typist.main import create_app
from typist.migrations import upgrade_to_head
from typist.services.analysis import overview_report, participant_results
from typist.services.figures import (
    format_generation_table,
    format_limitations_paragraph,
    format_overhead_line,
    generate_all_figures,
)
from typist.services.pipeline_sim import run_pipeline_simulation

runner = CliRunner()


class _CorpusBackedFakeLLMRuntime:
    """Deterministic pure-Python LLMRuntimeProtocol producing valid drills for any target set."""

    def __init__(self, index: WordIndex) -> None:
        self._index = index

    def complete(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        max_tokens: int = 180,
        temp: float = 0.8,
        top_p: float = 0.9,
        seed: int = 0,
    ) -> LLMOutput:
        _ = (max_tokens, temp, top_p)
        user_msg = messages[-1]["content"]
        match = re.search(r"pairs:\s*([a-z,\s]+)\.", user_msg)
        bigrams = [b.strip() for b in match.group(1).split(",")] if match else ["th", "er"]

        words: list[str] = []
        used: dict[str, int] = {}
        for round_idx in range(6):
            for bg in bigrams:
                candidates = [w for w in self._index.words_containing(bg)[:80] if 3 <= len(w) <= 6]
                for cand in candidates[(seed + round_idx) % max(1, len(candidates)) :] + candidates:
                    if used.get(cand, 0) < 2:
                        words.append(cand)
                        used[cand] = used.get(cand, 0) + 1
                        break

        fillers = [
            "in",
            "on",
            "by",
            "at",
            "to",
            "up",
            "we",
            "go",
            "so",
            "as",
            "or",
            "my",
            "now",
            "day",
            "sun",
            "sky",
            "way",
            "map",
            "air",
            "sea",
            "oak",
            "bay",
            "row",
            "box",
        ]
        f_idx = 0
        while len(" ".join(words)) < 278:
            filler = fillers[f_idx % len(fillers)]
            f_idx += 1
            if used.get(filler, 0) < 2:
                words.append(filler)
                used[filler] = used.get(filler, 0) + 1

        text = " ".join(words)
        while len(text) > 298 and len(words) > 10:
            words.pop()
            text = " ".join(words)

        return LLMOutput(
            text=text,
            tokens=64,
            tokens_per_sec=145.0,
            peak_memory_mb=910.0,
            gen_ms=441.4,
        )


@pytest.fixture
def migrated_engine(isolated_settings: Path) -> Iterator[Engine]:
    upgrade_to_head()
    engine = create_db_engine(isolated_settings)
    try:
        yield engine
    finally:
        engine.dispose()


def test_readme_file_exists() -> None:
    assert (REPO_ROOT / "README.md").is_file()
    assert (REPO_ROOT / "docs" / "figures" / "validation_audit.json").is_file()


def test_readme_four_elements_present() -> None:
    readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    # Section 15.3 item 1: Chart
    assert "docs/figures/set_error_rate_change.png" in readme_text
    # Section 15.3 item 2: Generation summary table header
    assert "| Arm | Drills | Mean Density | Real-Word Ratio | Acceptance Rate |" in readme_text
    # Section 15.3 item 3: Overhead line prefix
    assert "Instrumentation overhead: handler p95 =" in readme_text
    # Section 15.3 item 4: Honest simulated-data limitations paragraph
    assert "Simulated pipeline validation: all " in readme_text
    assert "typist test-pipeline" in readme_text
    assert "no human participant" in readme_text
    assert "regression to the mean" in readme_text


def test_readme_honesty_rules_and_exclusions() -> None:
    readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/analysis-plan.md" in readme_text
    assert "builder, unblinded" in readme_text

    forbidden = ["webassembly", "wasm", "statistically significant", "p-value", "p < 0.05"]
    for term in forbidden:
        assert term not in readme_text.lower(), f"Forbidden term {term!r} found in README"

    # Prevent CommonMark backslash-punctuation mangling inside GitHub MathJax blocks
    assert re.search(r"\\[,;!{}]", readme_text) is None


def test_readme_claims_trace_to_validation_audit(tmp_path: Path) -> None:
    readme_path = REPO_ROOT / "README.md"
    audit_path = REPO_ROOT / "docs" / "figures" / "validation_audit.json"
    readme_text = readme_path.read_text(encoding="utf-8")
    payload = json.loads(audit_path.read_text(encoding="utf-8"))

    assert payload["is_simulated"] is True
    arms_by_name = {a["arm"]: a for a in payload["arms"]}
    for required_arm in ("control", "heuristic", "markov", "llm"):
        assert required_arm in arms_by_name
        assert arms_by_name[required_arm]["drills_count"] > 0, (
            f"Arm {required_arm} must have generated > 0 drills in validation"
        )
    assert arms_by_name["llm"]["tokens_per_sec"] is not None
    assert arms_by_name["llm"]["tokens_per_sec"] >= 30.0

    assert f"{payload['total_keystrokes']:,}" in readme_text
    assert f"{payload['completed_sessions']} completed sessions" in readme_text

    for line in str(payload["generation_table"]).strip().splitlines():
        assert line.strip() in readme_text, f"Missing generation table line: {line}"

    assert str(payload["overhead_line"]) in readme_text
    assert str(payload["limitations_paragraph"]) in readme_text

    for s in payload["sets"]:
        base_str = f"{s['baseline_errors']}/{s['baseline_attempts']}"
        ret_str = f"{s['retest_errors']}/{s['retest_attempts']}"
        assert base_str in readme_text, f"Missing base counts: {base_str}"
        assert ret_str in readme_text, f"Missing ret counts: {ret_str}"
        if s["error_rate_change"] is not None:
            chg_str = f"{s['error_rate_change'] * 100:+.2f}%"
            assert chg_str in readme_text, f"Missing error rate change: {chg_str}"

    res = runner.invoke(app, ["check-readme", "--audit-json", str(audit_path)])
    assert res.exit_code == 0, f"check-readme failed: {res.output}"
    assert "README claims check passed" in res.output

    tampered_file = tmp_path / "TAMPERED_README.md"
    tampered_text = re.sub(r"\d[\d,]+ total keystrokes", "99,999 total keystrokes", readme_text)
    tampered_file.write_text(tampered_text, encoding="utf-8")
    bad_res = runner.invoke(
        app,
        ["check-readme", "--readme", str(tampered_file), "--audit-json", str(audit_path)],
    )
    assert bad_res.exit_code == 1
    assert "FAIL" in bad_res.output


def test_live_four_arm_simulated_db_check_readme(
    isolated_settings: Path, migrated_engine: Engine, tmp_path: Path
) -> None:
    corpus_dir = tmp_path / "corpus"
    build_corpus(corpus_dir, word_count=8000, tracked_count=100)
    index = WordIndex.load(corpus_dir)

    fastapi_app = create_app(get_settings())
    fastapi_app.dependency_overrides[get_word_index] = lambda: index
    client = TestClient(fastapi_app)

    fake_llm = _CorpusBackedFakeLLMRuntime(index)
    sim = run_pipeline_simulation(
        client,
        migrated_engine,
        isolated_settings,
        index,
        participant_alias="sim-4arm-ci",
        practice_days=2,
        error_rate=0.05,
        seed=42,
        is_builder=True,
        arms_enabled=("control", "heuristic", "markov", "llm"),
        runtime=fake_llm,
    )

    fig_dir = tmp_path / "figs"
    with Session(migrated_engine) as session:
        artifacts = generate_all_figures(
            session,
            out_dir=fig_dir,
            pid=sim.participant_id,
            n_draws=1000,
            n_resamples=100,
        )
        overview = overview_report(session)
        results = participant_results(session, sim.participant_id, n_draws=1000, n_resamples=100)
        gen_table = format_generation_table(overview)
        overhead = format_overhead_line(overview)
        limitations = format_limitations_paragraph(session, overview)

    assert artifacts.validation_audit_path is not None and artifacts.validation_audit_path.is_file()
    assert limitations.startswith("Simulated pipeline validation:")
    assert len(results.sets) == 4
    assert {s.arm for s in results.sets} == {"control", "heuristic", "markov", "llm"}

    set_lines = "\n".join(
        f"- Set {s.set_label} ({s.arm}): {s.baseline_errors}/{s.baseline_attempts} -> {s.retest_errors}/{s.retest_attempts}"
        for s in results.sets
    )
    synth_readme = tmp_path / "SYNTH_README.md"
    synth_readme.write_text(
        "![Chart](docs/figures/set_error_rate_change.png)\n\n"
        f"{set_lines}\n\n"
        f"{gen_table}\n\n"
        f"{overhead}\n\n"
        f"{limitations}\n",
        encoding="utf-8",
    )

    ok_res = runner.invoke(
        app,
        ["check-readme", "--readme", str(synth_readme), "--pid", sim.participant_id],
    )
    assert ok_res.exit_code == 0, f"Live DB check-readme failed: {ok_res.output}"

    bad_readme = tmp_path / "BAD_SYNTH_README.md"
    bad_readme.write_text(
        synth_readme.read_text(encoding="utf-8") + "\nResults are statistically significant.\n",
        encoding="utf-8",
    )
    bad_res = runner.invoke(
        app,
        ["check-readme", "--readme", str(bad_readme), "--pid", sim.participant_id],
    )
    assert bad_res.exit_code == 1
    assert "FAIL" in bad_res.output
