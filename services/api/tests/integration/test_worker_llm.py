"""Integration tests for worker LLM generator wiring and attempt metrics logging (T3.2)."""

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from typist.corpus.build import build_corpus
from typist.corpus.word_index import WordIndex
from typist.generation.base import Arm
from typist.generation.llm import FakeLLMRuntime, LLMOutput
from typist.generation.service import GenerationService
from typist.models import BigramAssignment, Drill, GenerationAttempt, GenerationJob, Participant
from typist.worker import build_default_generators

PID = "p-llm-01"


def _setup_participant_and_assignments(session: Session, words: list[str]) -> None:
    session.add(Participant(id=PID, alias=PID))
    session.flush()
    targets = ("th", "ea", "in", "st")
    for idx, bg in enumerate(targets):
        session.add(
            BigramAssignment(
                participant_id=PID,
                bigram=bg,
                set_label="A",
                arm="llm",
                baseline_rank=idx + 1,
                weakness_score=0.2,
                baseline_attempts=20,
                baseline_errors=4,
            )
        )
    session.commit()


def test_build_default_generators_registers_llm_with_injected_runtime(
    migrated_engine: Engine, tmp_path_factory
) -> None:
    corpus_dir = tmp_path_factory.mktemp("corpus_worker_llm")
    build_corpus(corpus_dir, word_count=20000, tracked_count=150)
    index = WordIndex.load(corpus_dir)
    fake_runtime = FakeLLMRuntime(canned_text="test")

    with Session(migrated_engine) as session:
        generators, _config = build_default_generators(session, index, runtime=fake_runtime)
        assert Arm.LLM in generators
        assert generators[Arm.LLM].arm is Arm.LLM
        assert generators[Arm.LLM].version == "llm-v1"


def test_generation_service_logs_attempts_with_tokens_per_sec_and_metrics(
    migrated_engine: Engine, tmp_path_factory
) -> None:
    corpus_dir = tmp_path_factory.mktemp("corpus_service_llm")
    build_corpus(corpus_dir, word_count=20000, tracked_count=150)
    index = WordIndex.load(corpus_dir)

    # Valid text matching coverage, length (between 270 and 300) and density
    valid_text = (
        "the weather in east is great this morning everyone staying there their seats "
        "eating steak instead thinking about next step early spring season with fresh "
        "air blowing past station where trains start each day clean water path stone "
        "stream reach into deep earth under warm sunlight"
    )
    assert 270 <= len(valid_text) <= 300

    out1 = LLMOutput(
        text="too short",
        tokens=2,
        tokens_per_sec=35.0,
        peak_memory_mb=825.0,
        gen_ms=15.0,
    )
    out2 = LLMOutput(
        text=valid_text,
        tokens=45,
        tokens_per_sec=48.5,
        peak_memory_mb=840.0,
        gen_ms=55.0,
    )
    fake_runtime = FakeLLMRuntime(canned_outputs=[out1, out2])

    with Session(migrated_engine) as session:
        _setup_participant_and_assignments(session, index.words)
        generators, validator_config = build_default_generators(
            session, index, runtime=fake_runtime
        )
        service = GenerationService(
            session,
            generators,
            known_words=index.words,
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
        assert len(drills) == 1
        drill = drills[0]
        assert drill.arm == "llm"
        assert drill.model_id == "mlx-community/Llama-3.2-1B-Instruct-4bit"
        assert drill.prompt_version == "v1"
        assert drill.generator_version == "llm-v1"

        # Verify generation_attempts rows
        attempts = session.exec(
            select(GenerationAttempt)
            .where(col(GenerationAttempt.job_id) == job.id)
            .order_by(col(GenerationAttempt.id))
        ).all()
        assert len(attempts) == 2

        # First attempt rejected (too short)
        assert attempts[0].accepted is False
        assert "too_short" in attempts[0].reject_reasons
        assert attempts[0].gen_tokens == 2
        assert attempts[0].tokens_per_sec == 35.0
        assert attempts[0].peak_memory_mb == 825.0
        assert attempts[0].gen_ms == 15.0

        # Second attempt accepted
        assert attempts[1].accepted is True
        assert attempts[1].drill_id == drill.id
        assert attempts[1].gen_tokens == 45
        assert attempts[1].tokens_per_sec == 48.5
        assert attempts[1].peak_memory_mb == 840.0
        assert attempts[1].gen_ms == 55.0
