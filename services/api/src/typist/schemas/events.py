"""Schemas for POST /api/v1/blocks/{block_id}/events (design doc 14, 12.4; T1.6 owner answers 4, 5, 10)."""

import re
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

KeystrokeOutcomeLiteral = Literal["correct", "error", "backspace"]

_TYPED_KEY = re.compile(r"[a-z ]")


class KeystrokeEventIn(BaseModel):
    """One keystroke_events row as the browser sends it (T1.4 KeystrokeRow; owner answers 4, 10).

    Field names are the column names. block_id is not here (it is the path, owner answer 4) and
    release_to_press_ms is never sent (owner answer 3). Nullable fields are required but may be
    null. The validator enforces the D13 charset and the backspace/t_up invariants; an invalid row
    rejects the whole batch with 422.
    """

    seq: int = Field(ge=0)
    key: str
    code: str = Field(min_length=1)
    t_down_ms: float
    t_up_ms: float | None
    dwell_ms: float | None
    iki_ms: float | None
    target_index: int = Field(ge=0)
    expected_char: str | None
    outcome: KeystrokeOutcomeLiteral
    first_attempt: bool | None
    after_pause: bool
    handler_ms: float
    dispatch_lag_ms: float

    @model_validator(mode="after")
    def _check_invariants(self) -> Self:
        if self.outcome == "backspace":
            if self.key != "Backspace":
                raise ValueError("a backspace row must have key 'Backspace'")
            if self.expected_char is not None or self.first_attempt is not None:
                raise ValueError("a backspace row must have null expected_char and first_attempt")
        else:
            if self.key == "Backspace" or _TYPED_KEY.fullmatch(self.key) is None:
                raise ValueError("key must be a single a-z or space character")
            if self.expected_char is None or self.first_attempt is None:
                raise ValueError("a non-backspace row must set expected_char and first_attempt")
        if (self.t_up_ms is None) != (self.dwell_ms is None):
            raise ValueError("t_up_ms and dwell_ms must both be null or both set")
        return self


class EventBatchIn(BaseModel):
    """The request body: a batch of rows. An empty list is a valid no-op (brief edge case 7)."""

    events: list[KeystrokeEventIn]


class EventBatchResult(BaseModel):
    """Response: rows inserted vs skipped as duplicates (section 14; owner answer 5)."""

    accepted: int
    duplicates: int
