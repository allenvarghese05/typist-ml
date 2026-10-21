"""session_stats end to end: golden fixture, two-block pooling, recompute idempotency (T1.9)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from typist.models import BigramStat, KeystrokeEvent, Participant, SessionBlock
from typist.models import Session as TypingSession
from typist.services.session_stats import (
    complete_session,
    compute_session_stats,
    recompute_stats,
)

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
NOW: Final = datetime(2026, 10, 19, 10, 0, 0, tzinfo=UTC)
STARTED_AT: Final = datetime(2026, 10, 6, 9, 0, 0, tzinfo=UTC)


def _golden() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _expected_bigrams(golden: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        (
            {field: entry[field] for field in EXPECTED_FIELDS}
            for entry in golden["expected_bigram_stats"]
        ),
        key=lambda row: row["bigram"],
    )


def _snapshot(session: Session, session_id: str) -> dict[str, Any]:
    row = session.get(TypingSession, session_id)
    assert row is not None
    stats = session.exec(select(BigramStat).where(col(BigramStat.session_id) == session_id)).all()
    bigrams = sorted(
        (
            {
                "bigram": s.bigram,
                "attempts": s.attempts,
                "errors": s.errors,
                "iki_median_ms": s.iki_median_ms,
                "iki_n": s.iki_n,
            }
            for s in stats
        ),
        key=lambda d: d["bigram"],
    )
    return {"wpm": row.wpm, "accuracy": row.accuracy, "bigrams": bigrams}


def _seed_participant(session: Session) -> str:
    participant = Participant(alias="golden")
    session.add(participant)
    session.flush()
    return participant.id


def _seed_golden_session(session: Session, participant_id: str, golden: dict[str, Any]) -> str:
    typing_session = TypingSession(
        participant_id=participant_id,
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
    rows = [{field: row[field] for field in ROW_FIELDS} for row in golden["keystrokes"]]
    session.add_all([KeystrokeEvent(block_id=block.id, **values) for values in rows])
    session.flush()
    return typing_session.id


def test_complete_golden_session_matches_the_fixture(migrated_engine: Engine) -> None:
    golden = _golden()
    with Session(migrated_engine) as session:
        participant_id = _seed_participant(session)
        session_id = _seed_golden_session(session, participant_id, golden)
        session.commit()
        stats = complete_session(session, session_id, NOW)
    assert stats.wpm == 22.0
    assert stats.accuracy == 0.859375
    assert stats.block_count == 1
    with Session(migrated_engine) as session:
        row = session.get(TypingSession, session_id)
        assert row is not None
        assert row.status == "completed"
        assert row.ended_at == NOW
        assert row.wpm == 22.0
        assert row.accuracy == 0.859375
        stored = session.exec(
            select(BigramStat).where(col(BigramStat.session_id) == session_id)
        ).all()
    actual = sorted(
        ({field: getattr(s, field) for field in EXPECTED_FIELDS} for s in stored),
        key=lambda d: d["bigram"],
    )
    assert actual == _expected_bigrams(golden)
    assert len(actual) == 19
    assert all(s.participant_id == participant_id for s in stored)


def test_recompute_reproduces_identical_numbers_twice(migrated_engine: Engine) -> None:
    golden = _golden()
    with Session(migrated_engine) as session:
        participant_id = _seed_participant(session)
        session_id = _seed_golden_session(session, participant_id, golden)
        session.commit()
        complete_session(session, session_id, NOW)
        first = _snapshot(session, session_id)
    with Session(migrated_engine) as session:
        result = recompute_stats(session, None)
        second = _snapshot(session, session_id)
    with Session(migrated_engine) as session:
        recompute_stats(session, participant_id)
        third = _snapshot(session, session_id)
    assert result.recomputed == 1
    assert first == second == third
    assert first["wpm"] == 22.0
    assert first["accuracy"] == 0.859375
    assert len(first["bigrams"]) == 19


def _simple_row(block_id: str, seq: int, t_down_ms: float, key: str, index: int) -> KeystrokeEvent:
    return KeystrokeEvent(
        block_id=block_id,
        seq=seq,
        key=key,
        code=f"Key{key.upper()}" if key != " " else "Space",
        t_down_ms=t_down_ms,
        target_index=index,
        expected_char=key,
        outcome="correct",
        first_attempt=True,
        handler_ms=0.0,
        dispatch_lag_ms=0.0,
    )


def test_two_block_session_pools_samples_and_sums_elapsed(migrated_engine: Engine) -> None:
    # Block 0 target "ab ab ab": three "ab" pairs with IKI 100, 200, 300; elapsed 1000.
    # Block 1 target "ab": one "ab" pair with IKI 1000; elapsed 1000.
    # Pooled "ab" samples [100,200,300,1000] -> median 250 (median of medians would be 600).
    # Correct first attempts: 8 + 2 = 10; elapsed 1000 + 1000 = 2000 ms -> wpm 60.
    with Session(migrated_engine) as session:
        participant = Participant(alias="two")
        session.add(participant)
        session.flush()
        ts = TypingSession(
            participant_id=participant.id,
            phase="baseline",
            day_index=1,
            client_info={},
            started_at=STARTED_AT,
        )
        session.add(ts)
        session.flush()
        b0 = SessionBlock(session_id=ts.id, block_index=0, arm="test", target_text="ab ab ab")
        b1 = SessionBlock(session_id=ts.id, block_index=1, arm="test", target_text="ab")
        session.add(b0)
        session.add(b1)
        session.flush()
        # Block 0 presses: a0=0 b1=100 sp2=200 a3=300 b4=500 sp5=600 a6=700 b7=1000
        session.add_all(
            [
                _simple_row(b0.id, 0, 0.0, "a", 0),
                _simple_row(b0.id, 1, 100.0, "b", 1),
                _simple_row(b0.id, 2, 200.0, " ", 2),
                _simple_row(b0.id, 3, 300.0, "a", 3),
                _simple_row(b0.id, 4, 500.0, "b", 4),
                _simple_row(b0.id, 5, 600.0, " ", 5),
                _simple_row(b0.id, 6, 700.0, "a", 6),
                _simple_row(b0.id, 7, 1000.0, "b", 7),
            ]
        )
        # Block 1 presses: a0=0 b1=1000 (gap 1000, still under 2000 ms, so it is a sample).
        session.add_all(
            [
                _simple_row(b1.id, 0, 0.0, "a", 0),
                _simple_row(b1.id, 1, 1000.0, "b", 1),
            ]
        )
        session.commit()
        stats = compute_session_stats(session, ts.id)
    assert stats.block_count == 2
    assert stats.wpm == 60.0
    assert stats.accuracy == 1.0
    ab = next(b for b in stats.bigrams if b.bigram == "ab")
    assert ab.attempts == 4
    assert ab.iki_n == 4
    assert ab.iki_median_ms == 250.0  # not 600.0 (median of medians)


def test_recompute_skips_non_completed_sessions(migrated_engine: Engine) -> None:
    golden = _golden()
    with Session(migrated_engine) as session:
        participant_id = _seed_participant(session)
        in_progress = _seed_golden_session(session, participant_id, golden)
        abandoned_id = _seed_golden_session(session, participant_id, golden)
        abandoned = session.get(TypingSession, abandoned_id)
        assert abandoned is not None
        abandoned.status = "abandoned"
        session.add(abandoned)
        session.commit()
        result = recompute_stats(session, participant_id)
    assert result.recomputed == 0
    assert result.skipped == 2
    with Session(migrated_engine) as session:
        for sid in (in_progress, abandoned_id):
            row = session.get(TypingSession, sid)
            assert row is not None
            assert row.wpm is None
            assert row.accuracy is None
            assert (
                session.exec(select(BigramStat).where(col(BigramStat.session_id) == sid)).all()
                == []
            )
