"""typist assign --pid: wiring, the seeded summary line, and the not-found error path (T2.2)."""

import json
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, col, select
from test_assignment_service import PID, WORDS, _seed_baseline
from typer.testing import CliRunner

from typist.cli import app
from typist.models import BigramAssignment
from typist.models import Session as TypingSession  # noqa: F401  (ensures models import)

runner = CliRunner()


def _write_corpus(corpus_dir: Path) -> None:
    corpus_dir.mkdir(parents=True, exist_ok=True)
    (corpus_dir / "words.json").write_text(
        json.dumps({"words": [[word, 1.0] for word in WORDS]}), encoding="utf-8"
    )
    (corpus_dir / "top_bigrams.json").write_text(
        json.dumps({"bigrams": [[word, 1] for word in WORDS]}), encoding="utf-8"
    )


def test_assign_cli_freezes_and_prints_the_summary(
    migrated_engine: Engine, isolated_settings: Path, tmp_path: Path
) -> None:
    _write_corpus(tmp_path / "corpus")
    with Session(migrated_engine) as session:
        _seed_baseline(session, PID)
        session.commit()
    result = runner.invoke(app, ["assign", "--pid", PID])
    assert result.exit_code == 0, result.output
    assert "16 bigrams frozen" in result.output
    assert "A->markov" in result.output
    with Session(migrated_engine) as session:
        rows = session.exec(
            select(BigramAssignment).where(col(BigramAssignment.participant_id) == PID)
        ).all()
    assert len(rows) == 16


def test_assign_cli_unknown_participant_exits_1(
    migrated_engine: Engine, isolated_settings: Path, tmp_path: Path
) -> None:
    _write_corpus(tmp_path / "corpus")
    result = runner.invoke(app, ["assign", "--pid", "nope"])
    assert result.exit_code == 1
    assert "no participant" in result.output
