"""Unit tests for README claims traceability and honesty constraints (T4.4; §15.3)."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session, col, func, select
from typer.testing import CliRunner

from typist.api.routers.admin import get_word_index
from typist.cli import app
from typist.config import REPO_ROOT, get_settings
from typist.corpus.build import build_corpus
from typist.corpus.word_index import WordIndex
from typist.db import create_db_engine
from typist.main import create_app
from typist.migrations import upgrade_to_head
from typist.models import KeystrokeEvent
from typist.models import Session as TypingSession
from typist.services.analysis import overview_report, participant_results
from typist.services.figures import (
    format_generation_table,
    format_limitations_paragraph,
    format_overhead_line,
)
from typist.services.pipeline_sim import run_pipeline_simulation

runner = CliRunner()


@dataclass
class PilotDbFixture:
    engine: Engine
    db_path: Path
    participant_id: str


@pytest.fixture
def migrated_engine(isolated_settings: Path) -> Iterator[Engine]:
    upgrade_to_head()
    engine = create_db_engine(isolated_settings)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def reference_pilot_db(
    isolated_settings: Path, migrated_engine: Engine, tmp_path: Path
) -> Iterator[PilotDbFixture]:
    corpus_dir = tmp_path / "corpus"
    build_corpus(corpus_dir, word_count=20000, tracked_count=150)
    index = WordIndex.load(corpus_dir)

    fastapi_app = create_app(get_settings())
    fastapi_app.dependency_overrides[get_word_index] = lambda: index
    client = TestClient(fastapi_app)

    result = run_pipeline_simulation(
        client,
        migrated_engine,
        isolated_settings,
        index,
        participant_alias="pilot-builder",
        practice_days=10,
        error_rate=0.05,
        seed=42,
        is_builder=True,
    )
    yield PilotDbFixture(
        engine=migrated_engine,
        db_path=isolated_settings,
        participant_id=result.participant_id,
    )


def test_readme_file_exists() -> None:
    readme_path = REPO_ROOT / "README.md"
    assert readme_path.is_file()


def test_readme_four_elements_present() -> None:
    readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    # Section 15.3 item 1: Chart
    assert "docs/figures/set_error_rate_change.png" in readme_text
    # Section 15.3 item 2: Generation summary table header
    assert "| Arm | Drills | Mean Density | Real-Word Ratio | Acceptance Rate |" in readme_text
    # Section 15.3 item 3: Overhead line prefix
    assert "Instrumentation overhead: handler p95 =" in readme_text
    # Section 15.3 item 4: Limitations paragraph prefix
    assert "This pilot reports findings from N = 1 participant (builder, unblinded)" in readme_text


def test_readme_honesty_rules_and_exclusions() -> None:
    readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/analysis-plan.md" in readme_text
    assert "builder, unblinded" in readme_text or "unblinded" in readme_text

    forbidden = ["webassembly", "wasm", "statistically significant", "p-value", "p < 0.05"]
    for term in forbidden:
        assert term not in readme_text.lower(), f"Forbidden term {term!r} found in README"


def test_readme_claims_trace_to_database(reference_pilot_db: PilotDbFixture) -> None:
    readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    with Session(reference_pilot_db.engine) as session:
        overview = overview_report(session)
        results = participant_results(session, reference_pilot_db.participant_id)

        # Total keystrokes and sessions count
        keystroke_count = session.exec(select(func.count()).select_from(KeystrokeEvent)).one()
        completed_sessions = session.exec(
            select(func.count())
            .select_from(TypingSession)
            .where(col(TypingSession.status) == "completed")
        ).one()

        assert f"{keystroke_count:,}" in readme_text or str(keystroke_count) in readme_text
        assert f"{completed_sessions} completed sessions" in readme_text

        # Generation table
        gen_table = format_generation_table(overview)
        for line in gen_table.strip().splitlines():
            assert line.strip() in readme_text, f"Missing generation table line: {line}"

        # Overhead line
        overhead_line = format_overhead_line(overview)
        assert overhead_line in readme_text, f"Missing overhead line: {overhead_line}"

        # Limitations paragraph
        limitations = format_limitations_paragraph(session, overview)
        assert limitations in readme_text, f"Missing limitations paragraph: {limitations}"

        # Per-set baseline/retest counts and error rate changes
        for s in results.sets:
            base_str = f"{s.baseline_errors}/{s.baseline_attempts}"
            ret_str = f"{s.retest_errors}/{s.retest_attempts}"
            assert base_str in readme_text, f"Missing base counts: {base_str}"
            assert ret_str in readme_text, f"Missing ret counts: {ret_str}"
            if s.error_rate_change is not None:
                chg_str = f"{s.error_rate_change * 100:+.2f}%"
                assert chg_str in readme_text, f"Missing error rate change: {chg_str}"


def test_cli_check_readme_success(reference_pilot_db: PilotDbFixture) -> None:
    res = runner.invoke(app, ["check-readme", "--pid", reference_pilot_db.participant_id])
    assert res.exit_code == 0, f"check-readme failed: {res.output}"
    assert "README claims check passed" in res.output


def test_cli_check_readme_detects_tampering(
    reference_pilot_db: PilotDbFixture, tmp_path: Path
) -> None:
    readme_path = REPO_ROOT / "README.md"
    original_text = readme_path.read_text(encoding="utf-8")

    import re

    tampered_file = tmp_path / "TAMPERED_README.md"
    # Tamper by changing keystroke count in limitations paragraph
    tampered_text = re.sub(r"\d[\d,]+ total keystrokes", "99,999 total keystrokes", original_text)
    tampered_file.write_text(tampered_text, encoding="utf-8")

    res = runner.invoke(
        app,
        [
            "check-readme",
            "--readme",
            str(tampered_file),
            "--pid",
            reference_pilot_db.participant_id,
        ],
    )
    assert res.exit_code == 1
    assert "FAIL" in res.output
