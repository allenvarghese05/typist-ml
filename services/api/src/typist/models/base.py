"""Shared pieces of the table modules: constraint naming, row ids, CHECK text and JSON (T1.1).

Importing this module sets SQLModel.metadata's naming convention (T1.1 owner answer 19), so every
constraint gets a stable name that later SQLite batch migrations can address.
typist/models/__init__.py imports this module before any table module.
"""

import json
import uuid
from collections.abc import Sequence
from typing import Any, Final, override

from sqlalchemy.engine import Dialect
from sqlalchemy.types import Text, TypeDecorator
from sqlmodel import SQLModel

NAMING_CONVENTION: Final[dict[str, str]] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

SQLModel.metadata.naming_convention = NAMING_CONVENTION


class JSONText(TypeDecorator[Any]):
    """A JSON value stored as TEXT (T1.1 Revision 3).

    SQLAlchemy's JSON type declares the column JSON, which has NUMERIC affinity in SQLite, so JSON
    text such as "10" or "0.4" is stored as a number and then fails JSON decoding on read. This
    type declares TEXT, writes json.dumps(value) and reads json.loads(text). Python None is SQL
    NULL in both directions; a JSON null value cannot be stored.
    """

    impl = Text
    cache_ok = True

    @override
    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        """Encode a Python value as JSON text; None stays SQL NULL."""
        if value is None:
            return None
        return json.dumps(value)

    @override
    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        """Decode stored JSON text; SQL NULL becomes None."""
        if value is None:
            return None
        return json.loads(value)


def new_id() -> str:
    """Return a new row id: a 36-character hyphenated UUID4 string (T1.1 owner answer 13).

    Ids are opaque and must differ between runs, so they come from uuid.uuid4() (the OS random
    source), not from a seeded generator. CLAUDE.md's seeded-randomness rule covers randomness
    that affects results (assignment, sampling, drill generation); row ids never do.
    """
    return str(uuid.uuid4())


def sql_in(column: str, values: Sequence[str]) -> str:
    """Return the CHECK text "<column> IN ('a', 'b', ...)" for a fixed set of allowed values.

    Values are literals from the model modules, never user input. A value containing a single
    quote raises ValueError.
    """
    if any("'" in value for value in values):
        raise ValueError("CHECK values must not contain a single quote")
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"
