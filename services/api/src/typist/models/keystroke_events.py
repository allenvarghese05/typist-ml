"""keystroke_events table (design doc section 8.1, D24): the raw data everything else comes from.

Rows are append-only (section 6.2, CLAUDE.md). The one allowed update is
typist.services.keystrokes.record_key_up, which fills in t_up_ms and dwell_ms once (T1.1 owner
answer 6). There are no triggers; that single write path is the convention.
"""

from typing import Any, ClassVar, Final

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from typist.models.base import sql_in

KEYSTROKE_OUTCOMES: Final[tuple[str, ...]] = ("correct", "error", "backspace")


class KeystrokeEvent(SQLModel, table=True):
    """One key press in one block; times are milliseconds relative to block start (section 12).

    NULL means "not known" (T1.1 owner answer 5): t_up_ms and dwell_ms until the key-up arrives
    (it may never, section 12.4); iki_ms and release_to_press_ms at seq 0, and
    release_to_press_ms also when the previous key's t_up was unknown at insert (it is never
    backfilled); expected_char and first_attempt on backspace rows. release_to_press_ms is
    negative under rollover and dwell_ms is stored even when odd (section 12.6 checks flag it),
    so neither has a CHECK. after_pause is true only for the first key after the window regains
    focus following a blur (D24); IKI over 2000 ms is derived from t_down_ms at analysis time.
    id is the SQLite rowid (INTEGER PRIMARY KEY, no AUTOINCREMENT). (block_id, seq) is unique so
    uploads can use ON CONFLICT (block_id, seq) DO NOTHING (section 12.4).
    """

    # ClassVar[Any]: see "Table names" in typist/models/__init__.py.
    __tablename__: ClassVar[Any] = "keystroke_events"
    __table_args__ = (
        sa.UniqueConstraint("block_id", "seq"),
        sa.CheckConstraint(sql_in("outcome", KEYSTROKE_OUTCOMES), name="outcome"),
        sa.CheckConstraint("seq >= 0", name="seq"),
    )

    id: int | None = Field(default=None, primary_key=True)
    block_id: str = Field(foreign_key="session_blocks.id")
    seq: int
    key: str
    code: str
    t_down_ms: float
    t_up_ms: float | None = None
    dwell_ms: float | None = None
    iki_ms: float | None = None
    release_to_press_ms: float | None = None
    target_index: int
    expected_char: str | None = None
    outcome: str
    first_attempt: bool | None = None
    after_pause: bool = Field(default=False, sa_column_kwargs={"server_default": sa.text("0")})
    handler_ms: float
    dispatch_lag_ms: float
