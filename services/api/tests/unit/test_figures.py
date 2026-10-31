"""Unit tests for figure generation and README snippet formatting (design doc 15.3; T4.3)."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlmodel import Session
from typer.testing import CliRunner

from typist.cli import app
from typist.db import create_db_engine
from typist.migrations import upgrade_to_head
from typist.models import BigramAssignment, BigramStat, Participant
from typist.models import Session as TypingSession
from typist.schemas.analysis import (
    ArmGenerationSummary,
    GenerationOverview,
    Overview,
    ParticipantResults,
    ParticipantSummary,
    PercentilesSchema,
    SessionOverheadEntry,
    SetOutcome,
)
from typist.services.analysis import DEFAULT_SEED
from typist.services.figures import (
    compute_set_change_interval,
    format_generation_table,
    format_limitations_paragraph,
    format_overhead_line,
    generate_all_figures,
    plot_set_error_rate_change,
)

NOW = datetime(2026, 10, 30, 12, 0, 0, tzinfo=UTC)
runner = CliRunner()


@pytest.fixture
def migrated_engine(isolated_settings: Path) -> Iterator[Engine]:
    """Upgrade per-test db and yield engine."""
    upgrade_to_head()
    engine = create_db_engine(isolated_settings)
    try:
        yield engine
    finally:
        engine.dispose()


def test_compute_set_change_interval_math() -> None:
    # 10 errors in 100 attempts at base (0.10); 5 errors in 100 at ret (0.05) -> change -0.05
    res = compute_set_change_interval(10, 100, 5, 100, n_draws=10_000, seed=DEFAULT_SEED)
    assert res is not None
    pt, low, high = res
    assert pt == -0.05
    assert low < pt < high
    assert -0.15 < low < 0.0
    assert -0.05 < high < 0.05

    # Zero attempts yields None
    assert compute_set_change_interval(0, 0, 5, 100) is None
    assert compute_set_change_interval(5, 100, 0, 0) is None


def test_format_generation_table() -> None:
    arms = [
        ArmGenerationSummary(
            arm="control",
            drills_count=20,
            attempts_count=20,
            acceptance_rate=1.0,
            attempts_per_drill=1.0,
            mean_target_density=0.0,
            mean_word_length=4.5,
            mean_real_word_ratio=1.0,
            tokens_per_sec=None,
            mean_gen_ms=None,
            peak_memory_mb=None,
        ),
        ArmGenerationSummary(
            arm="llm",
            drills_count=20,
            attempts_count=25,
            acceptance_rate=0.8,
            attempts_per_drill=1.25,
            mean_target_density=0.25,
            mean_word_length=4.2,
            mean_real_word_ratio=0.95,
            tokens_per_sec=45.2,
            mean_gen_ms=350.0,
            peak_memory_mb=850.0,
        ),
    ]
    overview = Overview(
        participants=[],
        overhead=[],
        generation=GenerationOverview(arms=arms, total_drills=40, total_attempts=45),
    )
    table = format_generation_table(overview)
    assert "| Arm | Drills | Mean Density | Real-Word Ratio | Acceptance Rate |" in table
    assert "| control | 20 | 0.000 | 1.000 | 100.0% |" in table
    assert "| llm | 20 | 0.250 | 0.950 | 80.0% |" in table


def test_format_overhead_line() -> None:
    overview = Overview(
        participants=[],
        overhead=[
            SessionOverheadEntry(
                session_id="all",
                participant_id="all",
                events=1000,
                handler=PercentilesSchema(p50=0.3, p95=0.75, p99=1.1),
                dispatch=PercentilesSchema(p50=0.8, p95=1.45, p99=2.3),
            )
        ],
        generation=GenerationOverview(
            arms=[
                ArmGenerationSummary(
                    arm="llm",
                    drills_count=10,
                    attempts_count=10,
                    acceptance_rate=1.0,
                    attempts_per_drill=1.0,
                    mean_target_density=0.25,
                    mean_word_length=4.2,
                    mean_real_word_ratio=0.95,
                    tokens_per_sec=42.5,
                    mean_gen_ms=350.0,
                    peak_memory_mb=850.0,
                )
            ],
            total_drills=10,
            total_attempts=10,
        ),
    )
    line = format_overhead_line(overview)
    assert "handler p95 = 0.75 ms (target < 1.0 ms)" in line
    assert "dispatch lag p95 = 1.45 ms" in line
    assert "LLM generation: 42.5 tokens/s on Apple Silicon" in line


def test_format_limitations_paragraph(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        overview = Overview(
            participants=[
                ParticipantSummary(
                    id="p1",
                    alias="builder-1",
                    status="done",
                    is_builder=True,
                    is_blinded=False,
                    completed_sessions=14,
                )
            ],
            overhead=[],
            generation=GenerationOverview(arms=[], total_drills=0, total_attempts=0),
        )
        para = format_limitations_paragraph(session, overview)
        assert "N = 1 participant (builder, unblinded)" in para
        assert "14 completed sessions" in para
        assert "builder, who was unblinded" in para


def _make_dummy_results(alias: str, is_builder: bool) -> ParticipantResults:
    sets = [
        SetOutcome(
            set_label="A",
            arm="control",
            bigrams=["th"],
            retained_bigrams=["th"],
            dropped_bigrams=[],
            baseline_attempts=50,
            baseline_errors=5,
            baseline_error_rate=0.10,
            baseline_beta_ci_lower=0.04,
            baseline_beta_ci_upper=0.18,
            retest_attempts=50,
            retest_errors=4,
            retest_error_rate=0.08,
            retest_beta_ci_lower=0.03,
            retest_beta_ci_upper=0.16,
            error_rate_change=-0.02,
            targeting_effect=None,
            posterior_effect_median=None,
            posterior_effect_ci_lower=None,
            posterior_effect_ci_upper=None,
            share_below_zero=None,
            baseline_iki_n=50,
            baseline_iki_median_ms=200.0,
            baseline_iki_iqr_ms=30.0,
            retest_iki_n=50,
            retest_iki_median_ms=190.0,
            retest_iki_iqr_ms=28.0,
            iki_change_ms=-10.0,
            iki_targeting_effect_ms=None,
            iki_bootstrap_median_ms=None,
            iki_bootstrap_ci_lower_ms=None,
            iki_bootstrap_ci_upper_ms=None,
        ),
        SetOutcome(
            set_label="B",
            arm="heuristic",
            bigrams=["er"],
            retained_bigrams=["er"],
            dropped_bigrams=[],
            baseline_attempts=50,
            baseline_errors=6,
            baseline_error_rate=0.12,
            baseline_beta_ci_lower=0.05,
            baseline_beta_ci_upper=0.21,
            retest_attempts=50,
            retest_errors=2,
            retest_error_rate=0.04,
            retest_beta_ci_lower=0.01,
            retest_beta_ci_upper=0.10,
            error_rate_change=-0.08,
            targeting_effect=-0.06,
            posterior_effect_median=-0.058,
            posterior_effect_ci_lower=-0.12,
            posterior_effect_ci_upper=0.01,
            share_below_zero=0.92,
            baseline_iki_n=50,
            baseline_iki_median_ms=210.0,
            baseline_iki_iqr_ms=35.0,
            retest_iki_n=50,
            retest_iki_median_ms=180.0,
            retest_iki_iqr_ms=25.0,
            iki_change_ms=-30.0,
            iki_targeting_effect_ms=-20.0,
            iki_bootstrap_median_ms=-19.8,
            iki_bootstrap_ci_lower_ms=-40.0,
            iki_bootstrap_ci_upper_ms=-2.0,
        ),
    ]
    return ParticipantResults(
        participant_id=f"id-{alias}",
        alias=alias,
        status="done",
        is_builder=is_builder,
        is_blinded=not is_builder,
        baseline_wpm=50.0,
        baseline_accuracy=0.95,
        retest_wpm=55.0,
        retest_accuracy=0.97,
        analyzed_baseline_session_ids=["s1"],
        analyzed_retest_session_ids=["s2"],
        posterior_draws=1000,
        bootstrap_resamples=100,
        seed=DEFAULT_SEED,
        sets=sets,
        exclusions=None,
    )


def test_plot_set_error_rate_change_single(tmp_path: Path) -> None:
    res = _make_dummy_results("builder-test", is_builder=True)
    png_path = tmp_path / "set_error_rate_change.png"
    svg_path = tmp_path / "set_error_rate_change.svg"

    plot_set_error_rate_change([res], png_path, svg_path, n_draws=1000)

    assert png_path.exists()
    assert svg_path.exists()

    # Verify PNG header
    with open(png_path, "rb") as f:
        header = f.read(8)
        assert header == b"\x89PNG\r\n\x1a\n"

    # Verify SVG is valid XML containing SVG tag
    svg_content = svg_path.read_text(encoding="utf-8")
    assert "<svg" in svg_content
    assert "builder-test [Builder (unblinded)]" in svg_content


def test_plot_set_error_rate_change_multiple(tmp_path: Path) -> None:
    p1 = _make_dummy_results("builder-user", is_builder=True)
    p2 = _make_dummy_results("peer-user", is_builder=False)
    png_path = tmp_path / "set_error_rate_change.png"
    svg_path = tmp_path / "set_error_rate_change.svg"

    plot_set_error_rate_change([p1, p2], png_path, svg_path, n_draws=1000)

    assert png_path.exists()
    assert svg_path.exists()
    svg_content = svg_path.read_text(encoding="utf-8")
    assert "builder-user [Builder (unblinded)]" in svg_content
    assert "peer-user [Peer (blinded)]" in svg_content


def test_generate_all_figures_end_to_end(migrated_engine: Engine, tmp_path: Path) -> None:
    with Session(migrated_engine) as session:
        p = Participant(alias="pilot-builder", status="done", is_builder=True, is_blinded=False)
        session.add(p)
        session.flush()

        session.add_all(
            [
                BigramAssignment(
                    participant_id=p.id,
                    set_label="A",
                    arm="control",
                    bigram="th",
                    baseline_rank=1,
                    weakness_score=0.5,
                    baseline_attempts=30,
                    baseline_errors=3,
                    frozen_at=NOW,
                ),
                BigramAssignment(
                    participant_id=p.id,
                    set_label="B",
                    arm="heuristic",
                    bigram="er",
                    baseline_rank=2,
                    weakness_score=0.4,
                    baseline_attempts=30,
                    baseline_errors=3,
                    frozen_at=NOW,
                ),
            ]
        )
        session.flush()

        s_base = TypingSession(
            participant_id=p.id,
            phase="baseline",
            day_index=1,
            status="completed",
            wpm=55.0,
            accuracy=0.96,
            client_info={},
            started_at=NOW,
            ended_at=NOW,
        )
        s_retest = TypingSession(
            participant_id=p.id,
            phase="retest",
            day_index=2,
            status="completed",
            wpm=60.0,
            accuracy=0.98,
            client_info={},
            started_at=NOW,
            ended_at=NOW,
        )
        session.add_all([s_base, s_retest])
        session.flush()

        session.add_all(
            [
                BigramStat(
                    participant_id=p.id,
                    session_id=s_base.id,
                    bigram="th",
                    attempts=30,
                    errors=3,
                    iki_n=0,
                ),
                BigramStat(
                    participant_id=p.id,
                    session_id=s_base.id,
                    bigram="er",
                    attempts=30,
                    errors=3,
                    iki_n=0,
                ),
                BigramStat(
                    participant_id=p.id,
                    session_id=s_retest.id,
                    bigram="th",
                    attempts=30,
                    errors=2,
                    iki_n=0,
                ),
                BigramStat(
                    participant_id=p.id,
                    session_id=s_retest.id,
                    bigram="er",
                    attempts=30,
                    errors=1,
                    iki_n=0,
                ),
            ]
        )
        session.commit()

        artifacts = generate_all_figures(session, out_dir=tmp_path, n_draws=1000, n_resamples=100)
        assert artifacts.primary_png.exists()
        assert artifacts.primary_svg.exists()
        assert artifacts.readme_snippets_path.exists()
        assert "README Snippets" in artifacts.snippets_markdown


def _seed_completed_participant(session: Session, alias: str = "pilot-builder") -> str:
    p = Participant(alias=alias, status="done", is_builder=True, is_blinded=False)
    session.add(p)
    session.flush()

    session.add_all(
        [
            BigramAssignment(
                participant_id=p.id,
                set_label="A",
                arm="control",
                bigram="th",
                baseline_rank=1,
                weakness_score=0.5,
                baseline_attempts=30,
                baseline_errors=3,
                frozen_at=NOW,
            ),
            BigramAssignment(
                participant_id=p.id,
                set_label="B",
                arm="heuristic",
                bigram="er",
                baseline_rank=2,
                weakness_score=0.4,
                baseline_attempts=30,
                baseline_errors=3,
                frozen_at=NOW,
            ),
        ]
    )
    session.flush()

    s_base = TypingSession(
        participant_id=p.id,
        phase="baseline",
        day_index=1,
        status="completed",
        wpm=55.0,
        accuracy=0.96,
        client_info={},
        started_at=NOW,
        ended_at=NOW,
    )
    s_retest = TypingSession(
        participant_id=p.id,
        phase="retest",
        day_index=2,
        status="completed",
        wpm=60.0,
        accuracy=0.98,
        client_info={},
        started_at=NOW,
        ended_at=NOW,
    )
    session.add_all([s_base, s_retest])
    session.flush()

    session.add_all(
        [
            BigramStat(
                participant_id=p.id,
                session_id=s_base.id,
                bigram="th",
                attempts=30,
                errors=3,
                iki_n=0,
            ),
            BigramStat(
                participant_id=p.id,
                session_id=s_base.id,
                bigram="er",
                attempts=30,
                errors=3,
                iki_n=0,
            ),
            BigramStat(
                participant_id=p.id,
                session_id=s_retest.id,
                bigram="th",
                attempts=30,
                errors=2,
                iki_n=0,
            ),
            BigramStat(
                participant_id=p.id,
                session_id=s_retest.id,
                bigram="er",
                attempts=30,
                errors=1,
                iki_n=0,
            ),
        ]
    )
    session.commit()
    return p.id


def test_cli_figures_command_empty_db(isolated_settings: Path, migrated_engine: Engine) -> None:
    result = runner.invoke(app, ["figures"])
    assert result.exit_code == 1
    assert "no completed participants found" in result.output


def test_cli_figures_command_success(
    isolated_settings: Path, migrated_engine: Engine, tmp_path: Path
) -> None:
    with Session(migrated_engine) as session:
        _seed_completed_participant(session)

    result = runner.invoke(app, ["figures", "--out-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "set_error_rate_change.png").exists()
    assert (tmp_path / "set_error_rate_change.svg").exists()
    assert (tmp_path / "readme_snippets.md").exists()
    assert "Saved primary chart" in result.output
    assert "README Snippets" in result.output


def test_cli_analyze_with_figures_flag(
    isolated_settings: Path, migrated_engine: Engine, tmp_path: Path
) -> None:
    with Session(migrated_engine) as session:
        pid = _seed_completed_participant(session)

    result = runner.invoke(app, ["analyze", "--pid", pid, "--figures", "--out-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert f"Participant: pilot-builder ({pid})" in result.output
    assert (tmp_path / "set_error_rate_change.png").exists()
    assert (tmp_path / "set_error_rate_change.svg").exists()
    assert (tmp_path / "readme_snippets.md").exists()
