"""The `typist` command (design doc section 14.1). T0.3 adds only `typist db migrate`."""

import random
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

import typer
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from typist.api.routers.admin import get_word_index
from typist.config import get_settings
from typist.corpus.build import build_corpus
from typist.corpus.word_index import WordIndex
from typist.db import create_db_engine
from typist.main import create_app
from typist.migrations import upgrade_to_head
from typist.models import ExperimentConfig, Participant
from typist.schemas.admin import ChecksResponse
from typist.schemas.analysis import ParticipantResults
from typist.services.analysis import (
    DEFAULT_BOOTSTRAP_RESAMPLES,
    DEFAULT_POSTERIOR_DRAWS,
    DEFAULT_SEED,
    ParticipantNotDoneError,
    participant_results,
)
from typist.services.assignment import (
    AssignmentError,
    MissingConfigError,
    assign_participant,
    load_assignment_config,
)
from typist.services.checks import run_participant_checks
from typist.services.figures import generate_all_figures
from typist.services.overhead import format_report, overhead_report
from typist.services.participants import (
    AliasAlreadyExistsError,
    ParticipantNotFoundError,
    create_participant,
    delete_participant,
)
from typist.services.pipeline_sim import run_pipeline_simulation
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
            typer.echo(
                f"participant {pid!r} is not assigned; run `typist assign --pid {pid}` first",
                err=True,
            )
            raise typer.Exit(code=1) from None
        except BaselinePassagesNotFoundError:
            typer.echo(
                "form A passages missing; run `typist corpus compose-baseline` first", err=True
            )
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


participant_app = typer.Typer(
    help="Participant administration commands (design doc 14.1).", no_args_is_help=True
)
app.add_typer(participant_app, name="participant")


@participant_app.callback()
def participant() -> None:
    """Participant administration commands (design doc section 14.1)."""


@participant_app.command("add")
def participant_add_command(
    alias: str = typer.Option(..., "--alias", help="Unique participant alias."),
    builder: bool = typer.Option(False, "--builder", help="Flag participant as unblinded builder."),
) -> None:
    """Create a new participant in 'enrolled' status."""
    settings = get_settings()
    engine = create_db_engine(settings.db_path)
    with Session(engine) as session:
        try:
            p = create_participant(session, alias=alias, is_builder=builder)
        except AliasAlreadyExistsError:
            typer.echo(f"participant with alias {alias!r} already exists", err=True)
            raise typer.Exit(code=1) from None
    typer.echo(f"created participant {p.id} (alias={p.alias}, builder={p.is_builder})")


@participant_app.command("delete")
def participant_delete_command(
    pid: str = typer.Option(..., "--pid", help="Participant id to delete."),
) -> None:
    """Delete a participant and all child records."""
    settings = get_settings()
    engine = create_db_engine(settings.db_path)
    with Session(engine) as session:
        try:
            deletion = delete_participant(session, pid)
        except ParticipantNotFoundError:
            typer.echo(f"no participant with id {pid!r}", err=True)
            raise typer.Exit(code=1) from None
    typer.echo(f"deleted participant {pid}: {deletion.sessions} sessions, {deletion.drills} drills")


def format_checks_report(report: ChecksResponse) -> str:
    """Format one participant's data-quality checks and session trend table for terminal display."""
    lines: list[str] = []
    lines.append(f"Participant: {report.alias} ({report.participant_id}) - Status: {report.status}")
    overall = "PASSED" if report.passed else "FAILED"
    lines.append(f"Data Quality Checks: [{overall}]")

    def _mark(passed: bool) -> str:
        return "PASS" if passed else "FAIL"

    c = report.checks
    lines.append(f"  [{_mark(c.seq_gaps.passed)}] Sequence Gaps: {c.seq_gaps.count} gap(s)")
    for detail in c.seq_gaps.details:
        lines.append(f"      - {detail}")

    lines.append(
        f"  [{_mark(c.dwell_anomalies.passed)}] Dwell Anomalies: "
        f"{c.dwell_anomalies.negative_count} negative, {c.dwell_anomalies.over_1000ms_count} > 1000ms"
    )
    for detail in c.dwell_anomalies.details:
        lines.append(f"      - {detail}")

    lines.append(
        f"  [{_mark(c.short_blocks.passed)}] Short Blocks: {c.short_blocks.count} short block(s)"
    )
    for detail in c.short_blocks.details:
        lines.append(f"      - {detail}")

    lines.append(
        f"  [{_mark(c.missing_keyups.passed)}] Missing Keyups: "
        f"{c.missing_keyups.missing_count}/{c.missing_keyups.total_events} "
        f"({c.missing_keyups.missing_share * 100:.2f}%)"
    )
    for detail in c.missing_keyups.details:
        lines.append(f"      - {detail}")

    lines.append(
        f"  [{_mark(c.in_progress_sessions.passed)}] In-Progress Sessions: "
        f"{c.in_progress_sessions.count} lingering"
    )
    for detail in c.in_progress_sessions.details:
        lines.append(f"      - {detail}")

    if report.trend:
        lines.append("\nSession Trends:")
        first_sets = list(report.trend[0].per_set_error_rate.keys())
        header = f"{'Day':<5} {'Phase':<10} {'WPM':<7} {'Accuracy':<10}"
        for s in first_sets:
            header += f" {'Set ' + s:<12}"
        lines.append(header)
        lines.append("-" * len(header))
        for row in report.trend:
            wpm_str = f"{row.wpm:.1f}" if row.wpm is not None else "-"
            acc_str = f"{row.accuracy * 100:.1f}%" if row.accuracy is not None else "-"
            line = f"{row.day_index:<5} {row.phase:<10} {wpm_str:<7} {acc_str:<10}"
            for s in first_sets:
                rate = row.per_set_error_rate.get(s)
                rate_str = f"{rate * 100:.1f}%" if rate is not None else "-"
                line += f" {rate_str:<12}"
            lines.append(line)
    else:
        lines.append("\nSession Trends: No completed sessions yet.")

    return "\n".join(lines)


@app.command("check")
def check_command(
    pid: str | None = typer.Option(
        None, "--pid", help="Participant id to check (default: all active participants)."
    ),
) -> None:
    """Run daily data-quality checks and print session trend table (design doc 12.6, 14.1; T2.9)."""
    settings = get_settings()
    engine = create_db_engine(settings.db_path)
    with Session(engine) as session:
        if pid is not None:
            try:
                reports = [run_participant_checks(session, pid)]
            except ParticipantNotFoundError:
                typer.echo(f"no participant with id {pid!r}", err=True)
                raise typer.Exit(code=1) from None
        else:
            participants = session.exec(
                select(Participant)
                .where(col(Participant.status) != "withdrawn")
                .order_by(col(Participant.alias))
            ).all()
            if not participants:
                typer.echo("no active participants found")
                return
            reports = [run_participant_checks(session, p.id) for p in participants]

    all_passed = True
    for report in reports:
        typer.echo(format_checks_report(report))
        typer.echo("")
        if not report.passed:
            all_passed = False

    if not all_passed:
        raise typer.Exit(code=1)


dev_app = typer.Typer(help="Developer simulation and diagnostic commands.", no_args_is_help=True)
app.add_typer(dev_app, name="dev")


@dev_app.command("test-pipeline")
@app.command("test-pipeline", hidden=True)
def test_pipeline_command(
    alias: str = typer.Option("dev-sim", "--alias", help="Participant alias"),
    error_rate: float = typer.Option(0.05, "--error-rate", help="Error rate (0.0 to 1.0)"),
    seed: int = typer.Option(42, "--seed", help="Random seed"),
    practice_days: int = typer.Option(
        2, "--practice-days", help="Number of practice days to simulate"
    ),
    is_builder: bool = typer.Option(
        True, "--is-builder/--no-is-builder", help="Whether participant is the author/builder"
    ),
) -> None:
    """Run an end-to-end experiment pipeline simulation with scripted keystrokes."""
    settings = get_settings()
    engine = create_db_engine(settings.db_path)
    typer.echo(f"Running pipeline test against database: {settings.db_path}")

    # Build or load corpus index
    corpus_dir = settings.corpus_dir
    if not (corpus_dir / "words.json").exists():
        typer.echo("Building temporary corpus artifacts...")
        build_corpus(corpus_dir, word_count=5000, tracked_count=50)
    index = WordIndex.load(corpus_dir)

    fastapi_app = create_app(settings)
    fastapi_app.dependency_overrides[get_word_index] = lambda: index
    client = TestClient(fastapi_app)

    try:
        result = run_pipeline_simulation(
            client,
            engine,
            settings.db_path,
            index,
            participant_alias=alias,
            practice_days=practice_days,
            error_rate=error_rate,
            seed=seed,
            log_fn=typer.echo,
            is_builder=is_builder,
        )
        typer.echo(
            f"\nSUCCESS: Participant '{result.alias}' ({result.participant_id}) reached status '{result.status}'."
        )
        typer.echo(
            f"Simulated {result.total_keystrokes} keystrokes across "
            f"{result.baseline_sessions} baseline, {result.practice_sessions} practice, and {result.retest_sessions} retest sessions."
        )
        typer.echo(
            f"Quality checks passed: {result.checks_passed}. Recomputed sessions: {result.recomputed_sessions}."
        )
    except Exception as exc:
        typer.echo(f"\nFAILURE: Pipeline simulation failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def format_analysis_report(res: ParticipantResults) -> str:
    """Format study-level outcome analysis report for terminal display."""
    lines: list[str] = []
    builder_str = " (builder, unblinded)" if res.is_builder else " (blinded)"
    lines.append(
        f"Participant: {res.alias} ({res.participant_id}){builder_str} - Status: {res.status}"
    )
    lines.append(
        f"Baseline: WPM={res.baseline_wpm if res.baseline_wpm is not None else '-'}, "
        f"Acc={f'{res.baseline_accuracy * 100:.1f}%' if res.baseline_accuracy is not None else '-'} "
        f"(Sessions: {', '.join(res.analyzed_baseline_session_ids)})"
    )
    lines.append(
        f"Retest:   WPM={res.retest_wpm if res.retest_wpm is not None else '-'}, "
        f"Acc={f'{res.retest_accuracy * 100:.1f}%' if res.retest_accuracy is not None else '-'} "
        f"(Sessions: {', '.join(res.analyzed_retest_session_ids)})"
    )
    lines.append("")

    # Primary Outcome table
    lines.append("PRIMARY OUTCOME: Error Rates and Beta Posterior Targeting Effects")
    lines.append(
        f"{'Set':<5} {'Arm':<11} {'Base Err':<12} {'Base 95% CI':<18} "
        f"{'Ret Err':<12} {'Ret 95% CI':<18} {'Change':<8} {'Effect E(s)':<12} {'P(E<0)':<8}"
    )
    lines.append("-" * 105)
    for s in res.sets:
        b_err = (
            f"{s.baseline_errors}/{s.baseline_attempts} ({s.baseline_error_rate * 100:.1f}%)"
            if s.baseline_error_rate is not None
            else "-"
        )
        b_ci = (
            f"[{s.baseline_beta_ci_lower:.4f}, {s.baseline_beta_ci_upper:.4f}]"
            if s.baseline_beta_ci_lower is not None
            else "-"
        )
        r_err = (
            f"{s.retest_errors}/{s.retest_attempts} ({s.retest_error_rate * 100:.1f}%)"
            if s.retest_error_rate is not None
            else "-"
        )
        r_ci = (
            f"[{s.retest_beta_ci_lower:.4f}, {s.retest_beta_ci_upper:.4f}]"
            if s.retest_beta_ci_lower is not None
            else "-"
        )
        chg = f"{s.error_rate_change * 100:+.2f}%" if s.error_rate_change is not None else "-"
        eff = f"{s.targeting_effect * 100:+.2f}%" if s.targeting_effect is not None else "-"
        p_below = f"{s.share_below_zero * 100:.1f}%" if s.share_below_zero is not None else "-"
        lines.append(
            f"{s.set_label:<5} {s.arm:<11} {b_err:<12} {b_ci:<18} "
            f"{r_err:<12} {r_ci:<18} {chg:<8} {eff:<12} {p_below:<8}"
        )
    lines.append("")

    # Secondary Outcome table
    lines.append("KEY SECONDARY OUTCOME: Median IKI and Bootstrap Confidence Intervals")
    lines.append(
        f"{'Set':<5} {'Arm':<11} {'Base IKI (n)':<16} {'Base IQR':<10} "
        f"{'Ret IKI (n)':<16} {'Ret IQR':<10} {'Change':<10} {'Effect F(s)':<14} {'Bootstrap 95% CI':<20}"
    )
    lines.append("-" * 115)
    for s in res.sets:
        b_iki = (
            f"{s.baseline_iki_median_ms:.1f}ms ({s.baseline_iki_n})"
            if s.baseline_iki_median_ms is not None
            else "-"
        )
        b_iqr = f"{s.baseline_iki_iqr_ms:.1f}ms" if s.baseline_iki_iqr_ms is not None else "-"
        r_iki = (
            f"{s.retest_iki_median_ms:.1f}ms ({s.retest_iki_n})"
            if s.retest_iki_median_ms is not None
            else "-"
        )
        r_iqr = f"{s.retest_iki_iqr_ms:.1f}ms" if s.retest_iki_iqr_ms is not None else "-"
        chg = f"{s.iki_change_ms:+.1f}ms" if s.iki_change_ms is not None else "-"
        eff = (
            f"{s.iki_targeting_effect_ms:+.1f}ms" if s.iki_targeting_effect_ms is not None else "-"
        )
        boot_ci = (
            f"[{s.iki_bootstrap_ci_lower_ms:+.1f}, {s.iki_bootstrap_ci_upper_ms:+.1f}]"
            if s.iki_bootstrap_ci_lower_ms is not None
            else "-"
        )
        lines.append(
            f"{s.set_label:<5} {s.arm:<11} {b_iki:<16} {b_iqr:<10} "
            f"{r_iki:<16} {r_iqr:<10} {chg:<10} {eff:<14} {boot_ci:<20}"
        )

    if res.exclusions:
        lines.append("")
        lines.append("EXCLUSIONS REPORT:")
        if res.exclusions.excluded_sessions:
            for ex in res.exclusions.excluded_sessions:
                lines.append(
                    f"  - Session {ex.session_id} ({ex.phase}, day {ex.day_index}): {ex.reason}"
                )
        else:
            lines.append("  - Excluded sessions: none")

        if res.exclusions.dropped_bigrams:
            for db in res.exclusions.dropped_bigrams:
                lines.append(
                    f"  - Dropped bigram '{db.bigram}' (Set {db.set_label}, {db.arm}): {db.retest_attempts} attempts (< 20)"
                )
        else:
            lines.append("  - Dropped bigrams: none")

        if res.exclusions.pause_counts:
            pause_strs = [f"{k}={v}" for k, v in sorted(res.exclusions.pause_counts.items())]
            lines.append(f"  - Excluded pause pairs: {', '.join(pause_strs)}")

    return "\n".join(lines)


@app.command("figures")
def figures_command(
    pid: str | None = typer.Option(
        None, "--pid", help="Participant id to generate figures for (default: all completed)."
    ),
    out_dir: Path | None = typer.Option(  # noqa: B008
        None,
        "--out-dir",
        help="Directory to save figures and snippets (default: <repo>/docs/figures).",
    ),
) -> None:
    """Regenerate study outcome figures and README Markdown snippets (§15.3, §16)."""
    settings = get_settings()
    engine = create_db_engine(settings.db_path)
    with Session(engine) as session:
        try:
            artifacts = generate_all_figures(session, out_dir=out_dir, pid=pid)
        except ParticipantNotFoundError:
            typer.echo(f"no participant with id {pid!r}", err=True)
            raise typer.Exit(code=1) from None
        except (ParticipantNotDoneError, ParticipantNotAssignedError) as error:
            typer.echo(f"cannot generate figures: {error}", err=True)
            raise typer.Exit(code=1) from None

    typer.echo(f"Saved primary chart: {artifacts.primary_png} (and .svg)")
    for alias, png, _svg in artifacts.participant_figures:
        if png != artifacts.primary_png:
            typer.echo(f"Saved participant chart ({alias}): {png} (and .svg)")
    typer.echo(f"Saved README snippets: {artifacts.readme_snippets_path}")
    typer.echo("\n" + artifacts.snippets_markdown)


@app.command("analyze")
def analyze_command(
    pid: str = typer.Option(..., "--pid", help="Participant id whose study results to analyze."),
    seed: int = typer.Option(
        DEFAULT_SEED, "--seed", help="Random seed for posterior draws and bootstrap."
    ),
    draws: int = typer.Option(
        DEFAULT_POSTERIOR_DRAWS, "--draws", help="Number of Beta posterior effect draws."
    ),
    resamples: int = typer.Option(
        DEFAULT_BOOTSTRAP_RESAMPLES, "--resamples", help="Number of IKI bootstrap resamples."
    ),
    figures: bool = typer.Option(
        False, "--figures", help="Also generate figures and README snippets for this participant."
    ),
    out_dir: Path | None = typer.Option(  # noqa: B008
        None,
        "--out-dir",
        help="Directory to save figures if --figures is set (default: <repo>/docs/figures).",
    ),
) -> None:
    """Compute and display pre-registered study outcome analysis for one completed participant."""
    settings = get_settings()
    engine = create_db_engine(settings.db_path)
    with Session(engine) as session:
        try:
            results = participant_results(
                session, pid, seed=seed, n_draws=draws, n_resamples=resamples
            )
        except ParticipantNotFoundError:
            typer.echo(f"no participant with id {pid!r}", err=True)
            raise typer.Exit(code=1) from None
        except (ParticipantNotDoneError, ParticipantNotAssignedError) as error:
            typer.echo(f"cannot analyze {pid}: {error}", err=True)
            raise typer.Exit(code=1) from None

        typer.echo(format_analysis_report(results))

        if figures:
            try:
                artifacts = generate_all_figures(
                    session,
                    out_dir=out_dir,
                    pid=pid,
                    seed=seed,
                    n_draws=draws,
                    n_resamples=resamples,
                )
                typer.echo(f"\nSaved primary chart: {artifacts.primary_png} (and .svg)")
                typer.echo(f"Saved README snippets: {artifacts.readme_snippets_path}")
            except Exception as exc:
                typer.echo(f"failed to generate figures: {exc}", err=True)
                raise typer.Exit(code=1) from exc
