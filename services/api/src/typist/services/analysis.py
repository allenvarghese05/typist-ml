"""Dashboard analysis reads (design doc 15.2; T1.10). session_matrix serves GET .../matrix.

Reads bigram_stats for one completed session and returns a BigramMatrix; it never re-attributes
(CLAUDE.md "one source of truth"). 404 (SessionNotFoundError, reused from session_stats) when the
session does not exist; 409 (SessionNotCompletedError) when its status is not 'completed' -- no
stats have been written yet (bigram_stats exists only for completed sessions; owner answers 1, 8).
"""

from collections.abc import Sequence
from statistics import fmean

from sqlmodel import Session, col, select

from typist.models import BigramAssignment, BigramStat, Participant
from typist.models import Session as TypingSession
from typist.schemas.analysis import BigramMatrix, MatrixCell, ParticipantResults, SetOutcome
from typist.services.participants import ParticipantNotFoundError
from typist.services.session_stats import SessionNotFoundError
from typist.services.test_composer import ParticipantNotAssignedError


class SessionNotCompletedError(RuntimeError):
    """The session exists but its status is not 'completed' (the endpoint returns 409)."""


class ParticipantNotDoneError(RuntimeError):
    """The participant exists but has not completed the study (status is not 'done')."""


def session_matrix(session: Session, session_id: str) -> BigramMatrix:
    """Build the BigramMatrix for one completed session from its bigram_stats rows.

    Raises SessionNotFoundError if the session does not exist, SessionNotCompletedError if its
    status is not 'completed'. Cells are ordered by bigram; error_rate = errors/attempts (None if
    attempts == 0, which never happens for a stored row but is guarded anyway). Reads only.
    """
    row = session.get(TypingSession, session_id)
    if row is None:
        raise SessionNotFoundError(session_id)
    if row.status != "completed":
        raise SessionNotCompletedError(session_id)
    stats = session.exec(
        select(BigramStat)
        .where(col(BigramStat.session_id) == session_id)
        .order_by(col(BigramStat.bigram))
    ).all()
    cells = [
        MatrixCell(
            bigram=stat.bigram,
            attempts=stat.attempts,
            errors=stat.errors,
            error_rate=(stat.errors / stat.attempts if stat.attempts > 0 else None),
            iki_median_ms=stat.iki_median_ms,
            iki_n=stat.iki_n,
        )
        for stat in stats
    ]
    return BigramMatrix(
        session_id=session_id,
        participant_id=row.participant_id,
        phase=row.phase,
        wpm=row.wpm,
        accuracy=row.accuracy,
        cells=cells,
    )


def participant_results(session: Session, participant_id: str) -> ParticipantResults:
    """Build ParticipantResults for a participant who has completed the study.

    Raises ParticipantNotFoundError if the participant does not exist,
    ParticipantNotDoneError if participant status is not 'done',
    and ParticipantNotAssignedError if there are no frozen bigram assignments.
    Reads bigram_stats across baseline and retest sessions.
    """
    participant = session.get(Participant, participant_id)
    if participant is None:
        raise ParticipantNotFoundError(participant_id)
    if participant.status != "done":
        raise ParticipantNotDoneError(
            f"participant {participant_id!r} status is {participant.status!r}, expected 'done'"
        )

    assignments = session.exec(
        select(BigramAssignment)
        .where(col(BigramAssignment.participant_id) == participant_id)
        .order_by(col(BigramAssignment.set_label), col(BigramAssignment.baseline_rank))
    ).all()
    if not assignments:
        raise ParticipantNotAssignedError(
            f"participant {participant_id!r} has no frozen assignments"
        )

    set_labels = sorted({a.set_label for a in assignments})
    bigram_to_set = {a.bigram: a.set_label for a in assignments}
    set_to_arm = {a.set_label: a.arm for a in assignments}
    set_to_bigrams: dict[str, list[str]] = {label: [] for label in set_labels}
    for a in assignments:
        set_to_bigrams[a.set_label].append(a.bigram)

    completed_sessions = session.exec(
        select(TypingSession).where(
            col(TypingSession.participant_id) == participant_id,
            col(TypingSession.status) == "completed",
        )
    ).all()

    baseline_sessions = [s for s in completed_sessions if s.phase == "baseline"]
    retest_sessions = [s for s in completed_sessions if s.phase == "retest"]

    baseline_wpms = [s.wpm for s in baseline_sessions if s.wpm is not None]
    retest_wpms = [s.wpm for s in retest_sessions if s.wpm is not None]
    baseline_wpm = round(fmean(baseline_wpms), 2) if baseline_wpms else None
    retest_wpm = round(fmean(retest_wpms), 2) if retest_wpms else None

    baseline_session_ids = {s.id for s in baseline_sessions}
    retest_session_ids = {s.id for s in retest_sessions}

    baseline_stats: Sequence[BigramStat] = (
        session.exec(
            select(BigramStat).where(col(BigramStat.session_id).in_(baseline_session_ids))
        ).all()
        if baseline_session_ids
        else []
    )
    retest_stats: Sequence[BigramStat] = (
        session.exec(
            select(BigramStat).where(col(BigramStat.session_id).in_(retest_session_ids))
        ).all()
        if retest_session_ids
        else []
    )

    baseline_counts: dict[str, dict[str, int]] = {
        label: {"attempts": 0, "errors": 0} for label in set_labels
    }
    for stat in baseline_stats:
        set_label = bigram_to_set.get(stat.bigram)
        if set_label is not None:
            baseline_counts[set_label]["attempts"] += stat.attempts
            baseline_counts[set_label]["errors"] += stat.errors

    retest_counts: dict[str, dict[str, int]] = {
        label: {"attempts": 0, "errors": 0} for label in set_labels
    }
    for stat in retest_stats:
        set_label = bigram_to_set.get(stat.bigram)
        if set_label is not None:
            retest_counts[set_label]["attempts"] += stat.attempts
            retest_counts[set_label]["errors"] += stat.errors

    sets: list[SetOutcome] = []
    for label in set_labels:
        b_att = baseline_counts[label]["attempts"]
        b_err = baseline_counts[label]["errors"]
        b_rate = round(b_err / b_att, 4) if b_att > 0 else None

        r_att = retest_counts[label]["attempts"]
        r_err = retest_counts[label]["errors"]
        r_rate = round(r_err / r_att, 4) if r_att > 0 else None

        sets.append(
            SetOutcome(
                set_label=label,
                arm=set_to_arm[label],
                bigrams=sorted(set_to_bigrams[label]),
                baseline_attempts=b_att,
                baseline_errors=b_err,
                baseline_error_rate=b_rate,
                retest_attempts=r_att,
                retest_errors=r_err,
                retest_error_rate=r_rate,
            )
        )

    return ParticipantResults(
        participant_id=participant_id,
        alias=participant.alias,
        status=participant.status,
        baseline_wpm=baseline_wpm,
        retest_wpm=retest_wpm,
        sets=sets,
    )
