"""Session endpoints: plan/start a session, fetch a session plan, and complete a session
(design doc sections 10.1, 13.7, 14; T1.9, T2.6).
"""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlmodel import Session

from typist.db import get_session, utc_now
from typist.models import Session as TypingSession
from typist.schemas.sessions import (
    BlockPlan,
    SessionPlan,
    SessionStartRequest,
    SessionSummary,
)
from typist.services.participants import ParticipantNotFoundError
from typist.services.session_planner import (
    PlannedSession,
    SessionPlannerError,
    get_session_plan,
    plan_session,
    replenish_drill_pool,
)
from typist.services.session_stats import (
    SessionNotFoundError,
    SessionNotInProgressError,
    complete_session,
)

router = APIRouter(tags=["sessions"])


def _to_session_plan(planned: PlannedSession) -> SessionPlan:
    """Convert a service PlannedSession dataclass into the API SessionPlan schema."""
    return SessionPlan(
        session_id=planned.session_id,
        participant_id=planned.participant_id,
        phase=planned.phase,
        day_index=planned.day_index,
        status=planned.status,
        blocks=[
            BlockPlan(
                block_id=block.block_id,
                block_index=block.block_index,
                label=block.label,
                target_text=block.target_text,
                started_at=block.started_at,
                ended_at=block.ended_at,
            )
            for block in planned.blocks
        ],
    )


@router.post(
    "/participants/{participant_id}/sessions",
    response_model=SessionPlan,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "participant not found"},
        status.HTTP_409_CONFLICT: {
            "description": "invalid phase, missing passage, or drill pool exhausted"
        },
    },
)
def post_participant_session(
    participant_id: str,
    session: Annotated[Session, Depends(get_session)],
    payload: Annotated[SessionStartRequest | None, Body()] = None,
) -> SessionPlan:
    """Start the next session for the participant's current phase or return the open one (14)."""
    req = payload if payload is not None else SessionStartRequest()
    try:
        planned = plan_session(
            session,
            participant_id,
            req.phase,
            client_info=req.client_info,
            now=utc_now(),
        )
    except ParticipantNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="participant not found"
        ) from error
    except SessionPlannerError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return _to_session_plan(planned)


@router.get(
    "/sessions/{session_id}",
    response_model=SessionPlan,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "session not found"},
    },
)
def get_session_by_id(
    session_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> SessionPlan:
    """Return the blinded SessionPlan for an existing session (design doc 14)."""
    try:
        planned = get_session_plan(session, session_id)
    except SessionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="session not found"
        ) from error
    return _to_session_plan(planned)


@router.post(
    "/sessions/{session_id}/complete",
    response_model=SessionSummary,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "session not found"},
        status.HTTP_409_CONFLICT: {"description": "session is not in progress"},
    },
)
def post_session_complete(
    session_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> SessionSummary:
    """Compute stats, mark the session completed, enqueue replenishment jobs, and return SessionSummary.

    404 if the session does not exist; 409 if its status is not 'in_progress' (already completed
    or abandoned). When a practice session completes, enqueues generation_jobs for any enabled arm
    whose ready drill pool is below the 3-day target (section 10.1, 13.7; T2.6 owner answer 4/5).
    Participant phase transitions belong to T2.8.
    """
    try:
        stats = complete_session(session, session_id, utc_now())
    except SessionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="session not found"
        ) from error
    except SessionNotInProgressError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="session is not in progress"
        ) from error

    completed_row = session.get(TypingSession, session_id)
    if completed_row is not None and completed_row.phase == "practice":
        replenish_drill_pool(session, completed_row.participant_id)

    return SessionSummary(
        session_id=session_id,
        wpm=stats.wpm,
        accuracy=stats.accuracy,
        bigram_count=len(stats.bigrams),
        blocks=stats.block_count,
    )
