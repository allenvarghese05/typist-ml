"""SQLModel table classes, one module per table group (design doc sections 7 and 8.1).

Importing this package registers every table on SQLModel.metadata (alembic/env.py relies on it).
`base` is imported first: it sets the constraint naming convention before any table is defined.
The class Session is a typing session; import it as TypingSession next to sqlmodel.Session.

Table names: every class declares `__tablename__: ClassVar[Any] = "<name>"`. sqlmodel 0.0.47
declares SQLModel.__tablename__ last as a `@declared_attr` method, so pyright sees the inherited
type as declared_attr[Unknown]; a plain str assignment, or a ClassVar[str] override, is rejected.
ClassVar[Any] passes pyright's override check with no suppression comment and changes nothing at
runtime (SQLAlchemy reads the string). Read a class's table name with
sqlalchemy.inspect(Model).tables[0].name, not Model.__tablename__.
"""

from typist.models import base
from typist.models.experiment_config import ExperimentConfig
from typist.models.keystroke_events import KeystrokeEvent
from typist.models.participants import Participant
from typist.models.sessions import Session, SessionBlock
from typist.models.text_passages import TextPassage

__all__ = [
    "ExperimentConfig",
    "KeystrokeEvent",
    "Participant",
    "Session",
    "SessionBlock",
    "TextPassage",
    "base",
]
