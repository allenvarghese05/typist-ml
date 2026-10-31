"""Unit tests for analysis session selection and clean IKI / pause extraction (T4.1)."""

from datetime import UTC, datetime

from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from typist.models import KeystrokeEvent, SessionBlock
from typist.models import Session as TypingSession
from typist.services.analysis import extract_clean_iki_and_pauses, select_phase_sessions


def test_select_phase_sessions_superseded_and_abandoned() -> None:
    """Verify selection of 2 most recent completed sessions; mark older as superseded, unfinished as abandoned."""
    now = datetime.now(UTC)
    s_abandoned = TypingSession(
        id="s-abandoned",
        participant_id="p-1",
        phase="baseline",
        day_index=1,
        started_at=datetime(2026, 10, 1, 10, 0, tzinfo=UTC),
        status="abandoned",
    )
    s_comp1 = TypingSession(
        id="s-comp1",
        participant_id="p-1",
        phase="baseline",
        day_index=1,
        started_at=datetime(2026, 10, 1, 11, 0, tzinfo=UTC),
        status="completed",
    )
    s_comp2 = TypingSession(
        id="s-comp2",
        participant_id="p-1",
        phase="baseline",
        day_index=2,
        started_at=datetime(2026, 10, 2, 10, 0, tzinfo=UTC),
        status="completed",
    )
    s_comp3 = TypingSession(
        id="s-comp3",
        participant_id="p-1",
        phase="baseline",
        day_index=3,
        started_at=datetime(2026, 10, 3, 10, 0, tzinfo=UTC),
        status="completed",
    )
    s_other_phase = TypingSession(
        id="s-other",
        participant_id="p-1",
        phase="retest",
        day_index=4,
        started_at=datetime(2026, 10, 4, 10, 0, tzinfo=UTC),
        status="completed",
    )

    all_sessions = [s_comp2, s_abandoned, s_comp1, s_other_phase, s_comp3]
    sel = select_phase_sessions(all_sessions, "baseline")

    assert [s.id for s in sel.analyzed_sessions] == ["s-comp2", "s_comp3".replace("_", "-")]
    reasons = {ex.session_id: ex.reason for ex in sel.excluded_sessions}
    assert reasons == {"s-abandoned": "abandoned", "s-comp1": "superseded"}


def test_extract_clean_iki_and_pauses() -> None:
    """Verify clean IKI and pause extraction across completed blocks with pause flags, gaps, and incomplete blocks."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        now = datetime.now(UTC)
        # Block 1: completed block with "the test"
        block1 = SessionBlock(
            id="blk-1",
            session_id="sess-1",
            block_index=0,
            arm="control",
            target_text="the cat",
            started_at=now,
            ended_at=now,
        )
        # Block 2: incomplete block (ended_at is None)
        block2 = SessionBlock(
            id="blk-2",
            session_id="sess-1",
            block_index=1,
            arm="control",
            target_text="the dog",
            started_at=now,
            ended_at=None,
        )
        session.add_all([block1, block2])
        session.commit()

        # Keystrokes for block 1:
        # 't' at 0 (seq 1, correct, first_attempt=True, t_down=1000)
        # 'h' at 1 (seq 2, correct, first_attempt=True, t_down=1150) -> gap 150ms for 'th'
        # 'e' at 2 (seq 3, correct, first_attempt=True, t_down=1300) -> gap 150ms for 'he'
        # ' ' at 3 (seq 4)
        # 'c' at 4 (seq 5, correct, first_attempt=True, t_down=1500)
        # 'a' at 5 (seq 6, correct, first_attempt=True, t_down=4000) -> gap 2500ms > 2000ms for 'ca' (pause)
        # 't' at 6 (seq 7, correct, first_attempt=True, t_down=4150, after_pause=True) -> after_pause for 'at' (pause)
        k_b1 = [
            KeystrokeEvent(
                block_id="blk-1",
                seq=1,
                target_index=0,
                key="t",
                code="KeyT",
                t_down_ms=1000.0,
                first_attempt=True,
                outcome="correct",
                handler_ms=0.5,
                dispatch_lag_ms=0.1,
            ),
            KeystrokeEvent(
                block_id="blk-1",
                seq=2,
                target_index=1,
                key="h",
                code="KeyH",
                t_down_ms=1150.0,
                first_attempt=True,
                outcome="correct",
                handler_ms=0.5,
                dispatch_lag_ms=0.1,
            ),
            KeystrokeEvent(
                block_id="blk-1",
                seq=3,
                target_index=2,
                key="e",
                code="KeyE",
                t_down_ms=1300.0,
                first_attempt=True,
                outcome="correct",
                handler_ms=0.5,
                dispatch_lag_ms=0.1,
            ),
            KeystrokeEvent(
                block_id="blk-1",
                seq=4,
                target_index=3,
                key=" ",
                code="Space",
                t_down_ms=1380.0,
                first_attempt=True,
                outcome="correct",
                handler_ms=0.5,
                dispatch_lag_ms=0.1,
            ),
            KeystrokeEvent(
                block_id="blk-1",
                seq=5,
                target_index=4,
                key="c",
                code="KeyC",
                t_down_ms=1500.0,
                first_attempt=True,
                outcome="correct",
                handler_ms=0.5,
                dispatch_lag_ms=0.1,
            ),
            KeystrokeEvent(
                block_id="blk-1",
                seq=6,
                target_index=5,
                key="a",
                code="KeyA",
                t_down_ms=4000.0,
                first_attempt=True,
                outcome="correct",
                after_pause=False,
                handler_ms=0.5,
                dispatch_lag_ms=0.1,
            ),
            KeystrokeEvent(
                block_id="blk-1",
                seq=7,
                target_index=6,
                key="t",
                code="KeyT",
                t_down_ms=4150.0,
                first_attempt=True,
                outcome="correct",
                after_pause=True,
                handler_ms=0.5,
                dispatch_lag_ms=0.1,
            ),
        ]

        # Keystrokes for block 2 (incomplete, must be ignored)
        k_b2 = [
            KeystrokeEvent(
                block_id="blk-2",
                seq=1,
                target_index=0,
                key="t",
                code="KeyT",
                t_down_ms=5000.0,
                first_attempt=True,
                outcome="correct",
                handler_ms=0.5,
                dispatch_lag_ms=0.1,
            ),
            KeystrokeEvent(
                block_id="blk-2",
                seq=2,
                target_index=1,
                key="h",
                code="KeyH",
                t_down_ms=5100.0,
                first_attempt=True,
                outcome="correct",
                handler_ms=0.5,
                dispatch_lag_ms=0.1,
            ),
        ]

        session.add_all(k_b1 + k_b2)
        session.commit()

        samples, pauses = extract_clean_iki_and_pauses(
            session, ["sess-1"], {"th", "he", "ca", "at"}
        )

        assert samples["th"] == [150.0]
        assert pauses["th"] == 0
        assert samples["he"] == [150.0]
        assert pauses["he"] == 0

        # 'ca' gap was 2500ms > 2000ms -> recorded as pause, not in samples
        assert samples["ca"] == []
        assert pauses["ca"] == 1

        # 'at' after_pause=True -> recorded as pause, not in samples
        assert samples["at"] == []
        assert pauses["at"] == 1
