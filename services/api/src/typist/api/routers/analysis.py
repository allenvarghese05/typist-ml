"""GET /analysis/sessions/{session_id}/matrix: the M1 bigram matrix (design doc 15.2; T1.10).

Read-only. 404 when the session does not exist; 409 when it is not completed (no stats yet).
The design doc's other /analysis/* endpoints (participants, overview) are T4 and are not here.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from typist.db import get_session
from typist.schemas.analysis import BigramMatrix
from typist.services.analysis import SessionNotCompletedError, session_matrix
from typist.services.session_stats import SessionNotFoundError

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
