"""Session planner: Latin square, drill pool selection, marking drills used, and pool replenishment
(design doc sections 3.3, 7, 8.1, 9.3, 10.1, 13.7, 14; D01, D02, D03, D11, D13, D18; T2.6).

Pure helpers (latin_square_arms, encode_block_order, block_label, resolve_session_phase) compute
the daily cyclic Latin square row, compact block_order string (e.g. 'LCHM'), blinded UI labels
('Block 1'..'Block 4'), and session phase without touching SQLite. plan_session builds baseline,
practice, and retest sessions: it returns an existing in_progress session if started <= 30 minutes
ago, or marks it 'abandoned' if > 30 minutes old (9.3); computes day_index (1 + all prior sessions
in phase; T1.1 owner answer 11) and rotates practice block order by completed practice sessions
(owner answer 1); selects ready drills in creation order (created_at ASC, id ASC), flushes
SessionBlock rows before setting drills.used_in_block_id (satisfying fk_drills_used_in_block_id_session_blocks),
and marks picked drills status='used' atomically in one transaction. replenish_drill_pool tops up
each enabled arm to 3 days of ready drills (6 drills per arm) by enqueueing deduplicated
generation_jobs rows.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import sqlalchemy as sa
from sqlmodel import Session, col, select

from typist.db import utc_now
from typist.models import (
    BigramAssignment,
    Drill,
    ExperimentConfig,
    GenerationJob,
    Participant,
    SessionBlock,
    TextPassage,
)
from typist.models import Session as TypingSession
from typist.models.sessions import SESSION_PHASES
from typist.services.participants import ParticipantNotFoundError
from typist.services.session_stats import SessionNotFoundError

POOL_TARGET_DAYS: Final[int] = 3
"""Target number of practice days of ready drills kept in the pool per arm (design doc 13.7)."""

STALE_SESSION_TIMEOUT: Final[timedelta] = timedelta(minutes=30)
"""Unfinished in_progress sessions older than 30 minutes become abandoned (design doc 9.3)."""

_PLANNER_INT_KEYS: Final[tuple[str, ...]] = (
    "block_chars",
    "drill_length_chars",
    "baseline_parts",
    "practice_days",
)

_STATUS_TO_PHASE: Final[dict[str, str]] = {
    "enrolled": "baseline",
    "baseline": "baseline",
    "assigned": "practice",
    "practice": "practice",
    "retest": "retest",
}


class SessionPlannerError(RuntimeError):
    """Base class for session planning errors that map to HTTP 409 Conflict."""


class InvalidSessionPhaseError(SessionPlannerError):
    """The participant's status or requested phase cannot start a session (409)."""


class PassageNotFoundError(SessionPlannerError):
    """The required baseline (form A) or retest (form B) passage part is missing or already completed (409)."""


class DrillPoolExhaustedError(SessionPlannerError):
    """One or more enabled arms have fewer ready drills than required to build a practice block (409)."""


class MissingConfigError(LookupError):
    """A required experiment_config key is absent (run migrations)."""


@dataclass(frozen=True)
class PlannerConfig:
    """experiment_config parameters used by session_planner."""

    arms: tuple[str, ...]
    block_chars: int
    drill_length_chars: int
    baseline_parts: int
    practice_days: int

    @property
    def drills_per_block(self) -> int:
        """Number of ready drills joined to form one practice block (600 // 300 == 2)."""
        return max(1, self.block_chars // self.drill_length_chars)

    @property
    def pool_target_drills(self) -> int:
        """Target ready drills per enabled arm (3 days * 2 drills/block == 6; section 13.7)."""
        return POOL_TARGET_DAYS * self.drills_per_block


@dataclass(frozen=True)
class PlannedBlock:
    """Blinded representation of one session block for the UI (D18, section 3.3, 9.2).

    Never includes arm or passage_id so the participant UI cannot see which arm a practice block
    belongs to.
    """

    block_id: str
    block_index: int
    label: str
    target_text: str
    started_at: datetime | None
    ended_at: datetime | None


@dataclass(frozen=True)
class PlannedSession:
    """Blinded session plan returned by plan_session and get_session_plan (D18, section 10.1, 14).

    Never includes sessions.block_order so the arm mapping stays hidden from the participant UI.
    """

    session_id: str
    participant_id: str
    phase: str
    day_index: int
    status: str
    blocks: tuple[PlannedBlock, ...]


def latin_square_arms(arms: Sequence[str], rotation_index: int) -> tuple[str, ...]:
    """Return the cyclic Latin-square arm order for the given 0-based rotation_index (3.3; owner answer 1).

    Shifts `arms` left by `rotation_index % len(arms)` positions so every arm appears once per
    session and rotates through every position across `len(arms)` days. Raises ValueError if `arms`
    is empty.
    """
    n = len(arms)
    if n == 0:
        raise ValueError("arms must not be empty")
    shift = rotation_index % n
    return tuple(arms[(i + shift) % n] for i in range(n))


def encode_block_order(arms: Sequence[str]) -> str:
    """Encode an ordered sequence of arm names into uppercase initials, e.g. 'CHML' or 'LCHM' (8.1).

    Raises ValueError if `arms` is empty or any arm string is empty.
    """
    if not arms or any(not arm for arm in arms):
        raise ValueError("arms must be non-empty strings")
    return "".join(arm[0].upper() for arm in arms)


def block_label(position: int) -> str:
    """Return the 1-based blinded block label shown in the UI: 'Block 1', 'Block 2', ... (3.3, D18).

    Raises ValueError if position < 0.
    """
    if position < 0:
        raise ValueError("position must be >= 0")
    return f"Block {position + 1}"


def resolve_session_phase(participant_status: str, requested_phase: str | None = None) -> str:
    """Resolve and validate the session phase from participant.status and optional requested_phase.

    Maps 'enrolled'/'baseline' -> 'baseline', 'assigned'/'practice' -> 'practice', 'retest' ->
    'retest'. Raises InvalidSessionPhaseError if participant_status is 'done'/'withdrawn' (or
    unknown), if requested_phase is not in SESSION_PHASES, or if requested_phase conflicts with the
    phase implied by participant_status (owner answer 4).
    """
    implied = _STATUS_TO_PHASE.get(participant_status)
    if implied is None:
        raise InvalidSessionPhaseError(
            f"participant with status {participant_status!r} cannot start a session"
        )
    if requested_phase is None:
        return implied
    if requested_phase not in SESSION_PHASES:
        raise InvalidSessionPhaseError(f"invalid session phase {requested_phase!r}")
    if requested_phase != implied:
        raise InvalidSessionPhaseError(
            f"requested phase {requested_phase!r} conflicts with participant status {participant_status!r}"
        )
    return requested_phase


def load_planner_config(session: Session) -> PlannerConfig:
    """Read arms_enabled, block_chars, drill_length_chars, baseline_parts, and practice_days."""
    ints: dict[str, int] = {}
    for key in _PLANNER_INT_KEYS:
        row = session.get(ExperimentConfig, key)
        if row is None:
            raise MissingConfigError(key)
        ints[key] = int(row.value)
    arms_row = session.get(ExperimentConfig, "arms_enabled")
    if arms_row is None:
        raise MissingConfigError("arms_enabled")
    arms = tuple(str(arm) for arm in arms_row.value)
    if not arms:
        raise MissingConfigError("arms_enabled")
    return PlannerConfig(
        arms=arms,
        block_chars=ints["block_chars"],
        drill_length_chars=ints["drill_length_chars"],
        baseline_parts=ints["baseline_parts"],
        practice_days=ints["practice_days"],
    )


def _ensure_aware_utc(dt: datetime) -> datetime:
    """Ensure a datetime loaded from SQLite is timezone-aware UTC before subtraction."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _build_planned_session(
    typing_session: TypingSession, blocks: Sequence[SessionBlock]
) -> PlannedSession:
    """Build a blinded PlannedSession from a Session row and its ordered SessionBlock rows."""
    ordered = sorted(blocks, key=lambda b: b.block_index)
    planned_blocks = tuple(
        PlannedBlock(
            block_id=block.id,
            block_index=block.block_index,
            label=block_label(position),
            target_text=block.target_text,
            started_at=block.started_at,
            ended_at=block.ended_at,
        )
        for position, block in enumerate(ordered)
    )
    return PlannedSession(
        session_id=typing_session.id,
        participant_id=typing_session.participant_id,
        phase=typing_session.phase,
        day_index=typing_session.day_index,
        status=typing_session.status,
        blocks=planned_blocks,
    )


def get_session_plan(session: Session, session_id: str) -> PlannedSession:
    """Load an existing session and its blocks ordered by block_index ASC (design doc 14).

    Raises SessionNotFoundError if no sessions row has session_id.
    """
    typing_session = session.get(TypingSession, session_id)
    if typing_session is None:
        raise SessionNotFoundError(session_id)
    blocks = session.exec(
        select(SessionBlock)
        .where(col(SessionBlock.session_id) == session_id)
        .order_by(col(SessionBlock.block_index))
    ).all()
    return _build_planned_session(typing_session, blocks)


def plan_session(
    session: Session,
    participant_id: str,
    phase: str | None = None,
    *,
    client_info: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> PlannedSession:
    """Start the next session for participant_id or return the open in_progress one (10.1, 14).

    1. Looks up Participant (raising ParticipantNotFoundError if absent) and resolves the phase via
       resolve_session_phase(participant.status, phase) (raising InvalidSessionPhaseError on
       'done'/'withdrawn' or phase mismatch).
    2. Checks for any existing in_progress session for (participant_id, resolved_phase). If one
       exists and (current_now - started_at) <= STALE_SESSION_TIMEOUT (30 minutes), returns that
       open session's PlannedSession without creating a new session or consuming drills (14). If it
       is > 30 minutes old, marks it status='abandoned', ended_at=current_now and commits (9.3).
    3. Computes day_index = 1 + count(all prior sessions in resolved_phase) (T1.1 owner answer 11)
       and completed_count = count(completed sessions in resolved_phase).
    4. For 'baseline' or 'retest': selects the TextPassage with part == completed_count (form 'A'
       shared for baseline; form 'B' participant-specific for retest; raises PassageNotFoundError
       if missing), creates Session (block_order=None) and one SessionBlock (block_index=passage.part,
       arm='test', passage_id=passage.id, target_text=passage.text), commits, and returns PlannedSession.
    5. For 'practice': computes Latin-square arm order via latin_square_arms(config.arms,
       completed_count) and block_order = encode_block_order(ordered_arms). Selects drills_per_block
       (2) ready drills per arm in creation order (created_at ASC, id ASC). If any arm has fewer
       than drills_per_block ready drills, raises DrillPoolExhaustedError before creating the
       session or mutating any drill. Otherwise inserts and flushes Session and SessionBlock rows
       first, updates each picked Drill to status='used' and used_in_block_id=block.id, commits
       atomically, and returns PlannedSession.
    """
    participant = session.get(Participant, participant_id)
    if participant is None:
        raise ParticipantNotFoundError(participant_id)
    resolved_phase = resolve_session_phase(participant.status, phase)
    config = load_planner_config(session)
    current_now = now if now is not None else utc_now()
    resolved_client_info: dict[str, Any] = dict(client_info) if client_info is not None else {}

    open_sessions = session.exec(
        select(TypingSession)
        .where(
            col(TypingSession.participant_id) == participant_id,
            col(TypingSession.phase) == resolved_phase,
            col(TypingSession.status) == "in_progress",
        )
        .order_by(col(TypingSession.started_at).desc(), col(TypingSession.id).desc())
    ).all()

    active_open_session_id: str | None = None
    abandoned_any = False
    for open_session in open_sessions:
        age = current_now - _ensure_aware_utc(open_session.started_at)
        if active_open_session_id is None and age <= STALE_SESSION_TIMEOUT:
            active_open_session_id = open_session.id
            continue
        open_session.status = "abandoned"
        open_session.ended_at = current_now
        session.add(open_session)
        abandoned_any = True

    if abandoned_any:
        session.commit()

    if active_open_session_id is not None:
        return get_session_plan(session, active_open_session_id)

    prior_sessions = session.exec(
        select(TypingSession).where(
            col(TypingSession.participant_id) == participant_id,
            col(TypingSession.phase) == resolved_phase,
        )
    ).all()
    day_index = len(prior_sessions) + 1
    completed_count = sum(1 for s in prior_sessions if s.status == "completed")

    if resolved_phase in ("baseline", "retest"):
        form = "A" if resolved_phase == "baseline" else "B"
        passage_stmt = select(TextPassage).where(
            col(TextPassage.kind) == resolved_phase,
            col(TextPassage.form) == form,
            col(TextPassage.part) == completed_count,
        )
        if resolved_phase == "baseline":
            passage_stmt = passage_stmt.where(col(TextPassage.participant_id).is_(None))
        else:
            passage_stmt = passage_stmt.where(col(TextPassage.participant_id) == participant_id)
        passage = session.exec(passage_stmt).first()
        if passage is None:
            raise PassageNotFoundError(
                f"no {resolved_phase} (form {form}) passage for part {completed_count}"
            )
        typing_session = TypingSession(
            participant_id=participant_id,
            phase=resolved_phase,
            day_index=day_index,
            block_order=None,
            status="in_progress",
            client_info=resolved_client_info,
            started_at=current_now,
        )
        session.add(typing_session)
        session.flush()
        block = SessionBlock(
            session_id=typing_session.id,
            block_index=passage.part,
            arm="test",
            passage_id=passage.id,
            target_text=passage.text,
        )
        session.add(block)
        session.commit()
        session.refresh(typing_session)
        session.refresh(block)
        return _build_planned_session(typing_session, (block,))

    ordered_arms = latin_square_arms(config.arms, completed_count)
    block_order = encode_block_order(ordered_arms)
    drills_needed = config.drills_per_block

    picked_by_arm: dict[str, list[Drill]] = {}
    for arm in ordered_arms:
        ready_drills = list(
            session.exec(
                select(Drill)
                .where(
                    col(Drill.participant_id) == participant_id,
                    col(Drill.arm) == arm,
                    col(Drill.status) == "ready",
                )
                .order_by(col(Drill.created_at).asc(), col(Drill.id).asc())
                .limit(drills_needed)
            ).all()
        )
        if len(ready_drills) < drills_needed:
            raise DrillPoolExhaustedError(
                f"participant {participant_id!r} arm {arm!r} has {len(ready_drills)} ready "
                f"drill(s), need {drills_needed}"
            )
        picked_by_arm[arm] = ready_drills

    typing_session = TypingSession(
        participant_id=participant_id,
        phase="practice",
        day_index=day_index,
        block_order=block_order,
        status="in_progress",
        client_info=resolved_client_info,
        started_at=current_now,
    )
    session.add(typing_session)
    session.flush()

    created_blocks: list[SessionBlock] = []
    for block_index, arm in enumerate(ordered_arms):
        arm_drills = picked_by_arm[arm]
        target_text = " ".join(drill.text for drill in arm_drills)
        block = SessionBlock(
            session_id=typing_session.id,
            block_index=block_index,
            arm=arm,
            passage_id=None,
            target_text=target_text,
        )
        session.add(block)
        session.flush()
        for drill in arm_drills:
            drill.status = "used"
            drill.used_in_block_id = block.id
            session.add(drill)
        created_blocks.append(block)

    session.commit()
    session.refresh(typing_session)
    for block in created_blocks:
        session.refresh(block)
    return _build_planned_session(typing_session, created_blocks)


def replenish_drill_pool(session: Session, participant_id: str) -> list[GenerationJob]:
    """Enqueue pending generation_jobs for any enabled arm whose ready+queued pool is below target (13.7).

    Target ready count per enabled arm is POOL_TARGET_DAYS * (block_chars // drill_length_chars)
    (3 * 2 = 6 drills; owner answer 5). Raises ParticipantNotFoundError if participant_id does not
    exist. Returns [] without enqueueing jobs if the participant has no frozen bigram_assignment
    rows yet. Subtracts already-queued (status IN ('pending', 'running')) GenerationJob.requested
    counts from the deficit so duplicate jobs are not enqueued while the worker is busy.
    """
    if session.get(Participant, participant_id) is None:
        raise ParticipantNotFoundError(participant_id)
    has_assignment = session.exec(
        select(BigramAssignment.bigram)
        .where(col(BigramAssignment.participant_id) == participant_id)
        .limit(1)
    ).first()
    if has_assignment is None:
        return []

    config = load_planner_config(session)
    target = config.pool_target_drills
    created_jobs: list[GenerationJob] = []

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
        deficit = target - (ready_count + queued_count)
        if deficit > 0:
            job = GenerationJob(
                participant_id=participant_id,
                arm=arm,
                requested=deficit,
                status="pending",
            )
            session.add(job)
            created_jobs.append(job)

    if created_jobs:
        session.commit()
        for job in created_jobs:
            session.refresh(job)
    return created_jobs
