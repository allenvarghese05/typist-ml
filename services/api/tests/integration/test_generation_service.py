"""Integration tests for GenerationService, atomic job claiming, and attempt logging (T2.5)."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import pytest
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from typist.corpus.build import build_corpus
from typist.corpus.word_index import WordIndex
from typist.generation.base import Arm, DrillCandidate, DrillGenerator, DrillSpec
from typist.generation.control import ControlGenerator
from typist.generation.heuristic import HeuristicGenerator
from typist.generation.service import (
    DrillGenerationExhaustedError,
    GenerationService,
    claim_next_job,
)
from typist.generation.validator import (
    RejectReason,
    load_validator_config,
)
from typist.models import (
    BigramAssignment,
    Drill,
    GenerationAttempt,
    GenerationJob,
    Participant,
)
from typist.worker import (
    build_default_generators,
    read_heartbeat_age_s,
    run_worker,
    run_worker_once,
)

PID: Final = "p-gen-01"


@pytest.fixture(scope="module")
def corpus_index(tmp_path_factory: pytest.TempPathFactory) -> WordIndex:
    corpus_dir = tmp_path_factory.mktemp("corpus_gen")
    build_corpus(corpus_dir, word_count=20000, tracked_count=150)
    return WordIndex.load(corpus_dir)


def _setup_participant(session: Session, participant_id: str = PID) -> None:
    session.add(Participant(id=participant_id, alias=participant_id))
    session.commit()


class _AlwaysFailsGenerator:
    arm = Arm.CONTROL
    version = "always-fail-v1"

    def generate(self, spec: DrillSpec) -> DrillCandidate:
        return DrillCandidate(
            text="short",
            raw_output="short",
            generator_version=self.version,
            seed=spec.seed,
        )


class _ScriptedFailThenPassGenerator:
    arm = Arm.CONTROL
    version = "scripted-v1"

    def __init__(self, fail_count: int, fallback: DrillGenerator) -> None:
        self._fails_remaining = fail_count
        self._fallback = fallback

    def generate(self, spec: DrillSpec) -> DrillCandidate:
        if self._fails_remaining > 0:
            self._fails_remaining -= 1
            return DrillCandidate(
                text="short",
                raw_output="short",
                generator_version=self.version,
                seed=spec.seed,
            )
        return self._fallback.generate(spec)


class _CrashingGenerator:
    arm = Arm.CONTROL
    version = "crashing-v1"

    def generate(self, spec: DrillSpec) -> DrillCandidate:
        raise RuntimeError("boom")


def test_claim_next_job_claims_oldest_pending_and_ignores_others(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _setup_participant(session)
        job_old = GenerationJob(
            participant_id=PID,
            arm="control",
            requested=1,
            status="pending",
            created_at=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
        )
        job_new = GenerationJob(
            participant_id=PID,
            arm="control",
            requested=1,
            status="pending",
            created_at=datetime(2026, 1, 1, 11, 0, 0, tzinfo=UTC),
        )
        job_running = GenerationJob(
            participant_id=PID,
            arm="control",
            requested=1,
            status="running",
            created_at=datetime(2026, 1, 1, 9, 0, 0, tzinfo=UTC),
        )
        job_done = GenerationJob(
            participant_id=PID,
            arm="control",
            requested=1,
            status="done",
            created_at=datetime(2026, 1, 1, 8, 0, 0, tzinfo=UTC),
        )
        session.add_all([job_old, job_new, job_running, job_done])
        session.commit()

        claimed1 = claim_next_job(session)
        assert claimed1 is not None
        assert claimed1.id == job_old.id
        assert claimed1.status == "running"
        assert claimed1.started_at is not None

        claimed2 = claim_next_job(session)
        assert claimed2 is not None
        assert claimed2.id == job_new.id
        assert claimed2.status == "running"
        assert claimed2.started_at is not None

        claimed3 = claim_next_job(session)
        assert claimed3 is None


def test_claim_next_job_is_atomic_under_concurrent_callers(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        _setup_participant(session)
        job = GenerationJob(
            participant_id=PID,
            arm="control",
            requested=1,
            status="pending",
        )
        session.add(job)
        session.commit()
        job_id = job.id

    def _try_claim() -> str | None:
        with Session(migrated_engine) as session:
            claimed = claim_next_job(session)
            return claimed.id if claimed is not None else None

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_try_claim) for _ in range(4)]
        results = [f.result() for f in futures]

    claimed_ids = [res for res in results if res is not None]
    assert len(claimed_ids) == 1
    assert claimed_ids[0] == job_id


def test_generate_with_retries_logs_rejected_attempts_then_accepts_and_links_drill_id(
    migrated_engine: Engine, corpus_index: WordIndex
) -> None:
    with Session(migrated_engine) as session:
        _setup_participant(session)
        validator_config = load_validator_config(session)
        real_control = ControlGenerator(corpus_index, validator_config, 5000)
        scripted_gen = _ScriptedFailThenPassGenerator(2, real_control)
        service = GenerationService(
            session,
            {Arm.CONTROL: scripted_gen},
            known_words=corpus_index.words,
            validator_config=validator_config,
        )

        job = GenerationJob(
            participant_id=PID,
            arm="control",
            requested=1,
            status="running",
        )
        session.add(job)
        session.commit()
        session.refresh(job)

        spec = DrillSpec(
            participant_id=PID,
            arm=Arm.CONTROL,
            target_bigrams=(),
            seed=0,
        )
        drill = service.generate_with_retries(spec, job_id=job.id, assignment_seed=123)
        assert drill.status == "ready"

        attempts = session.exec(
            select(GenerationAttempt)
            .where(col(GenerationAttempt.job_id) == job.id)
            .order_by(col(GenerationAttempt.id))
        ).all()
        assert len(attempts) == 3

        # First two rejected
        assert not attempts[0].accepted
        assert attempts[0].reject_reasons == [RejectReason.TOO_SHORT.value]
        assert attempts[0].drill_id is None

        assert not attempts[1].accepted
        assert attempts[1].reject_reasons == [RejectReason.TOO_SHORT.value]
        assert attempts[1].drill_id is None

        # Third accepted
        assert attempts[2].accepted
        assert attempts[2].reject_reasons == []
        assert attempts[2].drill_id == drill.id

        drills = session.exec(select(Drill).where(col(Drill.participant_id) == PID)).all()
        assert len(drills) == 1
        assert drills[0].id == drill.id
        assert drills[0].status == "ready"


def test_generate_with_retries_raises_when_all_attempts_exhausted(
    migrated_engine: Engine, corpus_index: WordIndex
) -> None:
    with Session(migrated_engine) as session:
        _setup_participant(session)
        validator_config = load_validator_config(session)
        service = GenerationService(
            session,
            {Arm.CONTROL: _AlwaysFailsGenerator()},
            known_words=corpus_index.words,
            validator_config=validator_config,
        )

        job = GenerationJob(
            participant_id=PID,
            arm="control",
            requested=1,
            status="running",
        )
        session.add(job)
        session.commit()
        session.refresh(job)

        spec = DrillSpec(
            participant_id=PID,
            arm=Arm.CONTROL,
            target_bigrams=(),
            seed=0,
        )
        with pytest.raises(DrillGenerationExhaustedError):
            service.generate_with_retries(spec, job_id=job.id, assignment_seed=123)

        attempts = session.exec(
            select(GenerationAttempt).where(col(GenerationAttempt.job_id) == job.id)
        ).all()
        assert len(attempts) == 5
        assert all(not a.accepted for a in attempts)
        assert all(a.drill_id is None for a in attempts)

        drills = session.exec(select(Drill).where(col(Drill.participant_id) == PID)).all()
        assert len(drills) == 0


def test_run_job_control_ignores_control_bigram_assignment_rows(
    migrated_engine: Engine, corpus_index: WordIndex
) -> None:
    with Session(migrated_engine) as session:
        _setup_participant(session)
        validator_config = load_validator_config(session)
        # Add 4 bigram_assignment rows for control
        for rank, bg in enumerate(("th", "he", "in", "an"), start=1):
            session.add(
                BigramAssignment(
                    participant_id=PID,
                    bigram=bg,
                    set_label="A",
                    arm="control",
                    baseline_rank=rank,
                    weakness_score=0.5,
                    baseline_attempts=10,
                    baseline_errors=2,
                )
            )
        job = GenerationJob(
            participant_id=PID,
            arm="control",
            requested=2,
            status="pending",
        )
        session.add(job)
        session.commit()
        session.refresh(job)

        control_gen = ControlGenerator(corpus_index, validator_config, 5000)
        service = GenerationService(
            session,
            {Arm.CONTROL: control_gen},
            known_words=corpus_index.words,
            validator_config=validator_config,
        )
        drills = service.run_job(job.id)
        assert len(drills) == 2
        for drill in drills:
            assert drill.target_bigrams == []
            assert drill.target_density == 0.0
            assert drill.status == "ready"
        assert drills[0].seed != drills[1].seed

        session.refresh(job)
        assert job.status == "done"
        assert job.error is None
        assert job.finished_at is not None


def test_run_job_heuristic_loads_frozen_target_bigrams_and_marks_job_done(
    migrated_engine: Engine, corpus_index: WordIndex
) -> None:
    with Session(migrated_engine) as session:
        _setup_participant(session)
        validator_config = load_validator_config(session)
        for rank, bg in enumerate(("th", "he", "in", "an"), start=1):
            session.add(
                BigramAssignment(
                    participant_id=PID,
                    bigram=bg,
                    set_label="A",
                    arm="heuristic",
                    baseline_rank=rank,
                    weakness_score=0.5,
                    baseline_attempts=10,
                    baseline_errors=2,
                )
            )
        job = GenerationJob(
            participant_id=PID,
            arm="heuristic",
            requested=2,
            status="pending",
        )
        session.add(job)
        session.commit()
        session.refresh(job)

        heuristic_gen = HeuristicGenerator(corpus_index, validator_config, 5000)
        service = GenerationService(
            session,
            {Arm.HEURISTIC: heuristic_gen},
            known_words=corpus_index.words,
            validator_config=validator_config,
        )
        drills = service.run_job(job.id)
        assert len(drills) == 2
        for drill in drills:
            assert drill.target_bigrams == ["th", "he", "in", "an"]
            assert 0.15 <= drill.target_density <= 0.40
            assert drill.status == "ready"

        session.refresh(job)
        assert job.status == "done"
        assert job.error is None
        assert job.finished_at is not None


def test_run_job_successive_jobs_use_increasing_drill_numbers_and_distinct_seeds(
    migrated_engine: Engine, corpus_index: WordIndex
) -> None:
    with Session(migrated_engine) as session:
        _setup_participant(session)
        validator_config = load_validator_config(session)
        control_gen = ControlGenerator(corpus_index, validator_config, 5000)
        service = GenerationService(
            session,
            {Arm.CONTROL: control_gen},
            known_words=corpus_index.words,
            validator_config=validator_config,
        )

        job1 = GenerationJob(
            participant_id=PID,
            arm="control",
            requested=1,
            status="pending",
        )
        session.add(job1)
        session.commit()
        session.refresh(job1)

        drills1 = service.run_job(job1.id)
        assert len(drills1) == 1

        job2 = GenerationJob(
            participant_id=PID,
            arm="control",
            requested=1,
            status="pending",
        )
        session.add(job2)
        session.commit()
        session.refresh(job2)

        drills2 = service.run_job(job2.id)
        assert len(drills2) == 1

        assert drills1[0].seed != drills2[0].seed
        assert drills1[0].text != drills2[0].text


def test_run_job_partial_progress_and_retry_recovery(
    migrated_engine: Engine, corpus_index: WordIndex
) -> None:
    with Session(migrated_engine) as session:
        _setup_participant(session)
        validator_config = load_validator_config(session)
        real_control = ControlGenerator(corpus_index, validator_config, 5000)

        # Generator that succeeds on drill 0 (attempt 0), then fails on drill 1 (all attempts)
        # Create a customized generator for partial progress
        class _PartialFailGenerator:
            arm = Arm.CONTROL
            version = "partial-v1"

            def __init__(self) -> None:
                self.calls = 0

            def generate(self, spec: DrillSpec) -> DrillCandidate:
                self.calls += 1
                if self.calls == 1:
                    return real_control.generate(spec)
                return DrillCandidate(
                    text="short",
                    raw_output="short",
                    generator_version=self.version,
                    seed=spec.seed,
                )

        service = GenerationService(
            session,
            {Arm.CONTROL: _PartialFailGenerator()},
            known_words=corpus_index.words,
            validator_config=validator_config,
        )

        job = GenerationJob(
            participant_id=PID,
            arm="control",
            requested=2,
            status="pending",
        )
        session.add(job)
        session.commit()
        session.refresh(job)

        drills = service.run_job(job.id)
        assert len(drills) == 1

        session.refresh(job)
        assert job.status == "failed"
        assert job.retries == 1
        assert job.error is not None
        assert job.finished_at is not None

        # Verify 1 drill and 6 attempts (1 accepted + 5 rejected)
        drills_in_db = session.exec(select(Drill).where(col(Drill.participant_id) == PID)).all()
        assert len(drills_in_db) == 1

        attempts_in_db = session.exec(
            select(GenerationAttempt).where(col(GenerationAttempt.job_id) == job.id)
        ).all()
        assert len(attempts_in_db) == 6
        assert sum(1 for a in attempts_in_db if a.accepted) == 1
        assert sum(1 for a in attempts_in_db if not a.accepted) == 5

        # Re-queue the job and run with working generator
        job.status = "pending"
        session.add(job)
        session.commit()

        service_fixed = GenerationService(
            session,
            {Arm.CONTROL: real_control},
            known_words=corpus_index.words,
            validator_config=validator_config,
        )
        recovered_drills = service_fixed.run_job(job.id)
        assert len(recovered_drills) == 1

        session.refresh(job)
        assert job.status == "done"
        assert job.error is None

        drills_total = session.exec(select(Drill).where(col(Drill.participant_id) == PID)).all()
        assert len(drills_total) == 2


def test_run_job_fails_cleanly_when_targeted_arm_has_no_assignment(
    migrated_engine: Engine, corpus_index: WordIndex
) -> None:
    with Session(migrated_engine) as session:
        _setup_participant(session)
        validator_config = load_validator_config(session)
        heuristic_gen = HeuristicGenerator(corpus_index, validator_config, 5000)
        service = GenerationService(
            session,
            {Arm.HEURISTIC: heuristic_gen},
            known_words=corpus_index.words,
            validator_config=validator_config,
        )

        job = GenerationJob(
            participant_id=PID,
            arm="heuristic",
            requested=1,
            status="pending",
        )
        session.add(job)
        session.commit()
        session.refresh(job)

        drills = service.run_job(job.id)
        assert drills == []

        session.refresh(job)
        assert job.status == "failed"
        assert job.retries == 1
        assert job.error is not None
        assert "no bigram_assignment rows" in job.error


def test_run_job_fails_cleanly_when_arm_generator_is_unregistered(
    migrated_engine: Engine, corpus_index: WordIndex
) -> None:
    with Session(migrated_engine) as session:
        _setup_participant(session)
        validator_config = load_validator_config(session)
        control_gen = ControlGenerator(corpus_index, validator_config, 5000)
        service = GenerationService(
            session,
            {Arm.CONTROL: control_gen},
            known_words=corpus_index.words,
            validator_config=validator_config,
        )

        job = GenerationJob(
            participant_id=PID,
            arm="llm",
            requested=1,
            status="pending",
        )
        session.add(job)
        session.commit()
        session.refresh(job)

        drills = service.run_job(job.id)
        assert drills == []

        session.refresh(job)
        assert job.status == "failed"
        assert job.retries == 1
        assert job.error is not None
        assert "no generator registered" in job.error


def test_run_job_fails_cleanly_when_generator_raises_unexpected_exception(
    migrated_engine: Engine, corpus_index: WordIndex
) -> None:
    with Session(migrated_engine) as session:
        _setup_participant(session)
        validator_config = load_validator_config(session)
        service = GenerationService(
            session,
            {Arm.CONTROL: _CrashingGenerator()},
            known_words=corpus_index.words,
            validator_config=validator_config,
        )

        job = GenerationJob(
            participant_id=PID,
            arm="control",
            requested=1,
            status="pending",
        )
        session.add(job)
        session.commit()
        session.refresh(job)

        drills = service.run_job(job.id)
        assert drills == []

        session.refresh(job)
        assert job.status == "failed"
        assert job.retries == 1
        assert job.error == "boom"


def test_run_worker_once_processes_one_job_and_writes_heartbeat(
    migrated_engine: Engine, isolated_settings: Path, corpus_index: WordIndex
) -> None:
    with Session(migrated_engine) as session:
        _setup_participant(session)
        job = GenerationJob(
            participant_id=PID,
            arm="control",
            requested=1,
            status="pending",
        )
        session.add(job)
        session.commit()
        job_id = job.id

    claimed = run_worker_once(migrated_engine, isolated_settings, corpus_index)
    assert claimed == job_id

    with Session(migrated_engine) as session:
        refreshed_job = session.get(GenerationJob, job_id)
        assert refreshed_job is not None
        assert refreshed_job.status == "done"

        drills = session.exec(select(Drill).where(col(Drill.participant_id) == PID)).all()
        assert len(drills) == 1
        assert drills[0].status == "ready"

    age = read_heartbeat_age_s(isolated_settings)
    assert age is not None
    assert age >= 0.0


def test_run_worker_drains_queue_and_stops_on_event(
    migrated_engine: Engine, isolated_settings: Path, corpus_index: WordIndex
) -> None:
    with Session(migrated_engine) as session:
        _setup_participant(session)
        job1 = GenerationJob(
            participant_id=PID,
            arm="control",
            requested=1,
            status="pending",
        )
        job2 = GenerationJob(
            participant_id=PID,
            arm="control",
            requested=1,
            status="pending",
        )
        session.add_all([job1, job2])
        session.commit()
        job1_id = job1.id
        job2_id = job2.id
        validator_config = load_validator_config(session)

    stop_event = threading.Event()
    real_control = ControlGenerator(corpus_index, validator_config, 5000)

    class _StoppingGenerator:
        arm = Arm.CONTROL
        version = "stopping-v1"

        def __init__(self) -> None:
            self.count = 0

        def generate(self, spec: DrillSpec) -> DrillCandidate:
            self.count += 1
            if self.count >= 2:
                stop_event.set()
            return real_control.generate(spec)

    processed = run_worker(
        migrated_engine,
        isolated_settings,
        corpus_index,
        poll_interval_s=0.01,
        stop_event=stop_event,
        generators={Arm.CONTROL: _StoppingGenerator()},
    )
    assert processed == 2

    with Session(migrated_engine) as session:
        j1 = session.get(GenerationJob, job1_id)
        j2 = session.get(GenerationJob, job2_id)
        assert j1 is not None and j1.status == "done"
        assert j2 is not None and j2.status == "done"


def test_build_default_generators_includes_markov(
    migrated_engine: Engine, corpus_index: WordIndex
) -> None:
    with Session(migrated_engine) as session:
        generators, config = build_default_generators(session, corpus_index)
        assert Arm.MARKOV in generators
        assert generators[Arm.MARKOV].arm is Arm.MARKOV
        assert generators[Arm.MARKOV].version == "markov-v1"


def test_run_worker_once_processes_markov_job(
    migrated_engine: Engine, isolated_settings: Path, corpus_index: WordIndex
) -> None:
    with Session(migrated_engine) as session:
        _setup_participant(session)
        # Seed bigram assignments for PID and MARKOV
        for idx, bg in enumerate(corpus_index.tracked_bigrams[:4]):
            session.add(
                BigramAssignment(
                    participant_id=PID,
                    arm="markov",
                    set_label="A",
                    bigram=bg,
                    baseline_rank=idx + 1,
                    baseline_attempts=20,
                    baseline_errors=4,
                    smoothed_error_rate=0.2,
                    frozen_at=datetime.now(UTC),
                )
            )
        job = GenerationJob(
            participant_id=PID,
            arm="markov",
            requested=1,
            status="pending",
        )
        session.add(job)
        session.commit()
        job_id = job.id

    claimed = run_worker_once(migrated_engine, isolated_settings, corpus_index)
    assert claimed == job_id

    with Session(migrated_engine) as session:
        refreshed_job = session.get(GenerationJob, job_id)
        assert refreshed_job is not None
        assert refreshed_job.status == "done"

        drills = session.exec(
            select(Drill).where(col(Drill.participant_id) == PID, col(Drill.arm) == "markov")
        ).all()
        assert len(drills) == 1
        assert drills[0].status == "ready"
        assert drills[0].generator_version == "markov-v1"
