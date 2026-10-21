"""Pure-path fixture, order-independence and property tests for attribution (T1.7 owner answers 2, 5)."""

import json
import random
from dataclasses import asdict
from pathlib import Path
from typing import Any, Final

from hypothesis import given
from hypothesis import strategies as st
from unit._stream_strategy import build_stream, letter_pair_positions, targets

from typist.models import KeystrokeEvent
from typist.services.attribution import attribute_block

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


def _golden() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _fixture_events(golden: dict[str, Any]) -> list[KeystrokeEvent]:
    return [
        KeystrokeEvent(block_id="golden", **{field: row[field] for field in ROW_FIELDS})
        for row in golden["keystrokes"]
    ]


def _expected_rows(golden: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        (
            {field: entry[field] for field in EXPECTED_FIELDS}
            for entry in golden["expected_bigram_stats"]
        ),
        key=lambda row: row["bigram"],
    )


def test_attribution_pure_path_matches_the_golden_fixture() -> None:
    golden = _golden()
    target = golden["session"]["target_text"]
    actual = [asdict(stat) for stat in attribute_block(target, _fixture_events(golden))]
    assert actual == _expected_rows(golden)


def test_attribution_is_order_independent() -> None:
    golden = _golden()
    target = golden["session"]["target_text"]
    events = _fixture_events(golden)
    shuffled = events.copy()
    random.Random(20261019).shuffle(shuffled)
    assert [asdict(stat) for stat in attribute_block(target, shuffled)] == [
        asdict(stat) for stat in attribute_block(target, events)
    ]


@given(data=st.data())
def test_attempts_never_exceed_letter_pair_positions(data: st.DataObject) -> None:
    target = data.draw(targets())
    rows = build_stream(data.draw, target)
    stats = attribute_block(target, rows)
    total_attempts = sum(stat.attempts for stat in stats)
    assert total_attempts <= letter_pair_positions(target)
    for stat in stats:
        assert stat.errors <= stat.attempts
        assert stat.iki_n <= stat.attempts
        assert (stat.iki_median_ms is None) == (stat.iki_n == 0)


@given(data=st.data())
def test_property_result_is_order_independent(data: st.DataObject) -> None:
    target = data.draw(targets())
    rows = build_stream(data.draw, target)
    shuffled = rows.copy()
    random.Random(data.draw(st.integers())).shuffle(shuffled)
    assert [asdict(stat) for stat in attribute_block(target, shuffled)] == [
        asdict(stat) for stat in attribute_block(target, rows)
    ]
