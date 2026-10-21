"""DB-path golden fixture test for attribution (design doc 12.3; T1.7 owner answers 2, 3).

Inserts the 89 golden rows through the migrated schema (the same pattern as
test_golden_fixture.py), runs attribute_block_from_db, and asserts the 19 expected bigram rows
exactly. The fixture is frozen (CLAUDE.md): a mismatch is a bug to flag, never an edit.
"""

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from sqlalchemy import Engine
from sqlmodel import Session

from typist.models import KeystrokeEvent, Participant, SessionBlock
from typist.models import Session as TypingSession
from typist.services.attribution import attribute_block_from_db

FIXTURE_PATH: Final = Path(__file__).resolve().parents[1] / "fixtures" / "golden_session.json"
ROW_FIELDS: Final = (
    "seq",
    "key",
    "code",
    "t_down_ms",
    "t_up_ms",
    "dwell_ms",
    "iki_ms",
    "target_index",
    "expected_char",
    "outcome",
    "first_attempt",
    "after_pause",
    "handler_ms",
    "dispatch_lag_ms",
)
EXPECTED_FIELDS: Final = ("bigram", "attempts", "errors", "iki_median_ms", "iki_n")
STARTED_AT: Final = datetime(2026, 10, 6, 9, 0, 0, tzinfo=UTC)


def _golden() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _expected_rows(golden: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        (
            {field: entry[field] for field in EXPECTED_FIELDS}
            for entry in golden["expected_bigram_stats"]
        ),
        key=lambda row: row["bigram"],
    )


def test_attribution_db_path_matches_the_golden_fixture(migrated_engine: Engine) -> None:
    golden = _golden()
    rows = [{field: row[field] for field in ROW_FIELDS} for row in golden["keystrokes"]]
    with Session(migrated_engine) as session:
        participant = Participant(alias="golden")
        session.add(participant)
        session.flush()
        typing_session = TypingSession(
            participant_id=participant.id,
            phase=golden["session"]["phase"],
            day_index=1,
            client_info={"source": "golden_session.json"},
            started_at=STARTED_AT,
        )
        session.add(typing_session)
        session.flush()
        block = SessionBlock(
            session_id=typing_session.id,
            block_index=golden["session"]["block_index"],
            arm=golden["session"]["arm"],
            target_text=golden["session"]["target_text"],
        )
        session.add(block)
        session.flush()
        block_id = block.id
        session.add_all([KeystrokeEvent(block_id=block_id, **values) for values in rows])
        session.commit()
        actual = [asdict(stat) for stat in attribute_block_from_db(session, block_id)]
    assert actual == _expected_rows(golden)
    assert len(actual) == 19
    assert sum(row["attempts"] for row in actual) == 26
    assert sum(row["errors"] for row in actual) == 6
    assert sum(row["iki_n"] for row in actual) == 18
