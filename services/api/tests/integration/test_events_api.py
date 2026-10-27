"""POST /api/v1/blocks/{block_id}/events on a temporary SQLite file (design doc 17.2, 12.4)."""

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from typist.config import Settings
from typist.main import create_app


def event(seq: int, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "seq": seq,
        "key": "a",
        "code": "KeyA",
        "t_down_ms": seq * 100.0,
        "t_up_ms": seq * 100.0 + 50.0,
        "dwell_ms": 50.0,
        "iki_ms": None if seq == 0 else 100.0,
        "target_index": seq,
        "expected_char": "a",
        "outcome": "correct",
        "first_attempt": True,
        "after_pause": False,
        "handler_ms": 0.2,
        "dispatch_lag_ms": 0.5,
    }
    base.update(over)
    return base


def client_for(db_path: Path) -> TestClient:
    return TestClient(create_app(Settings(db_path=db_path)))


def _block_count(db_path: Path, block_id: str) -> int:
    with closing(sqlite3.connect(db_path)) as connection:
        return connection.execute(
            "SELECT count(*) FROM keystroke_events WHERE block_id = ?", (block_id,)
        ).fetchone()[0]


def _seqs(db_path: Path, block_id: str) -> list[int]:
    with closing(sqlite3.connect(db_path)) as connection:
        return [
            row[0]
            for row in connection.execute(
                "SELECT seq FROM keystroke_events WHERE block_id = ? AND seq >= 10 ORDER BY seq",
                (block_id,),
            ).fetchall()
        ]


def test_same_batch_twice_stores_it_once(
    isolated_settings: Path, migrated_engine: Engine, seeded_ids: dict[str, str]
) -> None:
    block = seeded_ids["block_id"]
    batch = {"events": [event(10), event(11), event(12)]}
    with client_for(isolated_settings) as client:
        first = client.post(f"/api/v1/blocks/{block}/events", json=batch)
        second = client.post(f"/api/v1/blocks/{block}/events", json=batch)
    assert first.status_code == 200
    assert first.json() == {"accepted": 3, "duplicates": 0}
    assert second.status_code == 200
    assert second.json() == {"accepted": 0, "duplicates": 3}
    assert _seqs(isolated_settings, block) == [10, 11, 12]
    assert _block_count(isolated_settings, block) == 4  # seeded seq 0 + three new rows


def test_partial_overlap_inserts_only_the_new_rows(
    isolated_settings: Path, migrated_engine: Engine, seeded_ids: dict[str, str]
) -> None:
    block = seeded_ids["block_id"]
    with client_for(isolated_settings) as client:
        first = client.post(
            f"/api/v1/blocks/{block}/events", json={"events": [event(10), event(11)]}
        )
        second = client.post(
            f"/api/v1/blocks/{block}/events",
            json={"events": [event(11), event(12), event(13)]},
        )
    assert first.json() == {"accepted": 2, "duplicates": 0}
    assert second.json() == {"accepted": 2, "duplicates": 1}
    assert _seqs(isolated_settings, block) == [10, 11, 12, 13]


def test_empty_batch_is_a_noop(
    isolated_settings: Path, migrated_engine: Engine, seeded_ids: dict[str, str]
) -> None:
    block = seeded_ids["block_id"]
    with client_for(isolated_settings) as client:
        response = client.post(f"/api/v1/blocks/{block}/events", json={"events": []})
    assert response.status_code == 200
    assert response.json() == {"accepted": 0, "duplicates": 0}
    assert _block_count(isolated_settings, block) == 1  # only the seeded row


def test_unknown_block_returns_404(
    isolated_settings: Path, migrated_engine: Engine, seeded_ids: dict[str, str]
) -> None:
    with client_for(isolated_settings) as client:
        response = client.post("/api/v1/blocks/no-such-block/events", json={"events": [event(10)]})
    assert response.status_code == 404
    assert response.json() == {"detail": "block not found"}
    with closing(sqlite3.connect(isolated_settings)) as connection:
        total = connection.execute("SELECT count(*) FROM keystroke_events").fetchone()[0]
    assert total == 1  # nothing inserted anywhere


def test_stores_nullable_and_backspace_fields(
    isolated_settings: Path, migrated_engine: Engine, seeded_ids: dict[str, str]
) -> None:
    block = seeded_ids["block_id"]
    backspace = event(
        10,
        key="Backspace",
        code="Backspace",
        outcome="backspace",
        expected_char=None,
        first_attempt=None,
        t_up_ms=None,
        dwell_ms=None,
        after_pause=True,
    )
    no_key_up = event(11, t_up_ms=None, dwell_ms=None)
    with client_for(isolated_settings) as client:
        response = client.post(
            f"/api/v1/blocks/{block}/events", json={"events": [backspace, no_key_up]}
        )

    assert response.json() == {"accepted": 2, "duplicates": 0}
    with closing(sqlite3.connect(isolated_settings)) as connection:
        bs = connection.execute(
            "SELECT key, outcome, expected_char, first_attempt, t_up_ms, dwell_ms, "
            "release_to_press_ms, after_pause FROM keystroke_events "
            "WHERE block_id = ? AND seq = 10",
            (block,),
        ).fetchone()
        nk = connection.execute(
            "SELECT t_up_ms, dwell_ms, release_to_press_ms, after_pause, first_attempt "
            "FROM keystroke_events WHERE block_id = ? AND seq = 11",
            (block,),
        ).fetchone()
    assert bs == ("Backspace", "backspace", None, None, None, None, None, 1)
    assert nk == (None, None, None, 0, 1)


INVALID_ROWS = [
    pytest.param({**event(10), "seq": -1}, id="negative-seq"),
    pytest.param(event(10, outcome="skip"), id="bad-outcome"),
    pytest.param(event(10, key="A"), id="uppercase-key"),
    pytest.param(event(10, code=""), id="empty-code"),
    pytest.param(
        event(
            10,
            outcome="backspace",
            key="Backspace",
            code="Backspace",
            expected_char="a",
            first_attempt=None,
            t_up_ms=None,
            dwell_ms=None,
        ),
        id="backspace-with-expected-char",
    ),
    pytest.param(event(10, expected_char=None), id="non-backspace-missing-expected-char"),
    pytest.param(event(10, dwell_ms=None), id="t_up-without-dwell"),
]


@pytest.mark.parametrize("bad", INVALID_ROWS)
def test_invalid_row_rejects_the_whole_batch(
    isolated_settings: Path,
    migrated_engine: Engine,
    seeded_ids: dict[str, str],
    bad: dict[str, Any],
) -> None:
    block = seeded_ids["block_id"]
    with client_for(isolated_settings) as client:
        response = client.post(f"/api/v1/blocks/{block}/events", json={"events": [event(20), bad]})
    assert response.status_code == 422
    assert _block_count(isolated_settings, block) == 1  # the valid row in the batch is not inserted


def test_large_event_batch_chunked_safely(
    isolated_settings: Path, migrated_engine: Engine, seeded_ids: dict[str, str]
) -> None:
    block = seeded_ids["block_id"]
    batch = {"events": [event(10 + i) for i in range(2500)]}
    with client_for(isolated_settings) as client:
        response = client.post(f"/api/v1/blocks/{block}/events", json=batch)
    assert response.status_code == 200
    assert response.json() == {"accepted": 2500, "duplicates": 0}
    assert _block_count(isolated_settings, block) == 2501  # seeded seq 0 + 2500 new rows
