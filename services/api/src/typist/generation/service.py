"""GenerationService and atomic job claiming (design doc 6.2, 9.1, 10.2, 13.5; T2.5).

GenerationService is the only class that talks to SQLite during drill generation (9.1). Pure
generators (control, heuristic, markov, llm) turn a DrillSpec into a DrillCandidate without touching
the database; GenerationService loads the frozen bigram_assignment rows and experiment_config keys,
derives deterministic per-attempt seeds, runs the shared validate() gate up to max_attempts (5)
times per drill, logs every candidate in generation_attempts, and inserts accepted drills with
status='ready'. On an accepted attempt, the Drill row is flushed before inserting the
GenerationAttempt row so fk_generation_attempts_drill_id_drills is satisfied (brief edge case 1).
No mlx-lm import here, so this module runs on Linux CI (CLAUDE.md; D09).
"""

import hashlib
import logging
from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Final

import sqlalchemy as sa
from sqlmodel import Session, col, select

from typist.db import utc_now
from typist.generation.base import Arm, DrillCandidate, DrillGenerator, DrillSpec
from typist.generation.validator import (
    MissingConfigError,
    ValidatorConfig,
    load_validator_config,
    validate,
)
from typist.models import (
    BigramAssignment,
    Drill,
    ExperimentConfig,
    GenerationAttempt,
    GenerationJob,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS: Final[int] = 5

_SERVICE_CONFIG_KEYS: Final[tuple[str, ...]] = (
    "drill_length_chars",
    "d_min",
    "d_max",
    "assignment_seed",
)


class GenerationError(RuntimeError):
    """Base error for drill generation orchestration failures."""


class JobNotFoundError(GenerationError):
    """The requested generation_jobs.id does not exist."""


class UnregisteredArmError(GenerationError):
    """No DrillGenerator is registered for the job's arm."""


class MissingAssignmentError(GenerationError):
    """A targeted arm job has no frozen bigram_assignment rows for (participant_id, arm)."""


class DrillGenerationExhaustedError(GenerationError):
    """All max_attempts candidate generations for a single drill were rejected by the validator."""


@dataclass(frozen=True)
class _ServiceConfig:
    """experiment_config parameters needed to build a DrillSpec and derive seeds."""

    length_chars: int
    min_density: float
    max_density: float
    assignment_seed: int


def _load_service_config(session: Session) -> _ServiceConfig:
    """Read drill_length_chars, d_min, d_max, and assignment_seed from experiment_config."""
    values: dict[str, object] = {}
    for key in _SERVICE_CONFIG_KEYS:
        row = session.get(ExperimentConfig, key)
        if row is None:
            raise MissingConfigError(key)
        values[key] = row.value
    return _ServiceConfig(
        length_chars=int(str(values["drill_length_chars"])),
        min_density=float(str(values["d_min"])),
        max_density=float(str(values["d_max"])),
        assignment_seed=int(str(values["assignment_seed"])),
    )


def derive_drill_seed(
    assignment_seed: int,
    participant_id: str,
    arm: Arm,
    drill_number: int,
    attempt: int,
    job_retries: int = 0,
) -> int:
    """Return a deterministic non-negative 31-bit integer seed for one generation attempt (13.5).

    Hashes f"{assignment_seed}:{participant_id}:{arm.value}:{drill_number}:{job_retries}:{attempt}"
    with SHA-256 and masks the top 8 bytes to 0x7FFF_FFFF (fits signed 32-bit / SQLite INTEGER and
    JS safe integers, and never uses Python's randomized hash(); owner answer 3).
    """
    payload = (
        f"{assignment_seed}:{participant_id}:{arm.value}:{drill_number}:{job_retries}:{attempt}"
    )
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFF_FFFF


def claim_next_job(session: Session, now: datetime | None = None) -> GenerationJob | None:
    """Atomically claim the oldest pending generation job and return it, or None if none pending.

    Uses a single UPDATE ... WHERE id = (SELECT id FROM generation_jobs WHERE status = 'pending'
    ORDER BY created_at ASC, id ASC LIMIT 1) AND status = 'pending' RETURNING id statement (section
    6.2, 10.2; owner answer 4), commits immediately, and returns the refreshed GenerationJob. Two
    concurrent workers or poll cycles can never claim the same job.
    """
    claimed_at = now if now is not None else utc_now()
    stmt = sa.text(
        """
        UPDATE generation_jobs
        SET status = 'running', started_at = :started_at
        WHERE id = (
            SELECT id FROM generation_jobs
            WHERE status = 'pending'
            ORDER BY created_at ASC, id ASC
            LIMIT 1
        )
        AND status = 'pending'
        RETURNING id
        """
    ).bindparams(sa.bindparam("started_at", claimed_at, type_=sa.DateTime(timezone=True)))
    row = session.connection().execute(stmt).first()
    if row is None:
        session.rollback()
        return None
    claimed_id = str(row[0])
    session.commit()
    job = session.get(GenerationJob, claimed_id)
    if job is not None:
        session.refresh(job)
    return job


class GenerationService:
    """Orchestrates drill generation, validation retries, attempt logging, and drill persistence."""

    def __init__(
        self,
        session: Session,
        generators: Mapping[Arm, DrillGenerator],
        known_words: Collection[str],
        validator_config: ValidatorConfig | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        """Initialize the service with a DB session, arm->generator mapping, and corpus word set.

        If validator_config is None, loads it on demand from experiment_config via
        load_validator_config(session). max_attempts defaults to 5 (section 10.2, 13.5).
        """
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self._session = session
        self._generators = dict(generators)
        self._known_words = known_words
        self._validator_config = validator_config
        self._max_attempts = max_attempts

    def _get_validator_config(self) -> ValidatorConfig:
        if self._validator_config is None:
            self._validator_config = load_validator_config(self._session)
        return self._validator_config

    def _load_target_bigrams(self, participant_id: str, arm: Arm) -> tuple[str, ...]:
        """Return target bigrams for (participant_id, arm): () for CONTROL, else frozen rows."""
        if arm is Arm.CONTROL:
            return ()
        rows = self._session.exec(
            select(BigramAssignment)
            .where(
                col(BigramAssignment.participant_id) == participant_id,
                col(BigramAssignment.arm) == arm.value,
            )
            .order_by(col(BigramAssignment.baseline_rank), col(BigramAssignment.bigram))
        ).all()
        if not rows:
            raise MissingAssignmentError(
                f"no bigram_assignment rows for participant {participant_id!r} and arm {arm.value!r}"
            )
        return tuple(row.bigram for row in rows)

    def _existing_drill_count(self, participant_id: str, arm: Arm) -> int:
        """Count existing Drill rows for (participant_id, arm) to determine the next drill_number."""
        stmt = (
            select(sa.func.count())
            .select_from(Drill)
            .where(
                col(Drill.participant_id) == participant_id,
                col(Drill.arm) == arm.value,
            )
        )
        return int(self._session.exec(stmt).one())

    def _accepted_drills_for_job(self, job_id: str) -> int:
        """Count already-accepted drills linked to job_id in generation_attempts."""
        stmt = (
            select(sa.func.count())
            .select_from(GenerationAttempt)
            .where(
                col(GenerationAttempt.job_id) == job_id,
                col(GenerationAttempt.drill_id).is_not(None),
            )
        )
        return int(self._session.exec(stmt).one())

    def generate_with_retries(
        self,
        spec: DrillSpec,
        *,
        job_id: str | None = None,
        assignment_seed: int = 0,
        drill_number: int = 0,
        job_retries: int = 0,
    ) -> Drill:
        """Generate and validate one drill with up to max_attempts tries, saving attempts and drill.

        For attempt 0, uses spec.seed if non-zero, else derive_drill_seed(assignment_seed,
        spec.participant_id, spec.arm, drill_number, 0, job_retries). For attempt > 0, derives a
        fresh seed via derive_drill_seed (using assignment_seed if non-zero else spec.seed as the
        base seed). Every attempt is validated with validate(); when job_id is given, every attempt
        is persisted to generation_attempts. On acceptance, inserts and flushes the Drill row
        (status='ready') BEFORE inserting the GenerationAttempt row so fk_generation_attempts_drill_id_drills
        is satisfied, commits, and returns the Drill. Raises DrillGenerationExhaustedError if all
        max_attempts tries are rejected.
        """
        generator = self._generators.get(spec.arm)
        if generator is None:
            raise UnregisteredArmError(f"no generator registered for arm {spec.arm.value!r}")
        validator_config = self._get_validator_config()
        base_seed = assignment_seed if assignment_seed != 0 else spec.seed
        last_reasons: tuple[str, ...] = ()

        for attempt in range(self._max_attempts):
            if attempt == 0 and spec.seed != 0:
                attempt_seed = spec.seed
            else:
                attempt_seed = derive_drill_seed(
                    base_seed,
                    spec.participant_id,
                    spec.arm,
                    drill_number,
                    attempt,
                    job_retries,
                )
            attempt_spec = replace(spec, seed=attempt_seed)
            candidate: DrillCandidate = generator.generate(attempt_spec)
            result = validate(candidate.text, attempt_spec, validator_config, self._known_words)
            reason_tokens = [reason.value for reason in result.reasons]

            if result.accepted:
                drill = Drill(
                    participant_id=attempt_spec.participant_id,
                    arm=attempt_spec.arm.value,
                    target_bigrams=list(attempt_spec.target_bigrams),
                    text=candidate.text,
                    target_density=result.metrics.target_density,
                    mean_word_len=result.metrics.mean_word_len,
                    real_word_ratio=result.metrics.real_word_ratio,
                    generator_version=candidate.generator_version,
                    model_id=candidate.model_id,
                    prompt_version=candidate.prompt_version,
                    seed=candidate.seed,
                    status="ready",
                )
                self._session.add(drill)
                self._session.flush()
                if job_id is not None:
                    attempt_row = GenerationAttempt(
                        job_id=job_id,
                        drill_id=drill.id,
                        raw_output=candidate.raw_output,
                        clean_text=candidate.text,
                        density=result.metrics.target_density,
                        accepted=True,
                        reject_reasons=[],
                        gen_ms=candidate.gen_ms,
                        gen_tokens=candidate.gen_tokens,
                        tokens_per_sec=candidate.tokens_per_sec,
                        peak_memory_mb=candidate.peak_memory_mb,
                    )
                    self._session.add(attempt_row)
                self._session.commit()
                self._session.refresh(drill)
                return drill

            last_reasons = tuple(reason_tokens)
            if job_id is not None:
                rejected_row = GenerationAttempt(
                    job_id=job_id,
                    drill_id=None,
                    raw_output=candidate.raw_output,
                    clean_text=candidate.text,
                    density=result.metrics.target_density,
                    accepted=False,
                    reject_reasons=reason_tokens,
                    gen_ms=candidate.gen_ms,
                    gen_tokens=candidate.gen_tokens,
                    tokens_per_sec=candidate.tokens_per_sec,
                    peak_memory_mb=candidate.peak_memory_mb,
                )
                self._session.add(rejected_row)
                self._session.commit()

        raise DrillGenerationExhaustedError(
            f"exhausted {self._max_attempts} attempts for participant {spec.participant_id!r} "
            f"arm {spec.arm.value!r} drill {drill_number} (last reasons: {list(last_reasons)})"
        )

    def run_job(self, job_id: str) -> list[Drill]:
        """Run a generation job to completion or failure, returning the drills generated in this run.

        Loads the GenerationJob (raising JobNotFoundError if missing). If status is 'pending',
        transitions it to 'running' with started_at=utc_now(). Resolves the arm generator, config,
        and target bigrams (empty for CONTROL; frozen bigram_assignment rows for targeted arms).
        Generates the remaining requested drills (job.requested minus any drills already accepted
        for this job_id) via generate_with_retries, committing each drill and attempt as they happen.
        When all requested drills are ready, marks job.status='done', job.error=None,
        job.finished_at=utc_now(). On DrillGenerationExhaustedError or any other setup/generator
        exception, increments job.retries += 1, sets job.status='failed', job.error=str(exc),
        job.finished_at=utc_now(), commits, logs the failure, and returns the drills generated
        before the failure (owner answer 2).
        """
        job = self._session.get(GenerationJob, job_id)
        if job is None:
            raise JobNotFoundError(f"no generation_jobs row with id {job_id!r}")
        if job.status == "pending":
            job.status = "running"
            job.started_at = utc_now()
            self._session.add(job)
            self._session.commit()
            self._session.refresh(job)

        created_drills: list[Drill] = []
        try:
            arm = Arm(job.arm)
            if arm not in self._generators:
                raise UnregisteredArmError(f"no generator registered for arm {arm.value!r}")
            service_config = _load_service_config(self._session)
            self._get_validator_config()
            target_bigrams = self._load_target_bigrams(job.participant_id, arm)
            already_accepted = self._accepted_drills_for_job(job.id)
            remaining = max(0, job.requested - already_accepted)

            for _ in range(remaining):
                drill_number = self._existing_drill_count(job.participant_id, arm)
                seed = derive_drill_seed(
                    service_config.assignment_seed,
                    job.participant_id,
                    arm,
                    drill_number,
                    0,
                    job.retries,
                )
                spec = DrillSpec(
                    participant_id=job.participant_id,
                    arm=arm,
                    target_bigrams=target_bigrams,
                    length_chars=service_config.length_chars,
                    min_density=service_config.min_density,
                    max_density=service_config.max_density,
                    seed=seed,
                )
                drill = self.generate_with_retries(
                    spec,
                    job_id=job.id,
                    assignment_seed=service_config.assignment_seed,
                    drill_number=drill_number,
                    job_retries=job.retries,
                )
                created_drills.append(drill)

            job = self._session.get(GenerationJob, job_id)
            if job is not None:
                job.status = "done"
                job.error = None
                job.finished_at = utc_now()
                self._session.add(job)
                self._session.commit()
        except Exception as exc:  # noqa: BLE001
            self._session.rollback()
            failed_job = self._session.get(GenerationJob, job_id)
            if failed_job is not None:
                failed_job.retries += 1
                failed_job.status = "failed"
                failed_job.error = str(exc)
                failed_job.finished_at = utc_now()
                self._session.add(failed_job)
                self._session.commit()
            logger.error("generation job %s failed: %s", job_id, exc)
        return created_drills
