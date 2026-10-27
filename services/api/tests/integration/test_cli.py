"""The `typist` command: `typist db migrate`, `typist worker`, and cli tests (T0.3, T2.5)."""

import re
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, col, select
from typer.testing import CliRunner

from typist.cli import app
from typist.config import get_settings
from typist.corpus.build import build_corpus
from typist.db import create_db_engine
from typist.models import Drill, GenerationJob, Participant
from typist.worker import heartbeat_path

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


def test_help_lists_the_worker_command() -> None:
    root = runner.invoke(app, ["--help"])
    assert root.exit_code == 0, root.output
    assert "worker" in root.output
    worker_help = runner.invoke(app, ["worker", "--help"])
    assert worker_help.exit_code == 0, worker_help.output
    plain = re.sub(r"\x1b\[[0-9;]*m", "", worker_help.output)
    assert "--once" in plain
    assert "--poll-interval" in plain


def test_worker_exits_1_when_corpus_is_missing(isolated_settings: Path) -> None:
    migrate_result = runner.invoke(app, ["db", "migrate"])
    assert migrate_result.exit_code == 0, migrate_result.output
    result = runner.invoke(app, ["worker", "--once"])
    assert result.exit_code == 1, result.output
    assert "corpus artifacts missing" in result.output


def test_worker_once_claims_job_generates_drills_and_writes_heartbeat(
    isolated_settings: Path,
) -> None:
    migrate_result = runner.invoke(app, ["db", "migrate"])
    assert migrate_result.exit_code == 0, migrate_result.output

    settings = get_settings()
    build_corpus(settings.corpus_dir, word_count=20000, tracked_count=150)

    engine = create_db_engine(isolated_settings)
    with Session(engine) as session:
        participant = Participant(id="p-cli", alias="p-cli")
        session.add(participant)
        session.flush()
        job = GenerationJob(
            participant_id="p-cli",
            arm="control",
            requested=1,
            status="pending",
        )
        session.add(job)
        session.commit()
        job_id = job.id

    result = runner.invoke(app, ["worker", "--once"])
    assert result.exit_code == 0, result.output

    with Session(engine) as session:
        refreshed_job = session.get(GenerationJob, job_id)
        assert refreshed_job is not None
        assert refreshed_job.status == "done"

        drills = session.exec(select(Drill).where(col(Drill.participant_id) == "p-cli")).all()
        assert len(drills) == 1
        assert drills[0].status == "ready"

    assert heartbeat_path(isolated_settings).is_file()


def test_participant_add_and_delete_cli(migrated_engine: Engine, isolated_settings: Path) -> None:
    result = runner.invoke(app, ["participant", "add", "--alias", "cli_test_user", "--builder"])
    assert result.exit_code == 0
    assert "created participant" in result.output
    assert "builder=True" in result.output

    dup_result = runner.invoke(app, ["participant", "add", "--alias", "cli_test_user"])
    assert dup_result.exit_code == 1
    assert "already exists" in dup_result.output

    with Session(migrated_engine) as session:
        p = session.exec(select(Participant).where(col(Participant.alias) == "cli_test_user")).one()
        pid = p.id

    del_result = runner.invoke(app, ["participant", "delete", "--pid", pid])
    assert del_result.exit_code == 0
    assert f"deleted participant {pid}" in del_result.output

    missing_del = runner.invoke(app, ["participant", "delete", "--pid", "missing-pid"])
    assert missing_del.exit_code == 1
    assert "no participant with id 'missing-pid'" in missing_del.output
