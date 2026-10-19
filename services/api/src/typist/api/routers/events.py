"""POST /blocks/{block_id}/events: idempotent batch upload of keystroke rows (design doc 12.4, 14)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from typist.db import get_session
from typist.schemas.events import EventBatchIn, EventBatchResult
from typist.services.events import BlockNotFoundError, store_events

router = APIRouter(tags=["events"])


@router.post(
    "/blocks/{block_id}/events",
    response_model=EventBatchResult,
    responses={status.HTTP_404_NOT_FOUND: {"description": "block not found"}},
)
def post_block_events(
    block_id: str,
    batch: EventBatchIn,
    session: Annotated[Session, Depends(get_session)],
) -> EventBatchResult:
    """Insert the batch for block_id and return accepted/duplicate counts.

    Idempotent: re-sending a batch stores it once (ON CONFLICT DO NOTHING). Returns 404 if the
    block does not exist (owner answer 11b). EventBatchIn validates the body, so a malformed row
    yields 422 before this runs (owner answer 10).
    """
    try:
        result = store_events(session, block_id, batch.events)
    except BlockNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="block not found"
        ) from error
    return EventBatchResult(accepted=result.accepted, duplicates=result.duplicates)
