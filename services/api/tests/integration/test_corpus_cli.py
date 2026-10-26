"""typist corpus build, compose-baseline, and compose-retest: acceptance (coverage + recount +
word-disjointness from form A), idempotency, --replace, and error paths (T1.8, T2.7).
"""

import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, col, select
from typer.testing import CliRunner

from typist.cli import app
from typist.corpus.word_index import TOP_BIGRAMS_FILENAME, WordIndex
from typist.models import BigramAssignment, ExperimentConfig, Participant, SessionBlock, TextPassage
from typist.models import Session as TypingSession

runner = CliRunner()
FROZEN_AT = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)


def _shared_a_texts(engine: Engine) -> list[str]:
    with Session(engine) as session:
        passages = session.exec(
            select(TextPassage)
            .where(
                col(TextPassage.kind) == "baseline",
                col(TextPassage.form) == "A",
                col(TextPassage.participant_id).is_(None),
            )
            .order_by(col(TextPassage.part))
        ).all()
        return [p.text for p in passages]


def _participant_b_passages(engine: Engine, pid: str) -> list[TextPassage]:
    with Session(engine) as session:
        return list(
            session.exec(
                select(TextPassage)
                .where(
                    col(TextPassage.kind) == "retest",
                    col(TextPassage.form) == "B",
                    col(TextPassage.participant_id) == pid,
                )
                .order_by(col(TextPassage.part))
            ).all()
        )


def _recount(text: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for token in text.split(" "):
        for i in range(len(token) - 1):
            if token[i].isalpha() and token[i + 1].isalpha():
                counts[token[i : i + 2]] += 1
    return dict(counts)


def _seed_assigned_participant(
    session: Session, pid: str, bigrams: tuple[str, ...]
) -> None:
    session.add(Participant(id=pid, alias=pid, status="assigned"))
    session.flush()
    sets = ("A", "B", "C", "D")
    arms = ("control", "heuristic", "markov", "llm")
    for rank, bg in enumerate(bigrams, start=1):
        idx = (rank - 1) % 4
        session.add(
            BigramAssignment(
                participant_id=pid,
                bigram=bg,
                set_label=sets[idx],
                arm=arms[idx],
                baseline_rank=rank,
                weakness_score=0.1,
                baseline_attempts=20,
                baseline_errors=2,
                frozen_at=FROZEN_AT,
            )
        )
    session.commit()


def test_build_then_compose_covers_every_tracked_bigram(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    assert runner.invoke(app, ["corpus", "build"]).exit_code == 0
    assert runner.invoke(app, ["corpus", "compose-baseline"]).exit_code == 0

    corpus_dir = get_corpus_dir()
    index = WordIndex.load(corpus_dir)
    with Session(migrated_engine) as session:
        threshold = int(session.get(ExperimentConfig, "baseline_min_occurrences").value)  # type: ignore[union-attr]
        tracked_count = int(session.get(ExperimentConfig, "tracked_bigram_count").value)  # type: ignore[union-attr]
        passages = session.exec(
            select(TextPassage).where(
                col(TextPassage.kind) == "baseline",
                col(TextPassage.form) == "A",
                col(TextPassage.participant_id).is_(None),
            )
        ).all()

    combined: dict[str, int] = defaultdict(int)
    for passage in passages:
        assert passage.bigram_counts == _recount(passage.text)
        for bigram, count in _recount(passage.text).items():
            combined[bigram] += count

    tracked = index.tracked_bigrams[:tracked_count]
    below = [b for b in tracked if combined.get(b, 0) < threshold]
    assert below == [], below
    assert (corpus_dir / TOP_BIGRAMS_FILENAME).exists()


def test_compose_is_deterministic_across_runs(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    assert runner.invoke(app, ["corpus", "build"]).exit_code == 0
    assert runner.invoke(app, ["corpus", "compose-baseline"]).exit_code == 0
    first = _shared_a_texts(migrated_engine)
    second_run = runner.invoke(app, ["corpus", "compose-baseline"])
    assert second_run.exit_code == 0
    assert "unchanged" in second_run.stdout
    assert _shared_a_texts(migrated_engine) == first


def test_compose_retest_cli_covers_assigned_bigrams_at_40_and_avoids_form_a_words(
    isolated_settings: Path, migrated_engine: Engine
) -> None:
    help_res = runner.invoke(app, ["corpus", "compose-retest", "--help"])
    assert help_res.exit_code == 0
    clean_help = re.sub(r"\x1b\[[0-9;]*m", "", help_res.output)
    assert "--pid" in clean_help
    assert "--replace" in clean_help

    assert runner.invoke(app, ["corpus", "build"]).exit_code == 0
    index = WordIndex.load(get_corpus_dir())
    assigned = index.tracked_bigrams[:16]

    # Unknown participant -> exit 1.
    missing_pid = runner.invoke(app, ["corpus", "compose-retest", "--pid", "nope"])
    assert missing_pid.exit_code == 1
    assert "no participant" in missing_pid.output

    # Unassigned participant -> exit 1.
    with Session(migrated_engine) as session:
        session.add(Participant(id="p-unassigned", alias="p-unassigned"))
        session.commit()
    unassigned = runner.invoke(app, ["corpus", "compose-retest", "--pid", "p-unassigned"])
    assert unassigned.exit_code == 1
    assert "not assigned" in unassigned.output

    # Assigned participant, but form A not composed yet -> exit 1.
    with Session(migrated_engine) as session:
        _seed_assigned_participant(session, "p-retest-cli", assigned)
    no_form_a = runner.invoke(app, ["corpus", "compose-retest", "--pid", "p-retest-cli"])
    assert no_form_a.exit_code == 1
    assert "form A passages missing" in no_form_a.output

    # Compose form A, then compose form B.
    assert runner.invoke(app, ["corpus", "compose-baseline"]).exit_code == 0
    first = runner.invoke(app, ["corpus", "compose-retest", "--pid", "p-retest-cli"])
    assert first.exit_code == 0, first.output
    assert "created: 2 retest passages (form B) for p-retest-cli" in first.stdout

    # Second run is idempotent ('unchanged').
    second = runner.invoke(app, ["corpus", "compose-retest", "--pid", "p-retest-cli"])
    assert second.exit_code == 0, second.output
    assert "unchanged: 2 retest passages (form B) for p-retest-cli" in second.stdout

    form_a_words = {
        word for text in _shared_a_texts(migrated_engine) for word in text.split(" ")
    }
    passages = _participant_b_passages(migrated_engine, "p-retest-cli")
    assert len(passages) == 2

    combined: dict[str, int] = defaultdict(int)
    form_b_words: set[str] = set()
    for passage in passages:
        assert passage.bigram_counts == _recount(passage.text)
        form_b_words.update(passage.text.split(" "))
        for bg, count in passage.bigram_counts.items():
            combined[bg] += count

    for bg in assigned:
        assert combined[bg] >= 40, (bg, combined[bg])
    assert form_b_words.isdisjoint(form_a_words)

    # Tamper with stored form B text -> without --replace exits 1; with --replace replaces.
    with Session(migrated_engine) as session:
        row0 = session.exec(
            select(TextPassage).where(
                col(TextPassage.kind) == "retest",
                col(TextPassage.form) == "B",
                col(TextPassage.participant_id) == "p-retest-cli",
                col(TextPassage.part) == 0,
            )
        ).one()
        row0.text = "tampered text"
        session.add(row0)
        session.commit()

    diff_res = runner.invoke(app, ["corpus", "compose-retest", "--pid", "p-retest-cli"])
    assert diff_res.exit_code == 1
    assert "already exists and differs" in diff_res.output

    replace_res = runner.invoke(
        app, ["corpus", "compose-retest", "--pid", "p-retest-cli", "--replace"]
    )
    assert replace_res.exit_code == 0, replace_res.output
    assert "replaced: 2 retest passages (form B) for p-retest-cli" in replace_res.stdout

    # Reference part 0 in a SessionBlock and tamper again -> --replace is refused (exit 1).
    with Session(migrated_engine) as session:
        row0 = session.exec(
            select(TextPassage).where(
                col(TextPassage.kind) == "retest",
                col(TextPassage.form) == "B",
                col(TextPassage.participant_id) == "p-retest-cli",
                col(TextPassage.part) == 0,
            )
        ).one()
        row0.text = "tampered while in use"
        session.add(row0)
        typing_session = TypingSession(
            participant_id="p-retest-cli",
            phase="retest",
            day_index=1,
            client_info={},
            started_at=FROZEN_AT,
        )
        session.add(typing_session)
        session.flush()
        session.add(
            SessionBlock(
                session_id=typing_session.id,
                block_index=0,
                arm="test",
                passage_id=row0.id,
                target_text=row0.text,
            )
        )
        session.commit()

    in_use_res = runner.invoke(
        app, ["corpus", "compose-retest", "--pid", "p-retest-cli", "--replace"]
    )
    assert in_use_res.exit_code == 1
    assert "refusing to replace form B" in in_use_res.output


def get_corpus_dir() -> Path:
    from typist.config import get_settings

    return get_settings().corpus_dir
