"""Unit tests for scripted keystroke generation (design doc 16; T2.10)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session

from typist.api.routers.admin import get_word_index
from typist.config import get_settings
from typist.corpus.build import build_corpus
from typist.corpus.word_index import WordIndex
from typist.db import create_db_engine
from typist.main import create_app
from typist.migrations import upgrade_to_head
from typist.models import KeystrokeEvent, Participant
from typist.schemas.events import KeystrokeEventIn
from typist.services.attribution import attribute_block
from typist.services.pipeline_sim import generate_scripted_keystrokes, run_pipeline_simulation


@pytest.fixture
def migrated_engine(isolated_settings: Path) -> Iterator[Engine]:
    upgrade_to_head()
    engine = create_db_engine(isolated_settings)
    try:
        yield engine
    finally:
        engine.dispose()



def test_generate_scripted_keystrokes_empty() -> None:
    events = generate_scripted_keystrokes("")
    assert events == []


def test_generate_scripted_keystrokes_invariants() -> None:
    target = "the quick brown fox jumps over the lazy dog"
    events = generate_scripted_keystrokes(target, error_rate=0.25, seed=123)

    assert len(events) > len(target)  # Due to errors and backspaces

    for idx, ev in enumerate(events):
        assert ev.seq == idx
        KeystrokeEventIn.model_validate(ev)

        assert ev.dwell_ms is not None
        assert 20.0 <= ev.dwell_ms <= 300.0
        assert ev.t_up_ms == round(ev.t_down_ms + ev.dwell_ms, 2)

        if idx > 0:
            assert ev.t_down_ms > events[idx - 1].t_down_ms
            assert ev.iki_ms is not None
            assert ev.iki_ms > 0

        if ev.outcome == "backspace":
            assert ev.key == "Backspace"
            assert ev.code == "Backspace"
            assert ev.expected_char is None
            assert ev.first_attempt is None
        else:
            assert ev.expected_char is not None
            assert ev.first_attempt is not None
            assert ev.outcome in ("correct", "error")


def test_generate_scripted_keystrokes_attribution() -> None:
    target = "the the the the the the the the the"

    # Clean typing: 0 errors
    clean_events = generate_scripted_keystrokes(target, error_rate=0.0, seed=42)
    clean_rows = [KeystrokeEvent(block_id="test_clean", **e.model_dump()) for e in clean_events]
    clean_stats = {s.bigram: s for s in attribute_block(target, clean_rows)}
    assert "th" in clean_stats
    assert clean_stats["th"].attempts == 9
    assert clean_stats["th"].errors == 0

    # With moderate errors injected: errors must be attributed per D14
    err_events = generate_scripted_keystrokes(target, error_rate=0.3, seed=42)
    err_rows = [KeystrokeEvent(block_id="test_err", **e.model_dump()) for e in err_events]
    err_stats = {s.bigram: s for s in attribute_block(target, err_rows)}
    # An error on 'h' following a correct 't' attributes 1 attempt and 1 error to 'th'
    assert "th" in err_stats
    assert err_stats["th"].errors > 0


def test_run_pipeline_simulation_builder_status_and_replenishment(
    migrated_engine: Engine, isolated_settings: Path, tmp_path: Path
) -> None:
    corpus_dir = tmp_path / "corpus"
    build_corpus(corpus_dir, word_count=5000, tracked_count=50)
    index = WordIndex.load(corpus_dir)

    app = create_app(get_settings())
    app.dependency_overrides[get_word_index] = lambda: index
    client = TestClient(app)

    result = run_pipeline_simulation(
        client,
        migrated_engine,
        isolated_settings,
        index,
        participant_alias="test-builder",
        practice_days=4,
        is_builder=True,
    )

    assert result.status == "done"
    assert result.practice_sessions == 4

    with Session(migrated_engine) as session:
        p = session.get(Participant, result.participant_id)
        assert p is not None
        assert p.is_builder is True

