"""The `typist` command: `typist db migrate` wraps alembic upgrade head."""

from pathlib import Path

from typer.testing import CliRunner

from typist.cli import app

runner = CliRunner()


def test_db_migrate_upgrades_the_configured_database(isolated_settings: Path) -> None:
    result = runner.invoke(app, ["db", "migrate"])
    assert result.exit_code == 0, result.output
    assert isolated_settings.is_file()


def test_help_lists_the_db_migrate_command() -> None:
    root = runner.invoke(app, ["--help"])
    assert root.exit_code == 0, root.output
    assert "db" in root.output
    group = runner.invoke(app, ["db", "--help"])
    assert group.exit_code == 0, group.output
    assert "migrate" in group.output
