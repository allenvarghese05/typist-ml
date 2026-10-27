"""Participant lifecycle and deletion service (design doc 4.2, 9.3, 14; T1.1, T2.8)."""

from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session, col, delete, select

from typist.db import utc_now
from typist.models import (
    BigramAssignment,
    BigramStat,
    Drill,
    GenerationAttempt,
    GenerationJob,
    KeystrokeEvent,
    Participant,
    SessionBlock,
    TextPassage,
)
from typist.models import Session as TypingSession


class ParticipantNotFoundError(LookupError):
    """No participants row has the given id."""


class ParticipantError(RuntimeError):
    """Base class for participant service errors."""


class ParticipantStatusConflictError(ParticipantError):
    """The participant is in an invalid status for this operation (maps to 409 Conflict)."""


class AliasAlreadyExistsError(ParticipantError):
    """A participant with this alias already exists (maps to 409 Conflict)."""


class ParticipantWithdrawnError(ParticipantError):
    """Operation rejected because the participant has withdrawn (maps to 409 Conflict)."""


def create_participant(
    session: Session,
    alias: str,
    *,
    is_builder: bool = False,
    is_blinded: bool | None = None,
    keyboard_label: str | None = None,
) -> Participant:
    """Create a new participant in 'enrolled' status. Raises AliasAlreadyExistsError on duplicate alias."""
    existing = session.exec(select(Participant).where(col(Participant.alias) == alias)).first()
    if existing is not None:
        raise AliasAlreadyExistsError(f"participant with alias {alias!r} already exists")
    blinded = False if is_builder else (is_blinded if is_blinded is not None else True)
    participant = Participant(
        alias=alias,
        is_builder=is_builder,
        is_blinded=blinded,
        keyboard_label=keyboard_label,
        status="enrolled",
    )
    session.add(participant)
    session.commit()
    session.refresh(participant)
    return participant


def list_participants(session: Session) -> list[Participant]:
    """Return all participants ordered by created_at DESC, id ASC."""
    return list(
        session.exec(
            select(Participant).order_by(col(Participant.created_at).desc(), col(Participant.id))
        ).all()
    )


def get_participant(session: Session, participant_id: str) -> Participant:
    """Load a participant by id; raises ParticipantNotFoundError if absent."""
    participant = session.get(Participant, participant_id)
    if participant is None:
        raise ParticipantNotFoundError(participant_id)
    return participant


def record_consent(
    session: Session,
    participant_id: str,
    *,
    keyboard_label: str | None = None,
    now: datetime | None = None,
) -> Participant:
    """Record consent, moving status from 'enrolled' to 'baseline' and setting consent_at.

    Raises ParticipantNotFoundError (404) if absent, or ParticipantStatusConflictError (409) if
    participant.status is not 'enrolled'.
    """
    participant = get_participant(session, participant_id)
    if participant.status != "enrolled":
        raise ParticipantStatusConflictError(
            f"cannot record consent for participant with status {participant.status!r}; must be 'enrolled'"
        )
    participant.status = "baseline"
    participant.consent_at = now if now is not None else utc_now()
    if keyboard_label is not None:
        participant.keyboard_label = keyboard_label
    session.add(participant)
    session.commit()
    session.refresh(participant)
    return participant


def withdraw_participant(session: Session, participant_id: str) -> Participant:
    """Mark an active participant 'withdrawn'.

    Raises ParticipantNotFoundError (404) if absent, or ParticipantStatusConflictError (409) if
    participant.status is already 'done' or 'withdrawn'.
    """
    participant = get_participant(session, participant_id)
    if participant.status in ("done", "withdrawn"):
        raise ParticipantStatusConflictError(
            f"cannot withdraw participant with status {participant.status!r}; must be active"
        )
    participant.status = "withdrawn"
    session.add(participant)
    session.commit()
    session.refresh(participant)
    return participant


@dataclass(frozen=True)
class ParticipantDeletion:
    """Rows removed by delete_participant, per table."""

    bigram_assignment: int
    drills: int
    generation_jobs: int
    generation_attempts: int
    bigram_stats: int
    keystroke_events: int
    session_blocks: int
    sessions: int
    text_passages: int
    participants: int


def delete_participant(session: Session, participant_id: str) -> ParticipantDeletion:
    """Delete every row that belongs to one participant, children before parents, and commit.

    Order: generation_attempts of the participant's generation_jobs, generation_jobs, drills
    (before session_blocks, because drills.used_in_block_id references a block), bigram_assignment,
    keystroke_events of the participant's blocks, session_blocks, bigram_stats, sessions, the
    participant's own text_passages (participant_id set; shared passages with a NULL participant_id
    are never touched), then the participants row. There is no ON DELETE CASCADE, so this is the only
    delete path. Raises ParticipantNotFoundError, deleting nothing, if the participant does not
    exist. Any database error rolls the whole delete back.
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
    job_ids = list(
        session.exec(
            select(GenerationJob.id).where(col(GenerationJob.participant_id) == participant_id)
        ).all()
    )
    try:
        attempts = session.exec(
            delete(GenerationAttempt).where(col(GenerationAttempt.job_id).in_(job_ids))
        ).rowcount
        jobs = session.exec(
            delete(GenerationJob).where(col(GenerationJob.participant_id) == participant_id)
        ).rowcount
        drills = session.exec(
            delete(Drill).where(col(Drill.participant_id) == participant_id)
        ).rowcount
        assignments = session.exec(
            delete(BigramAssignment).where(col(BigramAssignment.participant_id) == participant_id)
        ).rowcount
        events = session.exec(
            delete(KeystrokeEvent).where(col(KeystrokeEvent.block_id).in_(block_ids))
        ).rowcount
        blocks = session.exec(
            delete(SessionBlock).where(col(SessionBlock.id).in_(block_ids))
        ).rowcount
        bigrams = session.exec(
            delete(BigramStat).where(col(BigramStat.session_id).in_(session_ids))
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
        bigram_assignment=assignments,
        drills=drills,
        generation_jobs=jobs,
        generation_attempts=attempts,
        bigram_stats=bigrams,
        keystroke_events=events,
        session_blocks=blocks,
        sessions=sessions,
        text_passages=passages,
        participants=participants,
    )
