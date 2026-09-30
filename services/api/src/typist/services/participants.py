"""Explicit deletion of one participant's data (design doc 4.2; T1.1 owner answer 10)."""

from dataclasses import dataclass

from sqlmodel import Session, col, delete, select

from typist.models import KeystrokeEvent, Participant, SessionBlock, TextPassage
from typist.models import Session as TypingSession


class ParticipantNotFoundError(LookupError):
    """No participants row has the given id."""


@dataclass(frozen=True)
class ParticipantDeletion:
    """Rows removed by delete_participant, per table."""

    keystroke_events: int
    session_blocks: int
    sessions: int
    text_passages: int
    participants: int


def delete_participant(session: Session, participant_id: str) -> ParticipantDeletion:
    """Delete every row that belongs to one participant, children before parents, and commit.

    Order: keystroke_events of the participant's blocks, session_blocks, sessions, the
    participant's own text_passages (participant_id set; shared passages with a NULL
    participant_id are never touched), then the participants row. There is no ON DELETE
    CASCADE, so this is the only delete path. Raises ParticipantNotFoundError, deleting nothing,
    if the participant does not exist. Any database error rolls the whole delete back.
    """
    if session.get(Participant, participant_id) is None:
        raise ParticipantNotFoundError(participant_id)
    session_ids = list(
        session.exec(
            select(TypingSession.id).where(col(TypingSession.participant_id) == participant_id)
        ).all()
    )
    block_ids = list(
        session.exec(
            select(SessionBlock.id).where(col(SessionBlock.session_id).in_(session_ids))
        ).all()
    )
    try:
        events = session.exec(
            delete(KeystrokeEvent).where(col(KeystrokeEvent.block_id).in_(block_ids))
        ).rowcount
        blocks = session.exec(
            delete(SessionBlock).where(col(SessionBlock.id).in_(block_ids))
        ).rowcount
        sessions = session.exec(
            delete(TypingSession).where(col(TypingSession.id).in_(session_ids))
        ).rowcount
        passages = session.exec(
            delete(TextPassage).where(col(TextPassage.participant_id) == participant_id)
        ).rowcount
        participants = session.exec(
            delete(Participant).where(col(Participant.id) == participant_id)
        ).rowcount
        session.commit()
    except Exception:
        session.rollback()
        raise
    return ParticipantDeletion(
        keystroke_events=events,
        session_blocks=blocks,
        sessions=sessions,
        text_passages=passages,
        participants=participants,
    )
