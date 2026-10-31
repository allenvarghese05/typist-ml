"""Daily data quality checks and drill pool status computations (design doc 12.6, 13.7, 14; T2.9).

Pure queries and aggregations over SQLite. Routers remain thin; all check algorithms live here.
Daily checks detect sequence gaps, negative/excessive dwell, short blocks, missing keyup share,
and lingering in_progress sessions. Also generates the daily session trend view (Owner decision #5).
"""

from typing import Final

import sqlalchemy as sa
from sqlmodel import Session, col, select

from typist.models import (
    BigramAssignment,
    BigramStat,
    Drill,
    GenerationJob,
    KeystrokeEvent,
    Participant,
    SessionBlock,
)
from typist.models import Session as TypingSession
from typist.schemas.admin import (
    ArmPoolStatus,
    CheckDetail,
    ChecksResponse,
    DataChecksResult,
    DwellCheckDetail,
    MissingKeyupsDetail,
    PoolResponse,
    SessionTrendEntry,
)
from typist.services.participants import ParticipantNotFoundError
from typist.services.session_planner import load_planner_config

MISSING_KEYUP_TOLERANCE_SHARE: Final[float] = 0.05
"""Share of missing keyup events above which the missing_keyups check fails (Owner answer 2)."""


def get_participant_pool_status(session: Session, participant_id: str) -> PoolResponse:
    """Compute ready, queued, used counts and deficit per arm for a participant."""
    participant = session.get(Participant, participant_id)
    if participant is None:
        raise ParticipantNotFoundError(participant_id)

    config = load_planner_config(session)
    target = config.pool_target_drills
    arm_statuses: list[ArmPoolStatus] = []

    for arm in config.arms:
        ready_count = int(
            session.exec(
                select(sa.func.count())
                .select_from(Drill)
                .where(
                    col(Drill.participant_id) == participant_id,
                    col(Drill.arm) == arm,
                    col(Drill.status) == "ready",
                )
            ).one()
        )
        queued_count = int(
            session.exec(
                select(sa.func.coalesce(sa.func.sum(GenerationJob.requested), 0)).where(
                    col(GenerationJob.participant_id) == participant_id,
                    col(GenerationJob.arm) == arm,
                    col(GenerationJob.status).in_(("pending", "running")),
                )
            ).one()
        )
        used_count = int(
            session.exec(
                select(sa.func.count())
                .select_from(Drill)
                .where(
                    col(Drill.participant_id) == participant_id,
                    col(Drill.arm) == arm,
                    col(Drill.status) == "used",
                )
            ).one()
        )
        deficit = max(0, target - (ready_count + queued_count))
        is_ready = ready_count >= target

        arm_statuses.append(
            ArmPoolStatus(
                arm=arm,
                ready_count=ready_count,
                target_count=target,
                queued_count=queued_count,
                used_count=used_count,
                deficit=deficit,
                is_ready=is_ready,
            )
        )

    return PoolResponse(
        participant_id=participant.id,
        alias=participant.alias,
        arms=arm_statuses,
    )


def get_all_pools_status(session: Session) -> list[PoolResponse]:
    """Compute pool status across all non-withdrawn participants."""
    participants = session.exec(
        select(Participant)
        .where(col(Participant.status) != "withdrawn")
        .order_by(col(Participant.alias))
    ).all()
    return [get_participant_pool_status(session, p.id) for p in participants]


def run_participant_checks(session: Session, participant_id: str) -> ChecksResponse:
    """Execute the 5 daily data quality checks and build session trend entries for a participant."""
    participant = session.get(Participant, participant_id)
    if participant is None:
        raise ParticipantNotFoundError(participant_id)

    # 1. Sequence gaps check
    blocks = session.exec(
        select(SessionBlock)
        .join(TypingSession, col(SessionBlock.session_id) == col(TypingSession.id))
        .where(col(TypingSession.participant_id) == participant_id)
    ).all()

    gap_count = 0
    gap_details: list[str] = []
    for block in blocks:
        events = session.exec(
            select(KeystrokeEvent.seq)
            .where(col(KeystrokeEvent.block_id) == block.id)
            .order_by(col(KeystrokeEvent.seq).asc())
        ).all()
        if not events:
            continue
        if events[0] != 0:
            gap_count += 1
            gap_details.append(
                f"block {block.id} (session {block.session_id}): starts at seq {events[0]} instead of 0"
            )
            continue
        for i in range(1, len(events)):
            if events[i] != events[i - 1] + 1:
                gap_count += 1
                gap_details.append(
                    f"block {block.id} (session {block.session_id}): gap between seq {events[i - 1]} and {events[i]}"
                )
                break

    seq_gaps = CheckDetail(
        passed=gap_count == 0,
        count=gap_count,
        details=gap_details,
    )

    # 2. Dwell anomalies check (< 0 or > 1000ms)
    dwells = session.exec(
        select(KeystrokeEvent.dwell_ms)
        .join(SessionBlock, col(KeystrokeEvent.block_id) == col(SessionBlock.id))
        .join(TypingSession, col(SessionBlock.session_id) == col(TypingSession.id))
        .where(
            col(TypingSession.participant_id) == participant_id,
            col(KeystrokeEvent.dwell_ms).is_not(None),
        )
    ).all()

    negative_count = sum(1 for d in dwells if d is not None and d < 0)
    over_1000ms_count = sum(1 for d in dwells if d is not None and d > 1000.0)
    dwell_details: list[str] = []
    if negative_count > 0:
        dwell_details.append(f"{negative_count} event(s) with negative dwell (< 0 ms)")
    if over_1000ms_count > 0:
        dwell_details.append(f"{over_1000ms_count} event(s) with dwell > 1000 ms (stuck key)")

    dwell_anomalies = DwellCheckDetail(
        passed=(negative_count == 0 and over_1000ms_count == 0),
        negative_count=negative_count,
        over_1000ms_count=over_1000ms_count,
        details=dwell_details,
    )

    # 3. Short blocks check (completed sessions with fewer events than target_text)
    completed_blocks = session.exec(
        select(SessionBlock)
        .join(TypingSession, col(SessionBlock.session_id) == col(TypingSession.id))
        .where(
            col(TypingSession.participant_id) == participant_id,
            col(TypingSession.status) == "completed",
        )
    ).all()

    short_count = 0
    short_details: list[str] = []
    for block in completed_blocks:
        target_len = len(block.target_text)
        event_count = int(
            session.exec(
                select(sa.func.count())
                .select_from(KeystrokeEvent)
                .where(col(KeystrokeEvent.block_id) == block.id)
            ).one()
        )
        if event_count < target_len:
            short_count += 1
            short_details.append(
                f"block {block.id} (session {block.session_id}): {event_count} events < {target_len} target chars"
            )

    short_blocks = CheckDetail(
        passed=short_count == 0,
        count=short_count,
        details=short_details,
    )

    # 4. Missing keyups check
    total_events = int(
        session.exec(
            select(sa.func.count())
            .select_from(KeystrokeEvent)
            .join(SessionBlock, col(KeystrokeEvent.block_id) == col(SessionBlock.id))
            .join(TypingSession, col(SessionBlock.session_id) == col(TypingSession.id))
            .where(col(TypingSession.participant_id) == participant_id)
        ).one()
    )
    missing_keyups_count = int(
        session.exec(
            select(sa.func.count())
            .select_from(KeystrokeEvent)
            .join(SessionBlock, col(KeystrokeEvent.block_id) == col(SessionBlock.id))
            .join(TypingSession, col(SessionBlock.session_id) == col(TypingSession.id))
            .where(
                col(TypingSession.participant_id) == participant_id,
                col(KeystrokeEvent.t_up_ms).is_(None),
            )
        ).one()
    )
    missing_share = (missing_keyups_count / total_events) if total_events > 0 else 0.0
    missing_passed = missing_share <= MISSING_KEYUP_TOLERANCE_SHARE
    missing_details = [
        f"{missing_keyups_count}/{total_events} missing keyup(s) ({missing_share * 100:.2f}%; limit {MISSING_KEYUP_TOLERANCE_SHARE * 100:.0f}%)"
    ]
    missing_keyups = MissingKeyupsDetail(
        passed=missing_passed,
        total_events=total_events,
        missing_count=missing_keyups_count,
        missing_share=round(missing_share, 4),
        details=missing_details,
    )

    # 5. In-progress sessions check
    in_progress = session.exec(
        select(TypingSession)
        .where(
            col(TypingSession.participant_id) == participant_id,
            col(TypingSession.status) == "in_progress",
        )
        .order_by(col(TypingSession.started_at).asc())
    ).all()
    in_progress_count = len(in_progress)
    in_progress_details = [
        f"session {s.id} (day {s.day_index}, phase {s.phase}, started {s.started_at.isoformat()}) left in_progress"
        for s in in_progress
    ]
    in_progress_sessions = CheckDetail(
        passed=in_progress_count == 0,
        count=in_progress_count,
        details=in_progress_details,
    )

    overall_passed = (
        seq_gaps.passed
        and dwell_anomalies.passed
        and short_blocks.passed
        and missing_keyups.passed
        and in_progress_sessions.passed
    )

    # Session trends
    trend_entries = participant_session_trend(session, participant_id)

    return ChecksResponse(
        participant_id=participant.id,
        alias=participant.alias,
        status=participant.status,
        passed=overall_passed,
        checks=DataChecksResult(
            seq_gaps=seq_gaps,
            dwell_anomalies=dwell_anomalies,
            short_blocks=short_blocks,
            missing_keyups=missing_keyups,
            in_progress_sessions=in_progress_sessions,
        ),
        trend=trend_entries,
    )


def participant_session_trend(session: Session, participant_id: str) -> list[SessionTrendEntry]:
    """Build session trend entries for a participant's completed sessions."""
    participant = session.get(Participant, participant_id)
    if participant is None:
        raise ParticipantNotFoundError(participant_id)

    completed_sessions = session.exec(
        select(TypingSession)
        .where(
            col(TypingSession.participant_id) == participant_id,
            col(TypingSession.status) == "completed",
        )
        .order_by(col(TypingSession.started_at).asc(), col(TypingSession.id).asc())
    ).all()

    assignments = session.exec(
        select(BigramAssignment).where(col(BigramAssignment.participant_id) == participant_id)
    ).all()
    bigram_to_set = {a.bigram: a.set_label for a in assignments}
    all_set_labels = sorted({a.set_label for a in assignments})

    trend_entries: list[SessionTrendEntry] = []
    for s in completed_sessions:
        stats = session.exec(select(BigramStat).where(col(BigramStat.session_id) == s.id)).all()
        per_set_attempts: dict[str, int] = {label: 0 for label in all_set_labels}
        per_set_errors: dict[str, int] = {label: 0 for label in all_set_labels}
        for stat in stats:
            set_label = bigram_to_set.get(stat.bigram)
            if set_label is not None:
                per_set_attempts[set_label] += stat.attempts
                per_set_errors[set_label] += stat.errors

        per_set_error_rate: dict[str, float | None] = {}
        for label in all_set_labels:
            att = per_set_attempts[label]
            err = per_set_errors[label]
            per_set_error_rate[label] = round(err / att, 4) if att > 0 else None

        trend_entries.append(
            SessionTrendEntry(
                session_id=s.id,
                phase=s.phase,
                day_index=s.day_index,
                started_at=s.started_at,
                wpm=s.wpm,
                accuracy=s.accuracy,
                per_set_error_rate=per_set_error_rate,
                per_set_attempts=per_set_attempts,
                per_set_errors=per_set_errors,
            )
        )
    return trend_entries

