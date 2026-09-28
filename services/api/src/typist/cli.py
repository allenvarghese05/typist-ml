"""The `typist` command (design doc section 14.1). T0.3 adds only `typist db migrate`."""

import typer

from typist.migrations import upgrade_to_head

app = typer.Typer(help="Typist-ML admin commands.", no_args_is_help=True, add_completion=False)
db_app = typer.Typer(help="Database commands.", no_args_is_help=True)
app.add_typer(db_app, name="db")


@app.callback()
def main() -> None:
    """Typist-ML admin commands (design doc section 14.1)."""


@db_app.callback()
def db() -> None:
    """Database commands."""


@db_app.command("migrate")
def migrate() -> None:
    """Run Alembic migrations: upgrade the configured database (TYPIST_DB_PATH) to head."""
    upgrade_to_head()
