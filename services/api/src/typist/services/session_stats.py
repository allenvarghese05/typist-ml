"""Session completion: WPM, accuracy and bigram_stats from raw keystrokes (design doc 12.3, 14; T1.9).

The one place session-level stats are computed (CLAUDE.md "one source of truth"). Pure functions
(block_elapsed_ms, session_metrics, merge_bigram_samples) do the maths; compute_session_stats only
reads; write_session_stats deletes-and-reinserts one session's bigram_stats and updates its
wpm/accuracy in one transaction; complete_session adds the 404/409 lifecycle and marks the session;
recompute_stats rebuilds every completed session. Attribution (D24/D23(a)) is reused unchanged via
attribute_block_samples: this module only pools a session's blocks (sum attempts/errors, concat raw
IKI samples, then one statistics.median -- NOT a median of medians; T1.7 answer 3). WPM uses D26's
elapsed-time base: per-block elapsed (last press - first press) summed across blocks, pauses and
blur included; correct-first-attempt characters / 5 / elapsed minutes.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from statistics import median

from sqlmodel import Session, col, delete, select

from typist.models import BigramStat, KeystrokeEvent, SessionBlock
from typist.models import Session as TypingSession
from typist.services.attribution import (
    BigramSamples,
    attribute_block_samples,
)
from typist.services.attribution import (
    BigramStat as ComputedBigramStat,
)

CHARS_PER_WORD = 5.0
"""Design doc 12.3 / D26 word length for WPM. A design constant, not an experiment_config knob."""

MS_PER_MINUTE = 60000.0
"""Milliseconds per minute for WPM. A design constant, not an experiment_config knob."""


class SessionNotFoundError(LookupError):
    """No sessions row has the given id (the endpoint turns this into 404)."""


class SessionNotInProgressError(RuntimeError):
    """complete_session was called on a session whose status is not 'in_progress' (409)."""


@dataclass(frozen=True)
class BlockMetrics:
    """Per-block inputs to session_metrics: summed, never divided at block level."""

    correct_first_attempts: int
    first_attempts: int
    elapsed_ms: float


@dataclass(frozen=True)
class SessionMetrics:
    """Session WPM and accuracy; either is None when its denominator is undefined (owner answer 5)."""

    wpm: float | None
    accuracy: float | None


@dataclass(frozen=True)
class SessionStats:
    """The full derived result for one session: metrics, block count, and bigram rows sorted by bigram."""

    wpm: float | None
    accuracy: float | None
    block_count: int
    bigrams: tuple[ComputedBigramStat, ...]


@dataclass(frozen=True)
class RecomputeResult:
    """How many sessions recompute rebuilt versus skipped (not completed)."""

    recomputed: int
    skipped: int


def block_elapsed_ms(rows: Sequence[KeystrokeEvent]) -> float:
    """Elapsed time of one block per D26: last row's press minus the first row's press, by seq.

    Pauses and blur are included (D26). Returns 0.0 for fewer than two rows (no span to measure).
    Rows may arrive in any order; they are ordered by seq. D26's two cases ("final character" and
    "last row" when unfinished) are the same press time here, so no target_text is needed.
    """
    if len(rows) < 2:
        return 0.0
    ordered = sorted(rows, key=lambda row: row.seq)
    return ordered[-1].t_down_ms - ordered[0].t_down_ms


def session_metrics(blocks: Sequence[BlockMetrics]) -> SessionMetrics:
    """Pool per-block counts and elapsed time into session WPM and accuracy (D26, owner answers 2/5).

    WPM = total correct first-attempt characters / CHARS_PER_WORD / total elapsed minutes, where
    total elapsed is the sum of per-block elapsed (between-block time is not typing). accuracy =
    total correct first attempts / total first attempts. wpm is None when total elapsed <= 0 or
    total correct == 0; accuracy is None when total first attempts == 0 (no zeros stored).
    """
    total_correct = sum(b.correct_first_attempts for b in blocks)
    total_first = sum(b.first_attempts for b in blocks)
    total_elapsed_ms = sum(b.elapsed_ms for b in blocks)
    accuracy = total_correct / total_first if total_first > 0 else None
    if total_elapsed_ms > 0.0 and total_correct > 0:
        wpm = total_correct / CHARS_PER_WORD / (total_elapsed_ms / MS_PER_MINUTE)
    else:
        wpm = None
    return SessionMetrics(wpm=wpm, accuracy=accuracy)


def merge_bigram_samples(
    per_block: Sequence[Mapping[str, BigramSamples]],
) -> dict[str, BigramSamples]:
    """Pool a session's per-block attribution: union bigrams, sum counts, concatenate IKI samples.

    per_block is the attribute_block_samples output for each block, in block order. For each
    bigram seen in any block: attempts and errors are summed; iki_samples are concatenated in block
    order (so one statistics.median can later be taken over the pooled list -- NOT a median of
    medians; T1.7 answer 3). Order never affects the result (sums and a median are order-free).
    """
    attempts: dict[str, int] = {}
    errors: dict[str, int] = {}
    samples: dict[str, list[float]] = {}
    for block in per_block:
        for bigram, entry in block.items():
            attempts[bigram] = attempts.get(bigram, 0) + entry.attempts
            errors[bigram] = errors.get(bigram, 0) + entry.errors
            samples.setdefault(bigram, []).extend(entry.iki_samples)
    return {
        bigram: BigramSamples(
            bigram=bigram,
            attempts=count,
            errors=errors[bigram],
            iki_samples=tuple(samples[bigram]),
        )
        for bigram, count in attempts.items()
    }


def _block_metrics(rows: Sequence[KeystrokeEvent]) -> BlockMetrics:
    """First-attempt counts (non-backspace rows) and elapsed time for one block's rows."""
    first = [row for row in rows if row.first_attempt]
    correct = sum(1 for row in first if row.outcome == "correct")
    return BlockMetrics(
        correct_first_attempts=correct,
        first_attempts=len(first),
        elapsed_ms=block_elapsed_ms(rows),
    )


def compute_session_stats(session: Session, session_id: str) -> SessionStats:
    """Read one session's blocks and rows and compute its WPM, accuracy and pooled bigram stats.

    Reads only (no writes). Blocks are read in block_index order; each block's rows are attributed
    with attribute_block_samples and its first-attempt counts and elapsed time measured. Bigram
    samples are pooled across blocks, then one statistics.median per bigram gives iki_median_ms
    (None when iki_n == 0). bigrams is sorted by bigram. Raises SessionNotFoundError if the
    session does not exist.
    """
    if session.get(TypingSession, session_id) is None:
        raise SessionNotFoundError(session_id)
    blocks = session.exec(
        select(SessionBlock)
        .where(col(SessionBlock.session_id) == session_id)
        .order_by(col(SessionBlock.block_index))
    ).all()
    block_metrics: list[BlockMetrics] = []
    per_block: list[Mapping[str, BigramSamples]] = []
    for block in blocks:
        rows = session.exec(
            select(KeystrokeEvent).where(col(KeystrokeEvent.block_id) == block.id)
        ).all()
        block_metrics.append(_block_metrics(rows))
        per_block.append(attribute_block_samples(block.target_text, rows))
    metrics = session_metrics(block_metrics)
    pooled = merge_bigram_samples(per_block)
    bigrams = tuple(
        ComputedBigramStat(
            bigram=bigram,
            attempts=pooled[bigram].attempts,
            errors=pooled[bigram].errors,
            iki_median_ms=(
                median(pooled[bigram].iki_samples) if pooled[bigram].iki_samples else None
            ),
            iki_n=len(pooled[bigram].iki_samples),
        )
        for bigram in sorted(pooled)
    )
    return SessionStats(
        wpm=metrics.wpm,
        accuracy=metrics.accuracy,
        block_count=len(blocks),
        bigrams=bigrams,
    )


def write_session_stats(session: Session, session_id: str, stats: SessionStats) -> None:
    """Delete-and-reinsert one session's bigram_stats and set its wpm/accuracy, in one transaction.

    Idempotent: deletes every bigram_stats row for session_id, inserts the computed rows (with the
    session's participant_id), sets sessions.wpm/accuracy, and commits once. Any uncommitted
    session-row changes already staged (e.g. status/ended_at) are committed in the same transaction.
    Raises SessionNotFoundError if the session does not exist.
    """
    row = session.get(TypingSession, session_id)
    if row is None:
        raise SessionNotFoundError(session_id)
    session.exec(delete(BigramStat).where(col(BigramStat.session_id) == session_id))
    for stat in stats.bigrams:
        session.add(
            BigramStat(
                participant_id=row.participant_id,
                session_id=session_id,
                bigram=stat.bigram,
                attempts=stat.attempts,
                errors=stat.errors,
                iki_median_ms=stat.iki_median_ms,
                iki_n=stat.iki_n,
            )
        )
    row.wpm = stats.wpm
    row.accuracy = stats.accuracy
    session.add(row)
    session.commit()


def complete_session(session: Session, session_id: str, now: datetime) -> SessionStats:
    """Complete an in-progress session: compute stats, mark it completed, write everything atomically.

    Raises SessionNotFoundError (404) if the session does not exist, SessionNotInProgressError
    (409) if its status is not 'in_progress'. Otherwise computes stats, stages status='completed'
    and ended_at=now on the session row, then write_session_stats commits status, ended_at, wpm,
    accuracy and the fresh bigram_stats in one transaction. Returns the SessionStats (the router
    builds SessionSummary). Block started_at/ended_at are not touched (block endpoints are later).
    """
    row = session.get(TypingSession, session_id)
    if row is None:
        raise SessionNotFoundError(session_id)
    if row.status != "in_progress":
        raise SessionNotInProgressError(session_id)
    stats = compute_session_stats(session, session_id)
    row.status = "completed"
    row.ended_at = now
    session.add(row)
    write_session_stats(session, session_id, stats)
    return stats


def recompute_stats(session: Session, participant_id: str | None = None) -> RecomputeResult:
    """Rebuild bigram_stats and wpm/accuracy for every completed session (optionally one participant).

    Processes only sessions with status == 'completed' (owner answer 6); others are counted as
    skipped and left untouched (status/ended_at are never changed by recompute). Each completed
    session is recomputed and written in its own transaction (write_session_stats commits per
    session), so the rebuild is deterministic and idempotent (acceptance). If participant_id is
    given, only that participant's sessions are considered.
    """
    query = select(TypingSession)
    if participant_id is not None:
        query = query.where(col(TypingSession.participant_id) == participant_id)
    recomputed = 0
    skipped = 0
    for row in session.exec(query).all():
        if row.status != "completed":
            skipped += 1
            continue
        stats = compute_session_stats(session, row.id)
        write_session_stats(session, row.id, stats)
        recomputed += 1
    return RecomputeResult(recomputed=recomputed, skipped=skipped)
