"""Golden fixture: structural consistency only (T1.2 owner answers 3, 12, 13, 15, 18; F12).

Checks that tests/fixtures/golden_session.json is well formed, that each stored row agrees with
its own timestamps, that derived_expectations agrees with the rows, and that every row inserts
unchanged into the migrated keystroke_events table. It never counts bigrams, applies skip rules
or takes medians: the expected values were derived by hand (docs/plans/T1.2-derivation.md), and
only the code under test (T1.3, T1.7, T1.9) reproduces them. Keys starting with "_" are notes;
keys starting with "review_aid_" are never asserted.
"""

import json
import string
from datetime import UTC, datetime
from functools import cache
from itertools import pairwise
from pathlib import Path
from typing import Any, Final

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from typist.models import KeystrokeEvent, Participant, SessionBlock
from typist.models import Session as TypingSession

FIXTURE_PATH: Final = Path(__file__).resolve().parents[1] / "fixtures" / "golden_session.json"

TOP_LEVEL_KEYS: Final = frozenset(
    {
        "format_version",
        "description",
        "created_date",
        "author",
        "changelog",
        "_note",
        "session",
        "case_index",
        "keystrokes",
        "expected_session",
        "expected_bigram_stats",
        "derived_expectations",
        "review_aid_position_trace",
    }
)
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
ROW_KEYS: Final = frozenset({*ROW_FIELDS, "case_labels", "_note"})
TIME_FIELDS: Final = ("t_down_ms", "t_up_ms", "dwell_ms", "iki_ms", "handler_ms", "dispatch_lag_ms")
REQUIRED_CASES: Final = frozenset("abcdefghijklmnopqs")
CASE_KEYS: Final = frozenset({"title", "seq_ranges", "_note"})
BIGRAM_KEYS: Final = frozenset(
    {"bigram", "attempts", "errors", "iki_median_ms", "iki_n", "review_aid_iki_samples_ms", "_note"}
)
SESSION_KEYS: Final = frozenset(
    {"correct_first_attempts", "first_attempts", "accuracy", "typing_time_ms", "wpm", "_note"}
)
TYPED_CHARS: Final = frozenset(string.ascii_lowercase + " ")
LETTERS: Final = frozenset(string.ascii_lowercase)
STARTED_AT: Final = datetime(2026, 10, 6, 9, 0, 0, tzinfo=UTC)


@cache
def _golden() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _rows() -> list[dict[str, Any]]:
    return _golden()["keystrokes"]


def _is_quarter_ms(value: float) -> bool:
    return (float(value) * 4).is_integer()


def test_top_level_keys_and_format_version() -> None:
    golden = _golden()
    assert set(golden) == TOP_LEVEL_KEYS
    assert golden["format_version"] == 1
    assert golden["changelog"][0]["format_version"] == 1


def test_session_is_one_baseline_test_block() -> None:
    session = _golden()["session"]
    assert session["phase"] == "baseline"
    assert session["arm"] == "test"
    assert session["block_index"] == 0
    assert set(session["target_text"]) <= TYPED_CHARS


def test_rows_have_exactly_the_row_keys() -> None:
    for row in _rows():
        assert set(row) == ROW_KEYS, row["seq"]


def test_seq_is_contiguous_from_zero() -> None:
    rows = _rows()
    assert [row["seq"] for row in rows] == list(range(len(rows)))


def test_iki_is_the_press_to_press_difference() -> None:
    rows = _rows()
    assert rows[0]["iki_ms"] is None
    for previous, row in pairwise(rows):
        assert row["iki_ms"] == row["t_down_ms"] - previous["t_down_ms"], row["seq"]


def test_dwell_is_release_minus_press() -> None:
    for row in _rows():
        if row["t_up_ms"] is None:
            assert row["dwell_ms"] is None, row["seq"]
        else:
            assert row["dwell_ms"] == row["t_up_ms"] - row["t_down_ms"], row["seq"]


def test_release_to_press_is_press_minus_previous_release() -> None:
    rows = _rows()
    entries = _golden()["derived_expectations"]["release_to_press_ms"]
    expected: list[float | None] = [None]
    expected.extend(
        None if previous["t_up_ms"] is None else row["t_down_ms"] - previous["t_up_ms"]
        for previous, row in pairwise(rows)
    )
    assert [entry["release_to_press_ms"] for entry in entries] == expected


def test_times_are_whole_or_quarter_milliseconds() -> None:
    row_times = [row[field] for row in _rows() for field in TIME_FIELDS if row[field] is not None]
    derived = [
        entry["release_to_press_ms"]
        for entry in _golden()["derived_expectations"]["release_to_press_ms"]
        if entry["release_to_press_ms"] is not None
    ]
    assert [value for value in row_times if not _is_quarter_ms(value)] == []
    assert [value for value in derived if not _is_quarter_ms(value)] == []


def test_rows_follow_the_keystroke_schema_rules() -> None:
    target_length = len(_golden()["session"]["target_text"])
    for row in _rows():
        seq = row["seq"]
        assert 0 <= row["target_index"] < target_length, seq
        assert isinstance(row["after_pause"], bool), seq
        assert row["handler_ms"] is not None, seq
        assert row["dispatch_lag_ms"] is not None, seq
        if row["outcome"] == "backspace":
            assert (row["key"], row["code"]) == ("Backspace", "Backspace"), seq
            assert row["expected_char"] is None, seq
            assert row["first_attempt"] is None, seq
        else:
            assert row["outcome"] in {"correct", "error"}, seq
            assert row["key"] in TYPED_CHARS, seq
            assert row["expected_char"] in TYPED_CHARS, seq
            assert isinstance(row["first_attempt"], bool), seq


def test_case_index_covers_every_required_case() -> None:
    cases = _golden()["case_index"]
    last_seq = len(_rows()) - 1
    assert set(cases) == REQUIRED_CASES
    for label, case in cases.items():
        assert set(case) == CASE_KEYS, label
        assert case["seq_ranges"], label
        for first, last in case["seq_ranges"]:
            assert 0 <= first <= last <= last_seq, label


def test_row_case_labels_match_the_case_index() -> None:
    rows = _rows()
    used = {label for row in rows for label in row["case_labels"]}
    assert used == REQUIRED_CASES
    for label, case in _golden()["case_index"].items():
        in_ranges = {seq for first, last in case["seq_ranges"] for seq in range(first, last + 1)}
        labelled = {row["seq"] for row in rows if label in row["case_labels"]}
        assert labelled == in_ranges, label


def test_expected_bigram_stats_have_the_agreed_shape() -> None:
    stats = _golden()["expected_bigram_stats"]
    bigrams = [entry["bigram"] for entry in stats]
    assert len(bigrams) == len(set(bigrams))
    for entry in stats:
        bigram = entry["bigram"]
        assert set(entry) == BIGRAM_KEYS, bigram
        assert len(bigram) == 2, bigram
        assert set(bigram) <= LETTERS, bigram
        assert entry["attempts"] >= 1, bigram
        assert (entry["iki_median_ms"] is None) == (entry["iki_n"] == 0), bigram


def test_expected_session_and_derived_expectations_have_the_agreed_shape() -> None:
    golden = _golden()
    assert set(golden["expected_session"]) == SESSION_KEYS
    seqs = [entry["seq"] for entry in golden["derived_expectations"]["release_to_press_ms"]]
    assert seqs == list(range(len(_rows())))


def test_rows_insert_unchanged_into_the_migrated_schema(migrated_engine: Engine) -> None:
    golden = _golden()
    expected = [{field: row[field] for field in ROW_FIELDS} for row in _rows()]
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
        session.add_all([KeystrokeEvent(block_id=block_id, **values) for values in expected])
        session.commit()
    with Session(migrated_engine) as session:
        stored = session.exec(
            select(KeystrokeEvent).where(col(KeystrokeEvent.block_id) == block_id)
        ).all()
        ordered = sorted(stored, key=lambda event: event.seq)
        actual = [{field: getattr(event, field) for field in ROW_FIELDS} for event in ordered]
        assert all(event.release_to_press_ms is None for event in ordered)
    assert actual == expected
