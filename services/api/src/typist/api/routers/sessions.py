"""POST /sessions/{session_id}/complete: compute stats and complete a session (design doc 14; T1.9).

Owner answer 3 (T1.9 brief): this endpoint is stats-only. The design doc's "update phase" and
"enqueue jobs" belong to M2 (assignment in T2.2, the worker in T2.5) and are deliberately not done
here. 404 for an unknown session; 409 when the session is not in_progress (section 14 "Invalid
state transitions ... return 409"); otherwise the session is marked completed and SessionSummary
is returned.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from typist.db import get_session, utc_now
from typist.schemas.sessions import SessionSummary
from typist.services.session_stats import (
    SessionNotFoundError,
    SessionNotInProgressError,
    complete_session,
)

router = APIRouter(tags=["sessions"])


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
    """Compute stats, mark the session completed, and return SessionSummary.

    404 if the session does not exist; 409 if its status is not 'in_progress' (already completed
    or abandoned). ended_at is set to utc_now(). Phase update and job enqueue are M2 (owner
    answer 3).
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
    return SessionSummary(
        session_id=session_id,
        wpm=stats.wpm,
        accuracy=stats.accuracy,
        bigram_count=len(stats.bigrams),
        blocks=stats.block_count,
    )
