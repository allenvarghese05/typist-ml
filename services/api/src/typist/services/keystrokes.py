"""The one write path that updates keystroke_events rows (T1.1 owner answer 6)."""

from sqlmodel import Session, col, select

from typist.models import KeystrokeEvent


class KeystrokeEventNotFoundError(LookupError):
    """No keystroke_events row has the given (block_id, seq)."""


class KeyUpAlreadyRecordedError(ValueError):
    """t_up_ms is already set; keystroke rows are append-only apart from one key-up fill."""


def record_key_up(session: Session, block_id: str, seq: int, t_up_ms: float) -> KeystrokeEvent:
    """Fill in the key-up time of one stored keystroke, the only update keystroke_events allows.

    Sets t_up_ms and dwell_ms = t_up_ms - t_down_ms on the row (block_id, seq), commits, and
    returns the refreshed row. Nothing else changes: release_to_press_ms on later rows is never
    backfilled. A negative or long dwell is stored as is (section 12.6 checks flag it).
    Raises KeystrokeEventNotFoundError if no row matches, and KeyUpAlreadyRecordedError if
    t_up_ms is already set (the row is left unchanged).
    """
    event = session.exec(
        select(KeystrokeEvent).where(
            col(KeystrokeEvent.block_id) == block_id, col(KeystrokeEvent.seq) == seq
        )
    ).one_or_none()
    if event is None:
        raise KeystrokeEventNotFoundError(f"no keystroke event (block_id={block_id!r}, seq={seq})")
    if event.t_up_ms is not None:
        raise KeyUpAlreadyRecordedError(
            f"key-up already recorded (block_id={block_id!r}, seq={seq})"
        )
    event.t_up_ms = t_up_ms
    event.dwell_ms = t_up_ms - event.t_down_ms
    session.add(event)
    session.commit()
    session.refresh(event)
    return event
