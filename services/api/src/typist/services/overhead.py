"""Instrumentation-overhead percentiles for `typist overhead` (design doc 12.5, 14.1; T1.10).

handler_ms and dispatch_lag_ms are recorded non-null on every keystroke_events row (section 12.5).
This module reports their p50/p95/p99 per session, plus a pooled "all" row. It only reads; it never
writes. The percentile method is fixed here so the published resume number is reproducible:
statistics.quantiles(values, n=100, method="inclusive"), with p50 = q[49], p95 = q[94], p99 = q[98]
(linear interpolation on the inclusive definition, matching numpy's default "linear"; no numpy
dependency). A single value is its own p50/p95/p99; an empty list has no percentiles (None).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import quantiles

from sqlmodel import Session, col, select

from typist.models import KeystrokeEvent, SessionBlock
from typist.models import Session as TypingSession


@dataclass(frozen=True)
class Percentiles:
    """p50, p95 and p99 of one metric (milliseconds)."""

    p50: float
    p95: float
    p99: float


@dataclass(frozen=True)
class SessionOverhead:
    """One printed row: a session (or the pooled "all" row) and its two metrics' percentiles.

    handler and dispatch are None when the session has no keystroke rows (nothing to measure).
    For the pooled row, session_id and participant_id are the literal string "all".
    """

    session_id: str
    participant_id: str
    events: int
    handler: Percentiles | None
    dispatch: Percentiles | None


def percentiles(values: Sequence[float]) -> Percentiles | None:
    """Return p50/p95/p99 of values by the inclusive-quantile method, or None if values is empty.

    One value is its own p50/p95/p99 (statistics.quantiles needs at least two). Otherwise
    q = quantiles(values, n=100, method="inclusive") and the percentiles are q[49], q[94], q[98].
    """
    if len(values) == 0:
        return None
    if len(values) == 1:
        only = values[0]
        return Percentiles(p50=only, p95=only, p99=only)
    q = quantiles(values, n=100, method="inclusive")
    return Percentiles(p50=q[49], p95=q[94], p99=q[98])


def overhead_report(
    session: Session,
    participant_id: str | None,
    session_id: str | None,
) -> list[SessionOverhead]:
    """Build one SessionOverhead per matching session plus a pooled "all" row (owner answer 2).

    Filter: session_id given -> only that session; else participant_id given -> that participant's
    sessions; else every session. Sessions are ordered by started_at then id (deterministic print).
    For each session, handler_ms and dispatch_lag_ms are read from its keystroke_events (joined
    through session_blocks) and reduced to percentiles (None when the session has no rows). The
    final "all" row pools every selected session's samples. Reads only.
    """
    query = select(TypingSession)
    if session_id is not None:
        query = query.where(col(TypingSession.id) == session_id)
    elif participant_id is not None:
        query = query.where(col(TypingSession.participant_id) == participant_id)
    query = query.order_by(col(TypingSession.started_at), col(TypingSession.id))
    rows: list[SessionOverhead] = []
    pooled_handler: list[float] = []
    pooled_dispatch: list[float] = []
    for typing_session in session.exec(query).all():
        samples = session.exec(
            select(KeystrokeEvent.handler_ms, KeystrokeEvent.dispatch_lag_ms)
            .join(SessionBlock, col(KeystrokeEvent.block_id) == col(SessionBlock.id))
            .where(col(SessionBlock.session_id) == typing_session.id)
        ).all()
        handler = [row[0] for row in samples]
        dispatch = [row[1] for row in samples]
        pooled_handler.extend(handler)
        pooled_dispatch.extend(dispatch)
        rows.append(
            SessionOverhead(
                session_id=typing_session.id,
                participant_id=typing_session.participant_id,
                events=len(samples),
                handler=percentiles(handler),
                dispatch=percentiles(dispatch),
            )
        )
    rows.append(
        SessionOverhead(
            session_id="all",
            participant_id="all",
            events=len(pooled_handler),
            handler=percentiles(pooled_handler),
            dispatch=percentiles(pooled_dispatch),
        )
    )
    return rows


_HEADER = "session  participant  events  handler p50/p95/p99  dispatch p50/p95/p99"


def _fmt(p: Percentiles | None) -> str:
    """Format one metric as 'p50/p95/p99' to 3 decimals, or '-/-/-' when there are no samples."""
    if p is None:
        return "-/-/-"
    return f"{p.p50:.3f}/{p.p95:.3f}/{p.p99:.3f}"


def format_report(rows: Sequence[SessionOverhead]) -> str:
    """Render the overhead rows as the printed table (header + one line per row).

    Milliseconds, 3 decimals; sessions with no samples print '-/-/-'. The "all" row is last.
    """
    lines = [_HEADER]
    for row in rows:
        lines.append(
            f"{row.session_id}  {row.participant_id}  {row.events}  "
            f"{_fmt(row.handler)}  {_fmt(row.dispatch)}"
        )
    return "\n".join(lines)
