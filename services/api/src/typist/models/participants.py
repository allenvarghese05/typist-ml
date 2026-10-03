"""participants table (design doc section 8.1): one row per person, stored by alias only (4.2)."""

from datetime import datetime
from typing import Any, ClassVar, Final

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from typist.models.base import new_id, sql_in

PARTICIPANT_STATUSES: Final[tuple[str, ...]] = (
    "enrolled",
    "baseline",
    "assigned",
    "practice",
    "retest",
    "done",
    "withdrawn",
)


class Participant(SQLModel, table=True):
    """A participant. status follows section 9.3; transitions are enforced in services (T2.8).

    The builder is never blinded (D18): CHECK is_builder = 0 OR is_blinded = 0. consent_at and
    keyboard_label are unknown at enrolment. created_at is filled by the database
    (CURRENT_TIMESTAMP, UTC, whole seconds) when the app leaves it None.
    """

    # ClassVar[Any]: see "Table names" in typist/models/__init__.py.
    __tablename__: ClassVar[Any] = "participants"
    __table_args__ = (
        sa.UniqueConstraint("alias"),
        sa.CheckConstraint(sql_in("status", PARTICIPANT_STATUSES), name="status"),
        sa.CheckConstraint("is_builder = 0 OR is_blinded = 0", name="builder_not_blinded"),
    )

    id: str = Field(default_factory=new_id, primary_key=True)
    alias: str
    is_builder: bool = False
    is_blinded: bool = True
    status: str = "enrolled"
    keyboard_label: str | None = None
    consent_at: datetime | None = None
    created_at: datetime | None = Field(
        default=None,
        nullable=False,
        sa_column_kwargs={"server_default": sa.text("CURRENT_TIMESTAMP")},
    )
