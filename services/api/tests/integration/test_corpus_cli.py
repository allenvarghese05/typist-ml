"""typist corpus build + compose-baseline: the acceptance (coverage + recount), idempotency."""

from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, col, select
from typer.testing import CliRunner

from typist.cli import app
from typist.corpus.word_index import TOP_BIGRAMS_FILENAME, WordIndex
from typist.models import ExperimentConfig, TextPassage

runner = CliRunner()


def _shared_a_texts(engine: Engine) -> list[str]:
    with Session(engine) as session:
        passages = session.exec(
            select(TextPassage)
            .where(
                col(TextPassage.kind) == "baseline",
                col(TextPassage.form) == "A",
                col(TextPassage.participant_id).is_(None),
            )
            .order_by(col(TextPassage.part))
        ).all()
        return [p.text for p in passages]


def _recount(text: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for token in text.split(" "):
        for i in range(len(token) - 1):
            if token[i].isalpha() and token[i + 1].isalpha():
                counts[token[i : i + 2]] += 1
    return dict(counts)


def test_build_then_compose_covers_every_tracked_bigram(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    assert runner.invoke(app, ["corpus", "build"]).exit_code == 0
    assert runner.invoke(app, ["corpus", "compose-baseline"]).exit_code == 0

    corpus_dir = get_corpus_dir()
    index = WordIndex.load(corpus_dir)
    with Session(migrated_engine) as session:
        threshold = int(session.get(ExperimentConfig, "baseline_min_occurrences").value)  # type: ignore[union-attr]
        tracked_count = int(session.get(ExperimentConfig, "tracked_bigram_count").value)  # type: ignore[union-attr]
        passages = session.exec(
            select(TextPassage).where(
                col(TextPassage.kind) == "baseline",
                col(TextPassage.form) == "A",
                col(TextPassage.participant_id).is_(None),
            )
        ).all()

    combined: dict[str, int] = defaultdict(int)
    for passage in passages:
        assert passage.bigram_counts == _recount(passage.text)
        for bigram, count in _recount(passage.text).items():
            combined[bigram] += count

    tracked = index.tracked_bigrams[:tracked_count]
    below = [b for b in tracked if combined.get(b, 0) < threshold]
    assert below == [], below
    assert (corpus_dir / TOP_BIGRAMS_FILENAME).exists()


def test_compose_is_deterministic_across_runs(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    assert runner.invoke(app, ["corpus", "build"]).exit_code == 0
    assert runner.invoke(app, ["corpus", "compose-baseline"]).exit_code == 0
    first = _shared_a_texts(migrated_engine)
    second_run = runner.invoke(app, ["corpus", "compose-baseline"])
    assert second_run.exit_code == 0
    assert "unchanged" in second_run.stdout
    assert _shared_a_texts(migrated_engine) == first


def get_corpus_dir() -> Path:
    from typist.config import get_settings

    return get_settings().corpus_dir
