# pyright: reportUnknownMemberType=none, reportUnknownVariableType=none, reportUnknownArgumentType=none
"""Figure and artifact generation for README and Results Notebook (design doc 15.3, 16; D01, D05, D18, D20).

Headless rendering: matplotlib.use("Agg") is set unconditionally before importing pyplot.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import matplotlib

# Must configure headless backend before importing pyplot
matplotlib.use("Agg")

# isort: split
import matplotlib.pyplot as plt
import numpy as np
import sqlalchemy as sa
from matplotlib.axes import Axes
from matplotlib.ticker import FuncFormatter
from sqlmodel import Session, col, select

from typist.config import REPO_ROOT
from typist.models import KeystrokeEvent, Participant, SessionBlock
from typist.models import Session as TypingSession
from typist.schemas.analysis import Overview, ParticipantResults
from typist.services.analysis import (
    DEFAULT_BOOTSTRAP_RESAMPLES,
    DEFAULT_POSTERIOR_DRAWS,
    DEFAULT_SEED,
    ParticipantNotDoneError,
    overview_report,
    participant_results,
)
from typist.services.participants import ParticipantNotFoundError

DEFAULT_FIGURES_DIR = REPO_ROOT / "docs" / "figures"


@dataclass(frozen=True)
class FigureArtifacts:
    """Paths to regenerated figure files and formatted README snippets."""

    primary_png: Path
    primary_svg: Path
    participant_figures: list[tuple[str, Path, Path]]
    readme_snippets_path: Path
    snippets_markdown: str
    validation_audit_path: Path | None = None


def compute_set_change_interval(
    base_errors: int,
    base_attempts: int,
    ret_errors: int,
    ret_attempts: int,
    *,
    n_draws: int = DEFAULT_POSTERIOR_DRAWS,
    seed: int = DEFAULT_SEED,
) -> tuple[float, float, float] | None:
    """Compute point estimate and 95% equal-tailed Jeffreys Beta credible interval for d(s) = p_ret - p_base.

    Returns (d_point, ci_lower, ci_upper) as floats rounded to 6 decimal places, or None if attempts <= 0.
    """
    if base_attempts <= 0 or ret_attempts <= 0:
        return None
    p_base_point = base_errors / base_attempts
    p_ret_point = ret_errors / ret_attempts
    d_point = p_ret_point - p_base_point

    rng = np.random.default_rng(seed)
    p_base_draws = rng.beta(base_errors + 0.5, base_attempts - base_errors + 0.5, size=n_draws)
    p_ret_draws = rng.beta(ret_errors + 0.5, ret_attempts - ret_errors + 0.5, size=n_draws)
    d_draws = p_ret_draws - p_base_draws

    ci_low = float(np.percentile(d_draws, 2.5))
    ci_high = float(np.percentile(d_draws, 97.5))
    return (round(d_point, 6), round(ci_low, 6), round(ci_high, 6))


def format_generation_table(overview: Overview) -> str:
    """Format the generation audit table required by §15.3 item 2."""
    headers = ["Arm", "Drills", "Mean Density", "Real-Word Ratio", "Acceptance Rate"]
    lines = [
        f"| {' | '.join(headers)} |",
        "|---|---:|---:|---:|---:|",
    ]
    for arm in overview.generation.arms:
        drills = f"{arm.drills_count}"
        density = f"{arm.mean_target_density:.3f}" if arm.mean_target_density is not None else "-"
        real_word = (
            f"{arm.mean_real_word_ratio:.3f}" if arm.mean_real_word_ratio is not None else "-"
        )
        acc = f"{arm.acceptance_rate * 100:.1f}%" if arm.acceptance_rate is not None else "-"
        lines.append(f"| {arm.arm} | {drills} | {density} | {real_word} | {acc} |")
    return "\n".join(lines)


def format_overhead_line(overview: Overview) -> str:
    """Format the overhead p95 and LLM throughput line required by §15.3 item 3."""
    pooled = next((e for e in overview.overhead if e.session_id == "all"), None)
    handler_str = f"{pooled.handler.p95:.2f} ms" if pooled and pooled.handler else "N/A"
    dispatch_str = f"{pooled.dispatch.p95:.2f} ms" if pooled and pooled.dispatch else "N/A"

    llm_arm = next((a for a in overview.generation.arms if a.arm == "llm"), None)
    if llm_arm and llm_arm.tokens_per_sec is not None:
        tps_str = f"{llm_arm.tokens_per_sec:.1f} tokens/s on Apple Silicon"
    else:
        tps_str = "N/A"

    return (
        f"Instrumentation overhead: handler p95 = {handler_str} (target < 1.0 ms), "
        f"dispatch lag p95 = {dispatch_str}. LLM generation: {tps_str}."
    )


def is_simulated_study(
    session: Session, participant_ids: Sequence[str] | None = None
) -> tuple[bool, float | None]:
    """Detect whether completed sessions were created by `typist test-pipeline`."""
    stmt = select(TypingSession).where(col(TypingSession.status) == "completed")
    if participant_ids:
        stmt = stmt.where(col(TypingSession.participant_id).in_(participant_ids))
    rows = session.exec(stmt).all()
    if not rows:
        return (False, None)
    for row in rows:
        info = row.client_info
        if info and info.get("simulated") is True:
            err_rate = info.get("error_rate")
            return (True, float(err_rate) if isinstance(err_rate, (int, float)) else None)
    if participant_ids:
        p_stmt = select(Participant).where(col(Participant.id).in_(participant_ids))
        for p in session.exec(p_stmt).all():
            if p.alias in ("pilot-builder", "sim-builder", "sim-validation") or p.alias.startswith(
                "sim-"
            ):
                return (True, 0.05)
    return (False, None)


def format_limitations_paragraph(
    session: Session, overview: Overview, pid: str | None = None
) -> str:
    """Format the limitations paragraph stating N, sessions, keystrokes, and unblinded status (§15.3 item 4)."""
    if pid is not None:
        done_participants = [p for p in overview.participants if p.id == pid and p.status == "done"]
    else:
        done_participants = [p for p in overview.participants if p.status == "done"]
        if len(done_participants) > 1:
            builder_candidates = [
                p
                for p in done_participants
                if p.alias in ("pilot-builder", "sim-validation") or p.alias.startswith("sim-")
            ]
            if builder_candidates:
                done_participants = builder_candidates[:1]

    done_pids = [p.id for p in done_participants]
    n_count = len(done_participants)
    total_sessions = sum(p.completed_sessions for p in done_participants)

    keystroke_stmt = select(sa.func.count()).select_from(KeystrokeEvent)
    if done_pids:
        keystroke_stmt = (
            keystroke_stmt.join(SessionBlock, col(KeystrokeEvent.block_id) == col(SessionBlock.id))
            .join(TypingSession, col(SessionBlock.session_id) == col(TypingSession.id))
            .where(col(TypingSession.participant_id).in_(done_pids))
        )
    total_keystrokes = int(session.exec(keystroke_stmt).one() or 0)

    is_sim, sim_error_rate = is_simulated_study(session, done_pids)
    if is_sim:
        rate_str = (
            f" at a fixed {sim_error_rate * 100:.1f}% random error rate"
            if sim_error_rate is not None
            else ""
        )
        return (
            f"Simulated pipeline validation: all {total_keystrokes:,} total keystrokes across "
            f"{total_sessions} completed sessions were generated by `typist test-pipeline`"
            f"{rate_str} with no human participant (configured as builder, unblinded). "
            f"Because a stateless simulator cannot learn, any apparent drop in raw error rate on "
            f"selected weak bigrams reflects regression to the mean rather than skill acquisition, "
            f"and the held-out control contrast is evaluated strictly as an end-to-end null-effect "
            f"calibration check."
        )

    has_builder = any(p.is_builder for p in done_participants)
    has_peer = any(not p.is_builder for p in done_participants)

    if n_count == 1 and has_builder:
        participant_desc = "N = 1 participant (builder, unblinded)"
    elif n_count == 2 and has_builder and has_peer:
        participant_desc = "N = 2 participants (1 unblinded builder and 1 blinded peer)"
    else:
        participant_desc = f"N = {n_count} participant{'s' if n_count != 1 else ''}"

    return (
        f"This pilot reports findings from {participant_desc} across {total_sessions} completed "
        f"sessions and {total_keystrokes:,} total keystrokes. The primary participant is the author "
        f"and system builder, who was unblinded to arm assignments during typing; results are "
        f"descriptive within-person comparisons and should be evaluated with this limitation in mind."
    )


def format_readme_snippets(session: Session, overview: Overview, pid: str | None = None) -> str:
    """Assemble all §15.3 Markdown snippets for README inclusion."""
    table = format_generation_table(overview)
    overhead = format_overhead_line(overview)
    limitations = format_limitations_paragraph(session, overview, pid=pid)

    return (
        "# README Snippets (Generated per §15.3)\n\n"
        "## Generation Summary Table\n\n"
        f"{table}\n\n"
        "## Overhead & Throughput\n\n"
        f"{overhead}\n\n"
        "## Limitations\n\n"
        f"{limitations}\n"
    )


def _render_participant_axis(
    ax: Axes,
    res: ParticipantResults,
    *,
    seed: int = DEFAULT_SEED,
    n_draws: int = DEFAULT_POSTERIOR_DRAWS,
    is_simulated: bool = False,
    simulated_error_rate: float | None = None,
) -> None:
    """Render error rate change points and intervals for one participant onto a matplotlib axis."""
    set_labels = [s.set_label for s in res.sets]
    x_positions = np.arange(len(set_labels))

    changes: list[float] = []
    ci_lows: list[float] = []
    ci_highs: list[float] = []
    xtick_labels: list[str] = []
    colors: list[str] = []
    markers: list[str] = []

    ctl_change: float | None = None

    for s in res.sets:
        interval = compute_set_change_interval(
            s.baseline_errors,
            s.baseline_attempts,
            s.retest_errors,
            s.retest_attempts,
            seed=seed,
            n_draws=n_draws,
        )
        if interval is not None:
            pt, low, high = interval
        else:
            pt, low, high = 0.0, 0.0, 0.0

        changes.append(pt)
        ci_lows.append(low)
        ci_highs.append(high)

        if s.arm == "control":
            ctl_change = pt
            xtick_labels.append(f"Set {s.set_label}\n(control)\n[held-out]")
            colors.append("#475569")  # Slate-600
            markers.append("s")  # Square for control
        else:
            xtick_labels.append(f"Set {s.set_label}\n({s.arm})")
            if s.arm == "heuristic":
                colors.append("#2563EB")  # Blue-600
            elif s.arm == "markov":
                colors.append("#059669")  # Emerald-600
            elif s.arm == "llm":
                colors.append("#7C3AED")  # Violet-600
            else:
                colors.append("#0284C7")
            markers.append("o")

    # Reference line at zero change
    ax.axhline(0.0, color="#94A3B8", linestyle="-", linewidth=1.0, zorder=1)

    # Reference line for control change
    if ctl_change is not None:
        ax.axhline(
            ctl_change,
            color="#64748B",
            linestyle="--",
            linewidth=1.2,
            alpha=0.85,
            label=f"Control change: {ctl_change * 100:+.2f}%",
            zorder=2,
        )

    # Plot points and error bars
    for i, x in enumerate(x_positions):
        err_low = changes[i] - ci_lows[i]
        err_high = ci_highs[i] - changes[i]
        ax.errorbar(
            x,
            changes[i],
            yerr=[[err_low], [err_high]],
            fmt=markers[i],
            color=colors[i],
            ecolor=colors[i],
            elinewidth=2.0,
            capsize=5.0,
            capthick=1.5,
            markersize=8,
            zorder=3,
        )
        # Value label
        offset = 0.003 if changes[i] >= 0 else -0.006
        ax.annotate(
            f"{changes[i] * 100:+.1f}%\n[{ci_lows[i] * 100:+.1f}%, {ci_highs[i] * 100:+.1f}%]",
            (float(x), float(changes[i] + offset)),
            textcoords="offset points",
            xytext=(0, 10 if changes[i] >= 0 else -18),
            ha="center",
            fontsize=8,
            color="#1E293B",
            fontweight="medium",
        )

    def _pct_formatter(val: float, _: object) -> str:
        return f"{val * 100:+.1f}%"

    ax.set_xticks(x_positions)
    ax.set_xticklabels(xtick_labels, fontsize=9)
    ax.yaxis.set_major_formatter(FuncFormatter(_pct_formatter))
    ax.grid(axis="y", color="#E2E8F0", linestyle=":", linewidth=0.8, alpha=0.7)

    if is_simulated:
        rate_badge = (
            f"Simulated · {simulated_error_rate * 100:.1f}% fixed error rate · no human participant"
            if simulated_error_rate is not None
            else "Simulated · no human participant"
        )
        ax.set_title(f"{res.alias} [{rate_badge}]", fontsize=10.5, fontweight="bold", pad=10)
    else:
        role_badge = "Builder (unblinded)" if res.is_builder else "Peer (blinded)"
        ax.set_title(f"{res.alias} [{role_badge}]", fontsize=11, fontweight="bold", pad=10)
    ax.set_ylabel("Change in Error Rate (Retest - Baseline)", fontsize=9)
    if ctl_change is not None:
        ax.legend(loc="upper right", fontsize=8, framealpha=0.9)


def plot_set_error_rate_change(
    results: Sequence[ParticipantResults],
    out_png: Path,
    out_svg: Path,
    *,
    seed: int = DEFAULT_SEED,
    n_draws: int = DEFAULT_POSTERIOR_DRAWS,
    is_simulated: bool = False,
    simulated_error_rate: float | None = None,
) -> tuple[Path, Path]:
    """Plot error rate change with 95% Jeffreys Beta intervals for one or more participants."""
    out_png.parent.mkdir(parents=True, exist_ok=True)
    out_svg.parent.mkdir(parents=True, exist_ok=True)

    suptitle = (
        "Pipeline Validation (Simulated Data): Per-Set Error Rate Change (95% Jeffreys CIs)"
        if is_simulated
        else "Per-Set Error Rate Change with 95% Jeffreys Beta Credible Intervals"
    )

    n_part = len(results)
    if n_part == 1:
        width = 8.4 if len(results[0].sets) >= 4 else 7.5
        fig, ax = plt.subplots(figsize=(width, 5.2), dpi=300)
        _render_participant_axis(
            ax,
            results[0],
            seed=seed,
            n_draws=n_draws,
            is_simulated=is_simulated,
            simulated_error_rate=simulated_error_rate,
        )
        fig.suptitle(
            suptitle,
            fontsize=12,
            fontweight="bold",
            y=0.98,
        )
    else:
        fig, axes = plt.subplots(1, n_part, figsize=(6.0 * n_part, 5.2), dpi=300, sharey=True)
        axes_list: Sequence[Axes] = cast(Sequence[Axes], [axes] if n_part == 1 else list(axes))  # pyright: ignore[reportUnknownArgumentType]
        for idx, res in enumerate(results):
            _render_participant_axis(
                axes_list[idx],
                res,
                seed=seed,
                n_draws=n_draws,
                is_simulated=is_simulated,
                simulated_error_rate=simulated_error_rate,
            )
            if idx > 0:
                axes_list[idx].set_ylabel("")
        fig.suptitle(
            suptitle,
            fontsize=13,
            fontweight="bold",
            y=0.98,
        )

    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    fig.savefig(out_svg, bbox_inches="tight")
    plt.close(fig)

    return (out_png, out_svg)


def build_validation_audit_payload(
    session: Session,
    overview: Overview,
    results: ParticipantResults,
    *,
    is_simulated: bool,
    simulated_error_rate: float | None,
) -> dict[str, Any]:
    """Build deterministic JSON audit payload for `typist check-readme` verification."""
    p_sessions = session.exec(
        select(TypingSession.id).where(
            TypingSession.participant_id == results.participant_id,
            col(TypingSession.status) == "completed",
        )
    ).all()
    total_sessions = len(p_sessions)
    if p_sessions:
        total_keystrokes = int(
            session.exec(
                select(sa.func.count())
                .select_from(KeystrokeEvent)
                .join(SessionBlock, col(KeystrokeEvent.block_id) == col(SessionBlock.id))
                .where(col(SessionBlock.session_id).in_(p_sessions))
            ).one()
            or 0
        )
    else:
        total_keystrokes = 0

    return {
        "participant_id": results.participant_id,
        "alias": results.alias,
        "is_simulated": is_simulated,
        "simulated_error_rate": simulated_error_rate,
        "completed_sessions": total_sessions,
        "total_keystrokes": total_keystrokes,
        "generation_table": format_generation_table(overview),
        "overhead_line": format_overhead_line(overview),
        "limitations_paragraph": format_limitations_paragraph(
            session, overview, pid=results.participant_id
        ),
        "arms": [
            {
                "arm": a.arm,
                "drills_count": a.drills_count,
                "attempts_count": a.attempts_count,
                "acceptance_rate": a.acceptance_rate,
                "mean_target_density": a.mean_target_density,
                "mean_real_word_ratio": a.mean_real_word_ratio,
                "tokens_per_sec": a.tokens_per_sec,
            }
            for a in overview.generation.arms
        ],
        "sets": [
            {
                "set_label": s.set_label,
                "arm": s.arm,
                "bigrams": list(s.bigrams),
                "baseline_errors": s.baseline_errors,
                "baseline_attempts": s.baseline_attempts,
                "baseline_error_rate": s.baseline_error_rate,
                "baseline_beta_ci_lower": s.baseline_beta_ci_lower,
                "baseline_beta_ci_upper": s.baseline_beta_ci_upper,
                "retest_errors": s.retest_errors,
                "retest_attempts": s.retest_attempts,
                "retest_error_rate": s.retest_error_rate,
                "retest_beta_ci_lower": s.retest_beta_ci_lower,
                "retest_beta_ci_upper": s.retest_beta_ci_upper,
                "error_rate_change": s.error_rate_change,
                "targeting_effect": s.targeting_effect,
                "posterior_effect_median": s.posterior_effect_median,
                "posterior_effect_ci_lower": s.posterior_effect_ci_lower,
                "posterior_effect_ci_upper": s.posterior_effect_ci_upper,
                "share_below_zero": s.share_below_zero,
                "baseline_iki_n": s.baseline_iki_n,
                "baseline_iki_median_ms": s.baseline_iki_median_ms,
                "baseline_iki_iqr_ms": s.baseline_iki_iqr_ms,
                "retest_iki_n": s.retest_iki_n,
                "retest_iki_median_ms": s.retest_iki_median_ms,
                "retest_iki_iqr_ms": s.retest_iki_iqr_ms,
                "iki_change_ms": s.iki_change_ms,
                "iki_targeting_effect_ms": s.iki_targeting_effect_ms,
                "iki_bootstrap_ci_lower_ms": s.iki_bootstrap_ci_lower_ms,
                "iki_bootstrap_ci_upper_ms": s.iki_bootstrap_ci_upper_ms,
            }
            for s in results.sets
        ],
    }


def generate_all_figures(
    session: Session,
    out_dir: Path | None = None,
    pid: str | None = None,
    *,
    seed: int = DEFAULT_SEED,
    n_draws: int = DEFAULT_POSTERIOR_DRAWS,
    n_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
) -> FigureArtifacts:
    """Generate all figures and README snippets for completed participants."""
    dest_dir = out_dir if out_dir is not None else DEFAULT_FIGURES_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)

    overview = overview_report(session)

    if pid is not None:
        p_record = next((p for p in overview.participants if p.id == pid), None)
        if p_record is None:
            raise ParticipantNotFoundError(f"no participant with id {pid!r}")
        if p_record.status != "done":
            raise ParticipantNotDoneError(
                f"participant {pid!r} status is {p_record.status!r}, expected 'done'"
            )
        completed_pids = [pid]
    else:
        completed_pids = [p.id for p in overview.participants if p.status == "done"]
        if not completed_pids:
            raise ParticipantNotDoneError("no completed participants found (status 'done')")

    is_sim, sim_error_rate = is_simulated_study(session, completed_pids)

    results_list: list[ParticipantResults] = []
    for cur_pid in completed_pids:
        results = participant_results(
            session, cur_pid, seed=seed, n_draws=n_draws, n_resamples=n_resamples
        )
        results_list.append(results)

    # 1. Primary multi-panel or single chart: set_error_rate_change.png and .svg
    primary_png = dest_dir / "set_error_rate_change.png"
    primary_svg = dest_dir / "set_error_rate_change.svg"
    plot_set_error_rate_change(
        results_list,
        primary_png,
        primary_svg,
        seed=seed,
        n_draws=n_draws,
        is_simulated=is_sim,
        simulated_error_rate=sim_error_rate,
    )

    # 2. Individual participant charts if more than 1 participant
    participant_figures: list[tuple[str, Path, Path]] = []
    if len(results_list) > 1:
        for res in results_list:
            alias_png = dest_dir / f"set_error_rate_change_{res.alias}.png"
            alias_svg = dest_dir / f"set_error_rate_change_{res.alias}.svg"
            plot_set_error_rate_change(
                [res],
                alias_png,
                alias_svg,
                seed=seed,
                n_draws=n_draws,
                is_simulated=is_sim,
                simulated_error_rate=sim_error_rate,
            )
            participant_figures.append((res.alias, alias_png, alias_svg))
    else:
        participant_figures.append((results_list[0].alias, primary_png, primary_svg))

    target_res = results_list[0]
    for r in results_list:
        if r.alias in ("pilot-builder", "sim-validation") or r.alias.startswith("sim-"):
            target_res = r
            break

    target_sim, target_err = is_simulated_study(session, [target_res.participant_id])
    target_overview = overview_report(session, participant_id=target_res.participant_id)

    # 3. README snippets markdown
    snippets_md = format_readme_snippets(session, target_overview, pid=target_res.participant_id)
    snippets_path = dest_dir / "readme_snippets.md"
    snippets_path.write_text(snippets_md, encoding="utf-8")

    # 4. Machine-readable audit snapshot for deterministic README verification
    audit_payload = build_validation_audit_payload(
        session,
        target_overview,
        target_res,
        is_simulated=target_sim,
        simulated_error_rate=target_err,
    )
    audit_path = dest_dir / "validation_audit.json"
    audit_path.write_text(json.dumps(audit_payload, indent=2) + "\n", encoding="utf-8")

    return FigureArtifacts(
        primary_png=primary_png,
        primary_svg=primary_svg,
        participant_figures=participant_figures,
        readme_snippets_path=snippets_path,
        snippets_markdown=snippets_md,
        validation_audit_path=audit_path,
    )
