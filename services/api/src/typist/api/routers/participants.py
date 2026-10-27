"""Participant endpoints: list, create, consent, withdraw, and delete (design doc 4.2, 14)."""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlmodel import Session

from typist.db import get_session
from typist.schemas.participants import (
    ParticipantConsent,
    ParticipantCreate,
    ParticipantDeletionResponse,
    ParticipantResponse,
)
from typist.services.participants import (
    AliasAlreadyExistsError,
    ParticipantNotFoundError,
    ParticipantStatusConflictError,
    create_participant,
    delete_participant,
    list_participants,
    record_consent,
    withdraw_participant,
)

router = APIRouter(tags=["participants"])


@router.get("/participants", response_model=list[ParticipantResponse])
def get_participants(
    session: Annotated[Session, Depends(get_session)],
) -> list[ParticipantResponse]:
    """List all participants ordered by created_at DESC, id ASC."""
    rows = list_participants(session)
    return [
        ParticipantResponse(
            id=p.id,
            alias=p.alias,
            is_builder=p.is_builder,
            is_blinded=p.is_blinded,
            status=p.status,
            keyboard_label=p.keyboard_label,
            consent_at=p.consent_at,
            created_at=p.created_at,  # pyright: ignore[reportArgumentType]
        )
        for p in rows
    ]


@router.post(
    "/participants",
    response_model=ParticipantResponse,
    responses={
        status.HTTP_409_CONFLICT: {"description": "alias already exists"},
    },
)
def post_participant(
    body: ParticipantCreate,
    session: Annotated[Session, Depends(get_session)],
) -> ParticipantResponse:
    """Create a new participant in 'enrolled' status."""
    try:
        p = create_participant(
            session,
            alias=body.alias,
            is_builder=body.is_builder,
            is_blinded=body.is_blinded,
            keyboard_label=body.keyboard_label,
        )
    except AliasAlreadyExistsError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return ParticipantResponse(
        id=p.id,
        alias=p.alias,
        is_builder=p.is_builder,
        is_blinded=p.is_blinded,
        status=p.status,
        keyboard_label=p.keyboard_label,
        consent_at=p.consent_at,
        created_at=p.created_at,  # pyright: ignore[reportArgumentType]
    )


@router.post(
    "/participants/{participant_id}/consent",
    response_model=ParticipantResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "participant not found"},
        status.HTTP_409_CONFLICT: {"description": "participant is not in enrolled status"},
    },
)
def post_participant_consent(
    participant_id: str,
    session: Annotated[Session, Depends(get_session)],
    body: Annotated[ParticipantConsent | None, Body()] = None,
) -> ParticipantResponse:
    """Record consent, moving status from 'enrolled' to 'baseline'."""
    keyboard_label = body.keyboard_label if body is not None else None
    try:
        p = record_consent(session, participant_id, keyboard_label=keyboard_label)
    except ParticipantNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="participant not found"
        ) from error
    except ParticipantStatusConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return ParticipantResponse(
        id=p.id,
        alias=p.alias,
        is_builder=p.is_builder,
        is_blinded=p.is_blinded,
        status=p.status,
        keyboard_label=p.keyboard_label,
        consent_at=p.consent_at,
        created_at=p.created_at,  # pyright: ignore[reportArgumentType]
    )


@router.post(
    "/participants/{participant_id}/withdraw",
    response_model=ParticipantResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "participant not found"},
        status.HTTP_409_CONFLICT: {"description": "participant is already done or withdrawn"},
    },
)
def post_participant_withdraw(
    participant_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ParticipantResponse:
    """Withdraw an active participant."""
    try:
        p = withdraw_participant(session, participant_id)
    except ParticipantNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="participant not found"
        ) from error
    except ParticipantStatusConflictError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return ParticipantResponse(
        id=p.id,
        alias=p.alias,
        is_builder=p.is_builder,
        is_blinded=p.is_blinded,
        status=p.status,
        keyboard_label=p.keyboard_label,
        consent_at=p.consent_at,
        created_at=p.created_at,  # pyright: ignore[reportArgumentType]
    )


@router.delete(
    "/participants/{participant_id}",
    response_model=ParticipantDeletionResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "participant not found"},
    },
)
def delete_participant_by_id(
    participant_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ParticipantDeletionResponse:
    """Delete all rows belonging to participant_id."""
    try:
        del_result = delete_participant(session, participant_id)
    except ParticipantNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="participant not found"
        ) from error
    return ParticipantDeletionResponse(
        participant_id=participant_id,
        bigram_assignment=del_result.bigram_assignment,
        drills=del_result.drills,
        generation_jobs=del_result.generation_jobs,
        generation_attempts=del_result.generation_attempts,
        bigram_stats=del_result.bigram_stats,
        keystroke_events=del_result.keystroke_events,
        session_blocks=del_result.session_blocks,
        sessions=del_result.sessions,
        text_passages=del_result.text_passages,
        participants=del_result.participants,
    )
