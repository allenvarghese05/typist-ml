"""Alembic environment for services/api.

Migrates the database the app uses: Settings.db_path (TYPIST_DB_PATH, default
<repo>/data/typist.db), opened through typist.db.create_db_engine so migrations get the same
SQLite pragmas. SQLite alters tables only in limited ways, so migrations render in batch mode.
"""

from logging.config import fileConfig

from alembic import context
from sqlmodel import SQLModel

# Imported for its side effect: table modules register themselves on SQLModel.metadata.
import typist.models  # noqa: F401
from typist.config import get_settings
from typist.db import create_db_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Emit SQL for `alembic upgrade --sql` without connecting to the database."""
    context.configure(
        url=f"sqlite:///{get_settings().db_path}",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations over a connection that has the app's pragmas (WAL, foreign keys)."""
    engine = create_db_engine(get_settings().db_path)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
