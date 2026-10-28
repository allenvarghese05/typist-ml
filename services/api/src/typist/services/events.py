"""Idempotent batch insert into keystroke_events (design doc 12.4; T1.6 owner answers 1, 3, 5)."""

from dataclasses import dataclass

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session

from typist.models import KeystrokeEvent, SessionBlock
from typist.schemas.events import KeystrokeEventIn


class BlockNotFoundError(LookupError):
    """No session_blocks row has the given id."""


@dataclass(frozen=True)
class EventIngestResult:
    """Rows inserted versus skipped as duplicates by store_events."""

    accepted: int
    duplicates: int


def store_events(
    session: Session, block_id: str, events: list[KeystrokeEventIn]
) -> EventIngestResult:
    """Insert a batch of keystroke rows for one block, idempotently, and commit.

    Uses INSERT ... ON CONFLICT (block_id, seq) DO NOTHING (section 12.4), so re-sending a batch
    never duplicates rows: accepted is the number actually inserted (the statement rowcount),
    duplicates is the rest (owner answer 5). release_to_press_ms is left NULL (owner answer 3). An
    empty batch is a no-op returning 0/0. Raises BlockNotFoundError, inserting nothing, if the
    block does not exist (the FK would otherwise raise; the router turns this into 404 — owner
    answer 11b).
    """
    if session.get(SessionBlock, block_id) is None:
        raise BlockNotFoundError(block_id)
    if not events:
        return EventIngestResult(accepted=0, duplicates=0)
    values = [{"block_id": block_id, **event.model_dump()} for event in events]
    chunk_size = 500
    accepted = 0
    for i in range(0, len(values), chunk_size):
        chunk = values[i : i + chunk_size]
        statement = (
            sqlite_insert(KeystrokeEvent)
            .values(chunk)
            .on_conflict_do_nothing(index_elements=["block_id", "seq"])
        )
        result = session.exec(statement)
        accepted += result.rowcount
    session.commit()
    return EventIngestResult(accepted=accepted, duplicates=len(events) - accepted)
