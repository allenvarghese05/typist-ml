"""The `typist` command (design doc section 14.1). T0.3 adds only `typist db migrate`."""

import random
from contextlib import suppress
from datetime import UTC, datetime

import typer
from sqlmodel import Session

from typist.config import get_settings
from typist.corpus.build import build_corpus
from typist.corpus.word_index import WordIndex
from typist.db import create_db_engine
from typist.migrations import upgrade_to_head
from typist.models import ExperimentConfig
from typist.services.assignment import (
    AssignmentError,
    MissingConfigError,
    assign_participant,
    load_assignment_config,
)
from typist.services.overhead import format_report, overhead_report
from typist.services.participants import ParticipantNotFoundError
from typist.services.session_stats import recompute_stats
from typist.services.test_composer import (
    BaselinePassagesInUseError,
    BaselinePassagesNotFoundError,
    BaselineTextsDifferError,
    ParticipantNotAssignedError,
    RetestPassagesInUseError,
    RetestTextsDifferError,
    compose_and_persist_retest,
    compose_baseline,
    load_baseline_config,
    persist_baseline,
)
from typist.services.test_composer import (
    MissingConfigError as ComposerMissingConfigError,
)
from typist.worker import DEFAULT_POLL_INTERVAL_S, run_worker

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


@corpus_app.command("compose-retest")
def compose_retest_command(
    pid: str = typer.Option(
        ..., "--pid", help="Participant id whose frozen assignment drives form B."
    ),
    replace: bool = typer.Option(
        False,
        "--replace",
        help="Overwrite existing form B texts for this participant (refused if a block uses them).",
    ),
) -> None:
    """Compose one participant's retest (form B) texts after assignment and write to text_passages.

    Requires shared form A passages in text_passages and frozen bigram_assignment rows for --pid.
    Idempotent: prints 'unchanged' if form B already matches; exits 1 if it differs unless
    --replace is passed; --replace is refused (exit 1) if any session block references a form B
    passage for this participant.
    """
    settings = get_settings()
    try:
        index = WordIndex.load(settings.corpus_dir)
    except FileNotFoundError:
        typer.echo("corpus artifacts missing; run `typist corpus build` first", err=True)
        raise typer.Exit(code=1) from None
    engine = create_db_engine(settings.db_path)
    with Session(engine) as session:
        try:
            result = compose_and_persist_retest(session, pid, index, replace=replace)
        except ComposerMissingConfigError as error:
            typer.echo(f"experiment_config is missing '{error}'; run `typist db migrate`", err=True)
            raise typer.Exit(code=1) from None
        except ParticipantNotFoundError:
            typer.echo(f"no participant with id {pid!r}", err=True)
            raise typer.Exit(code=1) from None
        except ParticipantNotAssignedError:
            typer.echo(f"participant {pid!r} is not assigned; run `typist assign --pid {pid}` first", err=True)
            raise typer.Exit(code=1) from None
        except BaselinePassagesNotFoundError:
            typer.echo("form A passages missing; run `typist corpus compose-baseline` first", err=True)
            raise typer.Exit(code=1) from None
        except RetestTextsDifferError:
            typer.echo(
                f"form B for {pid} already exists and differs; pass --replace to overwrite",
                err=True,
            )
            raise typer.Exit(code=1) from None
        except RetestPassagesInUseError:
            typer.echo(
                f"refusing to replace form B for {pid}: a session block references it",
                err=True,
            )
            raise typer.Exit(code=1) from None
    typer.echo(f"{result.status}: {result.parts} retest passages (form B) for {pid}")


@app.command("overhead")
def overhead(
    pid: str | None = typer.Option(
        None, "--pid", help="Only this participant's sessions (default: all)."
    ),
    session_id: str | None = typer.Option(
        None, "--session", help="Only this session (default: all)."
    ),
) -> None:
    """Print instrumentation-overhead percentiles (handler_ms, dispatch_lag_ms) per session.

    Reports p50/p95/p99 in milliseconds for each matching session plus a pooled "all" row
    (design doc 12.5). --session narrows to one session; else --pid narrows to one participant;
    else every session is reported. Prints "no keystroke events" and exits 0 when nothing matches.
    """
    settings = get_settings()
    engine = create_db_engine(settings.db_path)
    with Session(engine) as session:
        rows = overhead_report(session, pid, session_id)
    if rows[-1].events == 0:
        typer.echo("no keystroke events")
        return
    typer.echo(format_report(rows))


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


@app.command("assign")
def assign(
    pid: str = typer.Option(..., "--pid", help="Participant id to rank, split, map and freeze."),
) -> None:
    """Rank, split, seed-shuffle and freeze one participant's weak bigrams (design doc 3.4, 14.1).

    Allowed only when the participant has exactly baseline_parts completed baseline sessions and no
    existing assignment (owner answer 6; T2.8 owns the status transition). Reproducible: the arm
    shuffle uses random.Random(f"{assignment_seed}:{pid}") from experiment_config. Prints the frozen
    set -> arm map and exits 1 with a message on any precondition or data error.
    """
    settings = get_settings()
    try:
        index = WordIndex.load(settings.corpus_dir)
    except FileNotFoundError:
        typer.echo("corpus artifacts missing; run `typist corpus build` first", err=True)
        raise typer.Exit(code=1) from None
    engine = create_db_engine(settings.db_path)
    with Session(engine) as session:
        try:
            config = load_assignment_config(session)
        except MissingConfigError as error:
            typer.echo(f"experiment_config is missing '{error}'; run `typist db migrate`", err=True)
            raise typer.Exit(code=1) from None
        rng = random.Random(f"{config.seed}:{pid}")
        try:
            rows = assign_participant(session, pid, rng=rng, now=datetime.now(UTC), index=index)
        except ParticipantNotFoundError:
            typer.echo(f"no participant with id {pid!r}", err=True)
            raise typer.Exit(code=1) from None
        except AssignmentError as error:
            typer.echo(f"cannot assign {pid}: {error}", err=True)
            raise typer.Exit(code=1) from None
        labels = sorted({row.set_label for row in rows})
        mapping = {
            label: next(row.arm for row in rows if row.set_label == label) for label in labels
        }
        summary = ", ".join(f"{label}->{mapping[label]}" for label in labels)
        typer.echo(f"assigned {pid}: {len(rows)} bigrams frozen; sets {summary}")
        with suppress(BaselinePassagesNotFoundError, ValueError):
            compose_and_persist_retest(session, pid, index)


@app.command("worker")
def worker(
    once: bool = typer.Option(False, "--once", help="Run a single poll/claim cycle and exit."),
    poll_interval: float = typer.Option(
        DEFAULT_POLL_INTERVAL_S,
        "--poll-interval",
        help="Seconds to sleep between empty queue polls.",
    ),
) -> None:
    """Run the generation worker (design doc sections 6.2, 10.2, 14.1; T2.5).

    Loads the corpus index from TYPIST_CORPUS_DIR, writes the worker heartbeat next to
    TYPIST_DB_PATH, and polls generation_jobs for pending work. Exits 1 with a clear message if
    corpus artifacts or required experiment_config keys are missing.
    """
    settings = get_settings()
    try:
        index = WordIndex.load(settings.corpus_dir)
    except FileNotFoundError:
        typer.echo("corpus artifacts missing; run `typist corpus build` first", err=True)
        raise typer.Exit(code=1) from None
    engine = create_db_engine(settings.db_path)
    try:
        with Session(engine) as session:
            _config_int(session, "control_word_pool")
        run_worker(
            engine,
            settings.db_path,
            index,
            once=once,
            poll_interval_s=poll_interval,
        )
    finally:
        engine.dispose()
