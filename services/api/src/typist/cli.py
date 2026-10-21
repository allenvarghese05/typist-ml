"""The `typist` command (design doc section 14.1). T0.3 adds only `typist db migrate`."""

import random

import typer
from sqlmodel import Session

from typist.config import get_settings
from typist.corpus.build import build_corpus
from typist.corpus.word_index import WordIndex
from typist.db import create_db_engine
from typist.migrations import upgrade_to_head
from typist.models import ExperimentConfig
from typist.services.session_stats import recompute_stats
from typist.services.test_composer import (
    BaselinePassagesInUseError,
    BaselineTextsDifferError,
    compose_baseline,
    load_baseline_config,
    persist_baseline,
)

app = typer.Typer(help="Typist-ML admin commands.", no_args_is_help=True, add_completion=False)
db_app = typer.Typer(help="Database commands.", no_args_is_help=True)
app.add_typer(db_app, name="db")


@app.callback()
def main() -> None:
    """Typist-ML admin commands (design doc section 14.1)."""


@db_app.callback()
def db() -> None:
    """Database commands."""


@db_app.command("migrate")
def migrate() -> None:
    """Run Alembic migrations: upgrade the configured database (TYPIST_DB_PATH) to head."""
    upgrade_to_head()


corpus_app = typer.Typer(
    help="Corpus and baseline-text commands (design doc 14.1).", no_args_is_help=True
)
app.add_typer(corpus_app, name="corpus")


@corpus_app.callback()
def corpus() -> None:
    """Corpus build and baseline text composition (design doc sections 13, 14.1)."""


def _config_int(session: Session, key: str) -> int:
    """Return an integer experiment_config value; exit 1 if the key is missing (run migrations)."""
    row = session.get(ExperimentConfig, key)
    if row is None:
        typer.echo(f"experiment_config is missing '{key}'; run `typist db migrate`", err=True)
        raise typer.Exit(code=1)
    return int(row.value)


@corpus_app.command("build")
def build() -> None:
    """Build the word list and tracked-bigram index into the corpus directory.

    Reads corpus_word_count and tracked_bigram_count from experiment_config and writes
    words.json and top_bigrams.json to TYPIST_CORPUS_DIR (overwriting; the build is
    deterministic). The order-3 n-gram model (design doc 13.4) arrives in T3.1.
    """
    settings = get_settings()
    engine = create_db_engine(settings.db_path)
    with Session(engine) as session:
        word_count = _config_int(session, "corpus_word_count")
        tracked_count = _config_int(session, "tracked_bigram_count")
    build_corpus(settings.corpus_dir, word_count=word_count, tracked_count=tracked_count)
    typer.echo(f"built corpus artifacts in {settings.corpus_dir}")


@corpus_app.command("compose-baseline")
def compose_baseline_command(
    replace: bool = typer.Option(
        False, "--replace", help="Overwrite existing form A texts (refused if a block uses them)."
    ),
) -> None:
    """Compose the shared baseline (form A) texts and write them to text_passages.

    Idempotent: if form A already exists and matches, prints 'unchanged'; if it differs, exits 1
    unless --replace is passed; --replace is refused (exit 1) if any session block references a
    form A passage (the freeze guard; frozen_at enforcement is T3.5).
    """
    settings = get_settings()
    try:
        index = WordIndex.load(settings.corpus_dir)
    except FileNotFoundError:
        typer.echo("corpus artifacts missing; run `typist corpus build` first", err=True)
        raise typer.Exit(code=1) from None
    engine = create_db_engine(settings.db_path)
    with Session(engine) as session:
        config = load_baseline_config(session)
        passages = compose_baseline(config, index, random.Random(config.corpus_seed))
        try:
            result = persist_baseline(session, passages, replace=replace)
        except BaselineTextsDifferError:
            typer.echo("form A already exists and differs; pass --replace to overwrite", err=True)
            raise typer.Exit(code=1) from None
        except BaselinePassagesInUseError:
            typer.echo("refusing to replace form A: a session block references it", err=True)
            raise typer.Exit(code=1) from None
    typer.echo(f"{result.status}: {result.parts} baseline passages (form A)")


stats_app = typer.Typer(help="Statistics commands (design doc 14.1).", no_args_is_help=True)
app.add_typer(stats_app, name="stats")


@stats_app.callback()
def stats() -> None:
    """Rebuild derived statistics from raw keystrokes (design doc sections 6.2, 14.1)."""


@stats_app.command("recompute")
def recompute(
    pid: str | None = typer.Option(
        None, "--pid", help="Only this participant's sessions (default: all)."
    ),
) -> None:
    """Rebuild bigram_stats and sessions.wpm/accuracy for every completed session.

    Deterministic and idempotent: each completed session is deleted-and-reinserted in its own
    transaction, so re-running reproduces the same numbers (the T1.9 acceptance). Non-completed
    sessions (in_progress, abandoned) are skipped and never changed. status/ended_at are never
    touched by recompute (owner answers 4, 6, 8).
    """
    settings = get_settings()
    engine = create_db_engine(settings.db_path)
    with Session(engine) as session:
        result = recompute_stats(session, pid)
    typer.echo(f"recomputed {result.recomputed} session(s); skipped {result.skipped} not completed")
