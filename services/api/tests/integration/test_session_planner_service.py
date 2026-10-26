"""Integration tests for session_planner: Latin square rotation across days, single-use drill pool
selection in creation order, FK flush order, atomic rollback on pool exhaustion, open/stale session
handling, baseline/retest planning, and pool replenishment (T2.6).
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from typist.models import (
    BigramAssignment,
    Drill,
    ExperimentConfig,
    GenerationJob,
    Participant,
    SessionBlock,
    TextPassage,
)
from typist.models import Session as TypingSession
from typist.services.participants import ParticipantNotFoundError, delete_participant
from typist.services.session_planner import (
    DrillPoolExhaustedError,
    InvalidSessionPhaseError,
    PassageNotFoundError,
    get_session_plan,
    plan_session,
    replenish_drill_pool,
)
from typist.services.session_stats import SessionNotFoundError, complete_session

T0 = datetime(2026, 10, 26, 10, 0, 0, tzinfo=UTC)


def _make_drill(
    participant_id: str,
    arm: str,
    index: int,
    *,
    created_at: datetime,
    drill_id: str | None = None,
    status: str = "ready",
) -> Drill:
    word = f"{arm[:3]}{chr(ord('a') + index)}"
    text = " ".join([word] * 60)[:299].rstrip()
    kwargs: dict[str, object] = {
        "participant_id": participant_id,
        "arm": arm,
        "target_bigrams": [] if arm == "control" else ["th", "he", "in", "er"],
        "text": text,
        "target_density": 0.0 if arm == "control" else 0.25,
        "mean_word_len": 4.0,
        "real_word_ratio": 1.0,
        "generator_version": f"{arm}:v1",
        "seed": 1000 + index,
        "status": status,
        "created_at": created_at,
    }
    if drill_id is not None:
        kwargs["id"] = drill_id
    return Drill(**kwargs)  # type: ignore[arg-type]


def _seed_practice_participant(
    session: Session,
    participant_id: str = "p-plan-01",
    *,
    drills_per_arm: int = 8,
    arms: tuple[str, ...] = ("control", "heuristic", "markov", "llm"),
) -> dict[str, list[str]]:
    """Create a practice participant and `drills_per_arm` ready drills per arm in creation order."""
    session.add(Participant(id=participant_id, alias=participant_id, status="practice"))
    session.flush()
    drill_ids_by_arm: dict[str, list[str]] = {arm: [] for arm in arms}
    for arm in arms:
        for i in range(drills_per_arm):
            # Pair drills with identical timestamps on even/odd indices to test (created_at, id) tie-breaking.
            created_at = T0 + timedelta(seconds=i // 2)
            drill_id = f"d-{arm}-{i:02d}"
            drill = _make_drill(
                participant_id,
                arm,
                i,
                created_at=created_at,
                drill_id=drill_id,
            )
            session.add(drill)
            drill_ids_by_arm[arm].append(drill_id)
    session.commit()
    return drill_ids_by_arm


def test_practice_sessions_rotate_block_order_daily_and_never_reuse_drills(
    migrated_engine: Engine,
) -> None:
    expected_orders = ["CHML", "HMLC", "MLCH", "LCHM"]
    expected_arm_sequences = [
        ("control", "heuristic", "markov", "llm"),
        ("heuristic", "markov", "llm", "control"),
        ("markov", "llm", "control", "heuristic"),
        ("llm", "control", "heuristic", "markov"),
    ]
    seen_drill_ids: set[str] = set()

    with Session(migrated_engine) as session:
        drill_ids_by_arm = _seed_practice_participant(session, drills_per_arm=8)

        for day in range(4):
            now = T0 + timedelta(days=day)
            planned = plan_session(
                session,
                "p-plan-01",
                client_info={"day": day + 1},
                now=now,
            )
            assert planned.phase == "practice"
            assert planned.day_index == day + 1
            assert planned.status == "in_progress"
            assert [b.label for b in planned.blocks] == [
                "Block 1",
                "Block 2",
                "Block 3",
                "Block 4",
            ]
            assert [b.block_index for b in planned.blocks] == [0, 1, 2, 3]

            db_session = session.get(TypingSession, planned.session_id)
            assert db_session is not None
            assert db_session.block_order == expected_orders[day]

            db_blocks = session.exec(
                select(SessionBlock)
                .where(col(SessionBlock.session_id) == planned.session_id)
                .order_by(col(SessionBlock.block_index))
            ).all()
            assert tuple(b.arm for b in db_blocks) == expected_arm_sequences[day]

            for block_idx, block in enumerate(db_blocks):
                arm = expected_arm_sequences[day][block_idx]
                expected_pair = drill_ids_by_arm[arm][day * 2 : day * 2 + 2]
                used_drills = session.exec(
                    select(Drill)
                    .where(col(Drill.used_in_block_id) == block.id)
                    .order_by(col(Drill.created_at).asc(), col(Drill.id).asc())
                ).all()
                used_ids = [d.id for d in used_drills]
                assert used_ids == expected_pair
                assert all(d.status == "used" for d in used_drills)
                assert seen_drill_ids.isdisjoint(used_ids)
                seen_drill_ids.update(used_ids)
                assert block.target_text == f"{used_drills[0].text} {used_drills[1].text}"
                assert "  " not in block.target_text

            complete_session(session, planned.session_id, now + timedelta(minutes=10))

        # After 4 practice days (8 drills per arm * 4 arms = 32 drills), all 32 drills are used once.
        assert len(seen_drill_ids) == 32
        remaining_ready = session.exec(
            select(Drill).where(
                col(Drill.participant_id) == "p-plan-01",
                col(Drill.status) == "ready",
            )
        ).all()
        assert remaining_ready == []


def test_plan_session_rolls_back_atomically_when_any_arm_pool_is_exhausted(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        session.add(Participant(id="p-exhaust", alias="p-exhaust", status="practice"))
        session.flush()
        # control has 2 ready drills, heuristic has only 1 ready drill (below 2).
        session.add(_make_drill("p-exhaust", "control", 0, created_at=T0, drill_id="d-c-0"))
        session.add(_make_drill("p-exhaust", "control", 1, created_at=T0, drill_id="d-c-1"))
        session.add(_make_drill("p-exhaust", "heuristic", 0, created_at=T0, drill_id="d-h-0"))
        session.commit()

        with pytest.raises(DrillPoolExhaustedError, match="heuristic"):
            plan_session(session, "p-exhaust", now=T0)

        # No Session or SessionBlock created, and control's drills remain status='ready'.
        assert (
            session.exec(
                select(TypingSession).where(col(TypingSession.participant_id) == "p-exhaust")
            ).all()
            == []
        )
        control_drills = session.exec(
            select(Drill).where(col(Drill.participant_id) == "p-exhaust")
        ).all()
        assert all(d.status == "ready" and d.used_in_block_id is None for d in control_drills)


def test_plan_session_returns_open_session_under_30_minutes_and_abandons_stale_session(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed_practice_participant(session, "p-stale", drills_per_arm=6)

        # Day 1 completed (rotation_index 0 -> 'CHML').
        s1 = plan_session(session, "p-stale", now=T0)
        complete_session(session, s1.session_id, T0 + timedelta(minutes=12))

        # Start session 2 at T0 + 1 day (rotation_index 1 -> 'HMLC', day_index 2).
        t_day2 = T0 + timedelta(days=1)
        s2 = plan_session(session, "p-stale", now=t_day2)
        assert s2.day_index == 2

        # Calling plan_session again 15 minutes later returns the SAME open session without consuming new drills.
        s2_again = plan_session(session, "p-stale", now=t_day2 + timedelta(minutes=15))
        assert s2_again.session_id == s2.session_id
        assert [b.block_id for b in s2_again.blocks] == [b.block_id for b in s2.blocks]
        ready_after_retry = session.exec(
            select(Drill).where(
                col(Drill.participant_id) == "p-stale",
                col(Drill.status) == "ready",
            )
        ).all()
        assert len(ready_after_retry) == 8  # 6 - 2 (s1) - 2 (s2) = 2 per arm * 4 arms = 8

        # Calling plan_session 31 minutes after s2 started marks s2 'abandoned' and creates s3:
        # s3 gets day_index == 3 (never reuses abandoned day_index 2; T1.1 answer 11),
        # and rotation_index is still 1 ('HMLC') because s2 was not completed (owner answer 1),
        # and s3 consumes fresh drills (never reusing s2's drills).
        s3 = plan_session(session, "p-stale", now=t_day2 + timedelta(minutes=31))
        assert s3.session_id != s2.session_id
        assert s3.day_index == 3
        db_s2 = session.get(TypingSession, s2.session_id)
        db_s3 = session.get(TypingSession, s3.session_id)
        assert db_s2 is not None and db_s2.status == "abandoned"
        assert db_s2.ended_at == t_day2 + timedelta(minutes=31)
        assert db_s3 is not None and db_s3.block_order == "HMLC"


def test_plan_session_supports_two_arm_cut_line_mode(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        arms_cfg = session.get(ExperimentConfig, "arms_enabled")
        assert arms_cfg is not None
        arms_cfg.value = ["control", "heuristic"]
        session.add(arms_cfg)
        session.commit()

        _seed_practice_participant(
            session, "p-cut", drills_per_arm=4, arms=("control", "heuristic")
        )
        day1 = plan_session(session, "p-cut", now=T0)
        assert len(day1.blocks) == 2
        assert [b.label for b in day1.blocks] == ["Block 1", "Block 2"]
        db_day1 = session.get(TypingSession, day1.session_id)
        assert db_day1 is not None and db_day1.block_order == "CH"
        complete_session(session, day1.session_id, T0 + timedelta(minutes=5))

        day2 = plan_session(session, "p-cut", now=T0 + timedelta(days=1))
        db_day2 = session.get(TypingSession, day2.session_id)
        assert db_day2 is not None and db_day2.block_order == "HC"


def test_plan_baseline_and_retest_sessions_select_one_part_per_sitting(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        session.add(Participant(id="p-test", alias="p-test", status="enrolled"))
        p_a0 = TextPassage(
            kind="baseline",
            form="A",
            part=0,
            participant_id=None,
            text="the quick brown fox",
            bigram_counts={"th": 1},
        )
        p_a1 = TextPassage(
            kind="baseline",
            form="A",
            part=1,
            participant_id=None,
            text="jumps over lazy dog",
            bigram_counts={"ov": 1},
        )
        p_b0 = TextPassage(
            kind="retest",
            form="B",
            part=0,
            participant_id="p-test",
            text="retest form b part zero",
            bigram_counts={"re": 1},
        )
        session.add_all([p_a0, p_a1, p_b0])
        session.commit()

        # Baseline sitting 1 -> part 0
        b1 = plan_session(session, "p-test", now=T0)
        assert b1.phase == "baseline"
        assert b1.day_index == 1
        assert len(b1.blocks) == 1
        assert b1.blocks[0].block_index == 0
        assert b1.blocks[0].label == "Block 1"
        assert b1.blocks[0].target_text == "the quick brown fox"
        db_b1 = session.get(TypingSession, b1.session_id)
        assert db_b1 is not None and db_b1.block_order is None
        complete_session(session, b1.session_id, T0 + timedelta(minutes=10))

        # Baseline sitting 2 -> part 1 (block_index == passage.part == 1, label == 'Block 1')
        b2 = plan_session(session, "p-test", now=T0 + timedelta(days=1))
        assert b2.phase == "baseline"
        assert b2.day_index == 2
        assert len(b2.blocks) == 1
        assert b2.blocks[0].block_index == 1
        assert b2.blocks[0].label == "Block 1"
        assert b2.blocks[0].target_text == "jumps over lazy dog"
        complete_session(session, b2.session_id, T0 + timedelta(days=1, minutes=10))

        # Baseline sitting 3 -> no part 2 exists -> PassageNotFoundError
        with pytest.raises(PassageNotFoundError, match="part 2"):
            plan_session(session, "p-test", now=T0 + timedelta(days=2))

        # Move participant to retest and plan retest sitting 1 -> form B part 0
        participant = session.get(Participant, "p-test")
        assert participant is not None
        participant.status = "retest"
        session.add(participant)
        session.commit()

        r1 = plan_session(session, "p-test", now=T0 + timedelta(days=12))
        assert r1.phase == "retest"
        assert r1.day_index == 1
        assert len(r1.blocks) == 1
        assert r1.blocks[0].block_index == 0
        assert r1.blocks[0].target_text == "retest form b part zero"


def test_replenish_drill_pool_enqueues_deficit_and_deduplicates_pending_jobs(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        with pytest.raises(ParticipantNotFoundError):
            replenish_drill_pool(session, "missing-pid")

        _seed_practice_participant(session, "p-pool", drills_per_arm=4)
        # Without frozen bigram_assignment rows, replenish_drill_pool returns [].
        assert replenish_drill_pool(session, "p-pool") == []

        # Seed frozen bigram_assignment rows (1 per arm is sufficient to mark participant assigned).
        for rank, (label, arm, bg) in enumerate(
            [
                ("A", "control", "th"),
                ("B", "heuristic", "he"),
                ("C", "markov", "in"),
                ("D", "llm", "er"),
            ],
            start=1,
        ):
            session.add(
                BigramAssignment(
                    participant_id="p-pool",
                    bigram=bg,
                    set_label=label,
                    arm=arm,
                    baseline_rank=rank,
                    weakness_score=0.2,
                    baseline_attempts=20,
                    baseline_errors=4,
                    frozen_at=T0,
                )
            )
        # Pre-enqueue a running job of requested=1 for heuristic so its effective count is 4 + 1 = 5 (deficit 1).
        session.add(
            GenerationJob(
                participant_id="p-pool",
                arm="heuristic",
                requested=1,
                status="running",
            )
        )
        session.commit()

        jobs = replenish_drill_pool(session, "p-pool")
        by_arm = {job.arm: job.requested for job in jobs}
        # Target is 6 ready drills per arm; each arm has 4 ready, heuristic also has 1 running.
        assert by_arm == {"control": 2, "heuristic": 1, "markov": 2, "llm": 2}

        # Calling replenish_drill_pool again immediately enqueues nothing because pending jobs cover the deficit.
        assert replenish_drill_pool(session, "p-pool") == []


def test_get_session_plan_and_delete_participant_with_used_drills(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _seed_practice_participant(session, "p-del", drills_per_arm=2)
        planned = plan_session(session, "p-del", now=T0)
        loaded = get_session_plan(session, planned.session_id)
        assert loaded == planned

        with pytest.raises(SessionNotFoundError):
            get_session_plan(session, "non-existent-session")

        with pytest.raises(InvalidSessionPhaseError):
            plan_session(session, "p-del", phase="baseline", now=T0)

        # Verify delete_participant still succeeds when drills.used_in_block_id references session_blocks.
        deletion = delete_participant(session, "p-del")
        assert deletion.drills == 8
        assert deletion.session_blocks == 4
        assert deletion.sessions == 1
