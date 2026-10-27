"""Block timing and lifecycle service (design doc 14; T2.8)."""

from datetime import datetime

from sqlmodel import Session

from typist.db import utc_now
from typist.models import Participant, SessionBlock
from typist.models import Session as TypingSession
from typist.services.participants import ParticipantWithdrawnError


class BlockError(RuntimeError):
    """Base class for block lifecycle errors."""


class BlockNotFoundError(LookupError):
    """No session_blocks row has the given id."""


class BlockStateConflictError(BlockError):
    """Invalid block state transition (maps to 409 Conflict)."""


def start_block(session: Session, block_id: str, *, now: datetime | None = None) -> SessionBlock:
    """Set block.started_at to now.

    Raises BlockNotFoundError (404) if block does not exist. Raises BlockStateConflictError (409) if
    the session is not in_progress or if the block has already started. Raises ParticipantWithdrawnError
    (409) if the participant has withdrawn.
    """
    block = session.get(SessionBlock, block_id)
    if block is None:
        raise BlockNotFoundError(block_id)
    typing_session = session.get(TypingSession, block.session_id)
    if typing_session is None or typing_session.status != "in_progress":
        raise BlockStateConflictError("session is not in progress")
    participant = session.get(Participant, typing_session.participant_id)
    if participant is not None and participant.status == "withdrawn":
        raise ParticipantWithdrawnError(f"participant {typing_session.participant_id} is withdrawn")
    if block.started_at is not None:
        raise BlockStateConflictError("block already started")
    block.started_at = now if now is not None else utc_now()
    session.add(block)
    session.commit()
    session.refresh(block)
    return block


def complete_block(session: Session, block_id: str, *, now: datetime | None = None) -> SessionBlock:
    """Set block.ended_at to now.

    Raises BlockNotFoundError (404) if block does not exist. Raises BlockStateConflictError (409) if
    the session is not in_progress, if the block has not started, or if the block has already completed.
    Raises ParticipantWithdrawnError (409) if the participant has withdrawn.
    """
    block = session.get(SessionBlock, block_id)
    if block is None:
        raise BlockNotFoundError(block_id)
    typing_session = session.get(TypingSession, block.session_id)
    if typing_session is None or typing_session.status != "in_progress":
        raise BlockStateConflictError("session is not in progress")
    participant = session.get(Participant, typing_session.participant_id)
    if participant is not None and participant.status == "withdrawn":
        raise ParticipantWithdrawnError(f"participant {typing_session.participant_id} is withdrawn")
    if block.started_at is None:
        raise BlockStateConflictError("block has not started")
    if block.ended_at is not None:
        raise BlockStateConflictError("block already completed")
    block.ended_at = now if now is not None else utc_now()
    session.add(block)
    session.commit()
    session.refresh(block)
    return block
