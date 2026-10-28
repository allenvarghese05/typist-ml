"""Generation worker process: heartbeat file, generator wiring, and job poll loop (design doc 6.2,
7, 10.2, 13.7, 14.1; D11; T2.5).

The worker polls generation_jobs for pending rows, claims one atomically via claim_next_job, and
runs it through GenerationService. On startup and on every poll cycle (before and after running a
job) it writes a UTC timestamp to a sibling heartbeat file (<db_path.name>.heartbeat) atomically via
os.replace (owner answer 1), which GET /api/v1/health reads to report worker_heartbeat_age_s without
touching SQLite or failing on unmigrated databases. No mlx-lm import at module level, so tests and
Linux CI can import and exercise the worker loop with control, heuristic, or fake generators (CLAUDE.md).
"""

import logging
import os
import signal
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import FrameType
from typing import Any, Final

from sqlalchemy import Engine
from sqlmodel import Session

from typist.corpus.word_index import WordIndex
from typist.db import utc_now
from typist.generation.base import Arm, DrillGenerator
from typist.generation.control import ControlGenerator
from typist.generation.heuristic import HeuristicGenerator
from typist.generation.llm import (
    LLMGenerator,
    LLMRuntimeProtocol,
    MLXRuntime,
    is_apple_silicon,
    is_model_cached,
)
from typist.generation.markov import MarkovGenerator
from typist.generation.service import GenerationService, claim_next_job
from typist.generation.validator import MissingConfigError, ValidatorConfig, load_validator_config
from typist.models import ExperimentConfig

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_S: Final[float] = 2.0


def heartbeat_path(db_path: Path) -> Path:
    """Return the sibling heartbeat file path for db_path: <db_path.name>.heartbeat (owner answer 1)."""
    return db_path.with_name(f"{db_path.name}.heartbeat")


def write_heartbeat(db_path: Path, now: datetime | None = None) -> Path:
    """Atomically write the current UTC timestamp (ISO-8601) to heartbeat_path(db_path).

    Writes to a .tmp sibling and replaces the target with os.replace so /health never reads a
    partially-written file. Creates the parent directory if needed. Returns the heartbeat file path.
    """
    recorded_at = now if now is not None else utc_now()
    target = heartbeat_path(db_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    tmp.write_text(recorded_at.isoformat(), encoding="utf-8")
    os.replace(tmp, target)
    return target


def read_heartbeat_age_s(db_path: Path, now: datetime | None = None) -> float | None:
    """Return the age in seconds (rounded to 3 decimals, >= 0.0) of the worker heartbeat, or None.

    Returns None when the heartbeat file does not exist or cannot be parsed as a timezone-aware or
    UTC ISO-8601 datetime (owner answer 1). Never raises on missing or malformed files.
    """
    target = heartbeat_path(db_path)
    try:
        raw = target.read_text(encoding="utf-8").strip()
        heartbeat_dt = datetime.fromisoformat(raw)
    except (OSError, ValueError):
        return None
    if heartbeat_dt.tzinfo is None:
        heartbeat_dt = heartbeat_dt.replace(tzinfo=UTC)
    reference = now if now is not None else utc_now()
    age = (reference - heartbeat_dt).total_seconds()
    return max(0.0, round(age, 3))


@dataclass(frozen=True)
class LLMConfig:
    model_id: str
    model_revision: str
    prompt_version: str
    temperature: float
    top_p: float
    max_tokens: int


def load_llm_config(session: Session) -> LLMConfig:
    """Read the 6 LLM configuration keys from experiment_config; raise MissingConfigError if absent."""
    keys = (
        "llm_model_id",
        "llm_model_revision",
        "llm_prompt_version",
        "llm_temperature",
        "llm_top_p",
        "llm_max_tokens",
    )
    values: dict[str, Any] = {}
    for key in keys:
        row = session.get(ExperimentConfig, key)
        if row is None:
            raise MissingConfigError(key)
        values[key] = row.value
    return LLMConfig(
        model_id=str(values["llm_model_id"]),
        model_revision=str(values["llm_model_revision"]),
        prompt_version=str(values["llm_prompt_version"]),
        temperature=float(values["llm_temperature"]),
        top_p=float(values["llm_top_p"]),
        max_tokens=int(values["llm_max_tokens"]),
    )


def build_default_generators(
    session: Session,
    index: WordIndex,
    *,
    runtime: LLMRuntimeProtocol | None = None,
) -> tuple[dict[Arm, DrillGenerator], ValidatorConfig]:
    """Build the default generators (CONTROL, HEURISTIC, MARKOV, and optionally LLM).

    If runtime is provided, Arm.LLM is registered using that runtime. If omitted,
    registers Arm.LLM only when running on Apple Silicon and the model snapshot is cached.
    """
    validator_config = load_validator_config(session)
    pool_row = session.get(ExperimentConfig, "control_word_pool")
    if pool_row is None:
        raise MissingConfigError("control_word_pool")
    pool_size = int(pool_row.value)
    beta_row = session.get(ExperimentConfig, "markov_beta")
    if beta_row is None:
        raise MissingConfigError("markov_beta")
    markov_beta = float(beta_row.value)

    generators: dict[Arm, DrillGenerator] = {
        Arm.CONTROL: ControlGenerator(index, validator_config, pool_size),
        Arm.HEURISTIC: HeuristicGenerator(index, validator_config, pool_size),
        Arm.MARKOV: MarkovGenerator(index, validator_config, markov_beta),
    }

    llm_config_row = session.get(ExperimentConfig, "llm_model_id")
    if llm_config_row is not None:
        llm_config = load_llm_config(session)
        llm_runtime: LLMRuntimeProtocol | None = runtime
        if llm_runtime is None and is_apple_silicon():
            if is_model_cached(llm_config.model_id, llm_config.model_revision):
                try:
                    llm_runtime = MLXRuntime(
                        model_id=llm_config.model_id,
                        revision=llm_config.model_revision,
                    )
                except Exception as exc:
                    logger.warning("Could not load MLXRuntime: %s", exc)

        if llm_runtime is not None:
            generators[Arm.LLM] = LLMGenerator(
                index=index,
                config=validator_config,
                runtime=llm_runtime,
                model_id=llm_config.model_id,
                prompt_version=llm_config.prompt_version,
                temperature=llm_config.temperature,
                top_p=llm_config.top_p,
                max_tokens=llm_config.max_tokens,
            )

    return generators, validator_config


def run_worker_once(
    engine: Engine,
    db_path: Path,
    index: WordIndex,
    *,
    generators: Mapping[Arm, DrillGenerator] | None = None,
    known_words: frozenset[str] | None = None,
    runtime: LLMRuntimeProtocol | None = None,
) -> str | None:
    """Write a heartbeat, claim at most one pending job, run it if found, and write a heartbeat.

    Returns the claimed job_id if a job was claimed and processed, or None if no pending job existed.
    """
    write_heartbeat(db_path)
    words = known_words if known_words is not None else frozenset(index.words)
    with Session(engine) as session:
        job = claim_next_job(session)
        if job is None:
            return None
        job_id = job.id
        if generators is not None:
            arm_generators: Mapping[Arm, DrillGenerator] = generators
            validator_config: ValidatorConfig | None = None
        else:
            arm_generators, validator_config = build_default_generators(
                session, index, runtime=runtime
            )
        service = GenerationService(
            session,
            arm_generators,
            words,
            validator_config=validator_config,
        )
        service.run_job(job_id)
    write_heartbeat(db_path)
    return job_id


def run_worker(
    engine: Engine,
    db_path: Path,
    index: WordIndex,
    *,
    once: bool = False,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
    stop_event: threading.Event | None = None,
    generators: Mapping[Arm, DrillGenerator] | None = None,
    runtime: LLMRuntimeProtocol | None = None,
) -> int:
    """Run the generation worker loop until stopped (or for a single cycle when once=True).

    Installs SIGINT/SIGTERM handlers (when called on the main thread) that set the stop event so
    `just dev` and Ctrl-C exit cleanly without leaving zombie processes (brief edge case 9). When
    a job is claimed, immediately loops to check for another pending job before sleeping; sleeps for
    poll_interval_s only when the queue is empty. Returns the number of jobs processed.
    """
    stopper = stop_event if stop_event is not None else threading.Event()
    known_words = frozenset(index.words)
    write_heartbeat(db_path)

    previous_sigint: Callable[[int, FrameType | None], object] | int | None = None
    previous_sigterm: Callable[[int, FrameType | None], object] | int | None = None
    install_signals = not once and threading.current_thread() is threading.main_thread()

    def _handle_signal(_signum: int, _frame: FrameType | None) -> None:
        stopper.set()

    if install_signals:
        previous_sigint = signal.getsignal(signal.SIGINT)
        previous_sigterm = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

    processed = 0
    try:
        if once:
            claimed = run_worker_once(
                engine,
                db_path,
                index,
                generators=generators,
                known_words=known_words,
                runtime=runtime,
            )
            return 1 if claimed is not None else 0

        while not stopper.is_set():
            claimed = run_worker_once(
                engine,
                db_path,
                index,
                generators=generators,
                known_words=known_words,
                runtime=runtime,
            )
            if claimed is not None:
                processed += 1
                continue
            stopper.wait(timeout=poll_interval_s)
    finally:
        if install_signals:
            if previous_sigint is not None:
                signal.signal(signal.SIGINT, previous_sigint)
            if previous_sigterm is not None:
                signal.signal(signal.SIGTERM, previous_sigterm)
    return processed
