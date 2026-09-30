"""Shared pieces of the table modules: constraint naming, row ids and CHECK text (T1.1).

Importing this module sets SQLModel.metadata's naming convention (T1.1 owner answer 19), so every
constraint gets a stable name that later SQLite batch migrations can address.
typist/models/__init__.py imports this module before any table module.
"""

import uuid
from collections.abc import Sequence
from typing import Final

from sqlmodel import SQLModel

NAMING_CONVENTION: Final[dict[str, str]] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

SQLModel.metadata.naming_convention = NAMING_CONVENTION


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
