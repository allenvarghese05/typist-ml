"""text_passages table (design doc section 8.1): baseline (form A) and retest (form B) texts."""

from typing import Any, ClassVar, Final

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from typist.models.base import new_id, sql_in

TEXT_PASSAGE_KINDS: Final[tuple[str, ...]] = ("baseline", "retest")
TEXT_PASSAGE_FORMS: Final[tuple[str, ...]] = ("A", "B")


class TextPassage(SQLModel, table=True):
    """A test passage. participant_id is NULL for shared texts, set for one participant's retest.

    For test sessions, part equals the block_index of the session_blocks row that shows the
    passage (T1.1 owner answer 12). SQLite treats NULLs as distinct in unique indexes, so two
    partial unique indexes enforce uniqueness: (kind, form, part) among shared rows and
    (kind, form, part, participant_id) among per-participant rows (owner answer 11).
    """

    # ClassVar[Any]: see "Table names" in typist/models/__init__.py.
    __tablename__: ClassVar[Any] = "text_passages"
    __table_args__ = (
        sa.CheckConstraint(sql_in("kind", TEXT_PASSAGE_KINDS), name="kind"),
        sa.CheckConstraint(sql_in("form", TEXT_PASSAGE_FORMS), name="form"),
        sa.Index(
            "uq_text_passages_shared_kind_form_part",
            "kind",
            "form",
            "part",
            unique=True,
            sqlite_where=sa.text("participant_id IS NULL"),
        ),
        sa.Index(
            "uq_text_passages_participant_kind_form_part",
            "kind",
            "form",
            "part",
            "participant_id",
            unique=True,
            sqlite_where=sa.text("participant_id IS NOT NULL"),
        ),
    )

    id: str = Field(default_factory=new_id, primary_key=True)
    kind: str
    form: str
    part: int
    participant_id: str | None = Field(default=None, foreign_key="participants.id")
    text: str
    bigram_counts: dict[str, int] = Field(sa_type=sa.JSON)
