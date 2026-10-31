"""GET /analysis/sessions/{session_id}/matrix: the M1 bigram matrix (design doc 15.2; T1.10).

Read-only. 404 when the session does not exist; 409 when it is not completed (no stats yet).
The design doc's other /analysis/* endpoints (participants, overview) are T4 and are not here.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from typist.db import get_session
from typist.schemas.admin import SessionTrendEntry
from typist.schemas.analysis import BigramMatrix, Overview, ParticipantResults
from typist.services.analysis import (
    ParticipantNotDoneError,
    SessionNotCompletedError,
    overview_report,
    participant_results,
    session_matrix,
)
from typist.services.checks import participant_session_trend
from typist.services.participants import ParticipantNotFoundError
from typist.services.session_stats import SessionNotFoundError
from typist.services.test_composer import ParticipantNotAssignedError

router = APIRouter(tags=["analysis"])


@router.get(
    "/analysis/sessions/{session_id}/matrix",
    response_model=BigramMatrix,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "session not found"},
        status.HTTP_409_CONFLICT: {"description": "session is not completed"},
    },
)
def get_session_matrix(
    session_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> BigramMatrix:
    """Return the completed session's bigram matrix.

    404 if the session does not exist; 409 if its status is not 'completed' (no stats written yet).
    """
    try:
        return session_matrix(session, session_id)
    except SessionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="session not found"
        ) from error
    except SessionNotCompletedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="session is not completed"
        ) from error


@router.get(
    "/analysis/participants/{participant_id}",
    response_model=ParticipantResults,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "participant not found"},
        status.HTTP_409_CONFLICT: {"description": "participant not done or not assigned"},
    },
)
def get_participant_analysis(
    participant_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ParticipantResults:
    """Return study-level per-set outcome analysis for a participant whose status is 'done'."""
    try:
        return participant_results(session, participant_id)
    except ParticipantNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="participant not found"
        ) from error
    except (ParticipantNotDoneError, ParticipantNotAssignedError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.get(
    "/analysis/participants/{participant_id}/trend",
    response_model=list[SessionTrendEntry],
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "participant not found"},
    },
)
def get_participant_trend(
    participant_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> list[SessionTrendEntry]:
    """Return chronological session trend entries for a participant."""
    try:
        return participant_session_trend(session, participant_id)
    except ParticipantNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="participant not found"
        ) from error


@router.get(
    "/analysis/overview",
    response_model=Overview,
)
def get_overview(
    session: Annotated[Session, Depends(get_session)],
) -> Overview:
    """Return system-wide overview: participants, overhead percentiles, and generation audit stats."""
    return overview_report(session)
