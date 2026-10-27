"""Admin endpoints: assignment and participant management (design doc 14; T2.8)."""

import random
from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session

from typist.corpus.word_index import WordIndex
from typist.db import get_session, utc_now
from typist.models import Participant
from typist.schemas.admin import AssignmentResponse
from typist.services.assignment import (
    AssignmentError,
    assign_participant,
    load_assignment_config,
)
from typist.services.participants import ParticipantNotFoundError
from typist.services.test_composer import (
    BaselinePassagesNotFoundError,
    compose_and_persist_retest,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def get_word_index(request: Request) -> WordIndex:
    """Dependency to load the WordIndex from the app's configured corpus_dir."""
    return WordIndex.load(request.app.state.settings.corpus_dir)


@router.post(
    "/participants/{participant_id}/assign",
    response_model=AssignmentResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "participant not found"},
        status.HTTP_409_CONFLICT: {
            "description": "invalid status, baseline incomplete, already assigned, or too few candidates"
        },
    },
)
def post_admin_assign(
    participant_id: str,
    session: Annotated[Session, Depends(get_session)],
    index: Annotated[WordIndex, Depends(get_word_index)],
) -> AssignmentResponse:
    """Rank, split, map and freeze weak bigrams; transitions participant to 'assigned'."""
    participant = session.get(Participant, participant_id)
    if participant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="participant not found")
    if participant.status != "baseline":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"participant status {participant.status!r} cannot be assigned; must be 'baseline'",
        )
    try:
        config = load_assignment_config(session)
        rng = random.Random(f"{config.seed}:{participant_id}")
        rows = assign_participant(session, participant_id, rng=rng, now=utc_now(), index=index)
    except ParticipantNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="participant not found"
        ) from error
    except AssignmentError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

    form_b_composed = False
    with suppress(BaselinePassagesNotFoundError, ValueError):
        compose_and_persist_retest(session, participant_id, index)
        form_b_composed = True

    mapping = {row.set_label: row.arm for row in rows}
    return AssignmentResponse(
        participant_id=participant_id,
        status="assigned",
        frozen_bigrams=len(rows),
        mapping=mapping,
        form_b_composed=form_b_composed,
    )
