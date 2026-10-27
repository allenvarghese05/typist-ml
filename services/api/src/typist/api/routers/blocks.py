"""Block timing endpoints: mark block start and end (design doc 14; T2.8)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from typist.db import get_session
from typist.schemas.blocks import BlockResponse
from typist.services.blocks import (
    BlockNotFoundError,
    BlockStateConflictError,
    complete_block,
    start_block,
)
from typist.services.participants import ParticipantWithdrawnError
from typist.services.session_planner import block_label

router = APIRouter(tags=["blocks"])


@router.post(
    "/blocks/{block_id}/start",
    response_model=BlockResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "block not found"},
        status.HTTP_409_CONFLICT: {
            "description": "block already started, session not in progress, or participant withdrawn"
        },
    },
)
def post_block_start(
    block_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> BlockResponse:
    """Record block start time; returns blinded BlockResponse."""
    try:
        block = start_block(session, block_id)
    except BlockNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="block not found"
        ) from error
    except (BlockStateConflictError, ParticipantWithdrawnError) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    return BlockResponse(
        id=block.id,
        session_id=block.session_id,
        block_index=block.block_index,
        label=block_label(block.block_index),
        started_at=block.started_at,
        ended_at=block.ended_at,
    )


@router.post(
    "/blocks/{block_id}/complete",
    response_model=BlockResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "block not found"},
        status.HTTP_409_CONFLICT: {
            "description": "block not started, already completed, session not in progress, or participant withdrawn"
        },
    },
)
def post_block_complete(
    block_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> BlockResponse:
    """Record block completion time; returns blinded BlockResponse."""
    try:
        block = complete_block(session, block_id)
    except BlockNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="block not found"
        ) from error
    except (BlockStateConflictError, ParticipantWithdrawnError) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    return BlockResponse(
        id=block.id,
        session_id=block.session_id,
        block_index=block.block_index,
        label=block_label(block.block_index),
        started_at=block.started_at,
        ended_at=block.ended_at,
    )
