# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Scripted keystroke generation and dev-only pipeline simulation (design doc 16; T2.10).

Provides generate_scripted_keystrokes to simulate realistic typing with monotonic timestamps,
dwell times, and backspace error corrections conforming to D14 attribution and D27 row invariants.
Provides run_pipeline_simulation to run the full end-to-end experiment loop.
Never used as scientific evidence (CLAUDE.md; Project Guide).
"""

from datetime import datetime, timedelta, timezone
import random
import unittest.mock
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session

from typist.corpus.word_index import WordIndex
from typist.db import unfreeze_config_for_testing
from typist.models import (
    Drill,
    ExperimentConfig,
    Participant,
)
from typist.schemas.events import KeystrokeEventIn
from typist.services.session_stats import recompute_stats
from typist.services.test_composer import (
    compose_baseline,
    load_baseline_config,
    persist_baseline,
)
from typist.worker import run_worker_once


def generate_scripted_keystrokes(
    target_text: str,
    *,
    error_rate: float = 0.05,
    seed: int = 42,
    base_t_down_ms: float = 1000.0,
    mean_iki_ms: float = 140.0,
    mean_dwell_ms: float = 70.0,
) -> list[KeystrokeEventIn]:
    """Generate realistic KeystrokeEventIn rows typing target_text with seeded errors and backspaces.

    For every position pos:
    - If rng.random() < error_rate on first attempt:
      1. Type wrong character (outcome="error", first_attempt=True).
      2. Type Backspace (outcome="backspace", target_index=pos, expected_char=None).
      3. Type correct character (outcome="correct", first_attempt=False).
    - Otherwise:
      1. Type correct character (outcome="correct", first_attempt=True).

    Strictly satisfies D14 (first-attempt error attribution), D15 (monotonic timestamps),
    D24 (no unexpected pause flags), D25 (backspace post-move target_index), and D27 (row fields).
    Dwell times are between 50ms and 90ms; IKIs are positive (~140ms); sequence starts at 0 with no gaps.
    """
    if not target_text:
        return []

    rng = random.Random(seed)
    events: list[KeystrokeEventIn] = []

    t_down = base_t_down_ms
    prev_t_down: float | None = None
    attempted_positions: set[int] = set()

    seq = 0
    pos = 0
    text_len = len(target_text)

    while pos < text_len:
        expected = target_text[pos]
        first_attempt = pos not in attempted_positions
        attempted_positions.add(pos)

        make_error = first_attempt and (rng.random() < error_rate)

        if make_error:
            wrong_char = "a" if expected != "a" else "b"
            dwell = round(mean_dwell_ms + (rng.random() - 0.5) * 20.0, 2)
            iki = (
                round(mean_iki_ms + (rng.random() - 0.5) * 40.0, 2)
                if prev_t_down is not None
                else None
            )
            t_up = round(t_down + dwell, 2)
            code = f"Key{wrong_char.upper()}"
            events.append(
                KeystrokeEventIn(
                    seq=seq,
                    key=wrong_char,
                    code=code,
                    t_down_ms=round(t_down, 2),
                    t_up_ms=t_up,
                    dwell_ms=dwell,
                    iki_ms=iki,
                    target_index=pos,
                    expected_char=expected,
                    outcome="error",
                    first_attempt=True,
                    after_pause=False,
                    handler_ms=0.2,
                    dispatch_lag_ms=0.5,
                )
            )
            seq += 1
            prev_t_down = t_down
            t_down += round(mean_iki_ms + (rng.random() - 0.5) * 40.0, 2)

            dwell = round(mean_dwell_ms + (rng.random() - 0.5) * 20.0, 2)
            iki = round(mean_iki_ms + (rng.random() - 0.5) * 40.0, 2)
            t_up = round(t_down + dwell, 2)
            events.append(
                KeystrokeEventIn(
                    seq=seq,
                    key="Backspace",
                    code="Backspace",
                    t_down_ms=round(t_down, 2),
                    t_up_ms=t_up,
                    dwell_ms=dwell,
                    iki_ms=iki,
                    target_index=pos,
                    expected_char=None,
                    outcome="backspace",
                    first_attempt=None,
                    after_pause=False,
                    handler_ms=0.2,
                    dispatch_lag_ms=0.5,
                )
            )
            seq += 1
            prev_t_down = t_down
            t_down += round(mean_iki_ms + (rng.random() - 0.5) * 40.0, 2)

            dwell = round(mean_dwell_ms + (rng.random() - 0.5) * 20.0, 2)
            iki = round(mean_iki_ms + (rng.random() - 0.5) * 40.0, 2)
            t_up = round(t_down + dwell, 2)
            code = "Space" if expected == " " else f"Key{expected.upper()}"
            events.append(
                KeystrokeEventIn(
                    seq=seq,
                    key=expected,
                    code=code,
                    t_down_ms=round(t_down, 2),
                    t_up_ms=t_up,
                    dwell_ms=dwell,
                    iki_ms=iki,
                    target_index=pos,
                    expected_char=expected,
                    outcome="correct",
                    first_attempt=False,
                    after_pause=False,
                    handler_ms=0.2,
                    dispatch_lag_ms=0.5,
                )
            )
            seq += 1
            prev_t_down = t_down
            t_down += round(mean_iki_ms + (rng.random() - 0.5) * 40.0, 2)
            pos += 1
        else:
            dwell = round(mean_dwell_ms + (rng.random() - 0.5) * 20.0, 2)
            iki = (
                round(mean_iki_ms + (rng.random() - 0.5) * 40.0, 2)
                if prev_t_down is not None
                else None
            )
            t_up = round(t_down + dwell, 2)
            code = "Space" if expected == " " else f"Key{expected.upper()}"
            events.append(
                KeystrokeEventIn(
                    seq=seq,
                    key=expected,
                    code=code,
                    t_down_ms=round(t_down, 2),
                    t_up_ms=t_up,
                    dwell_ms=dwell,
                    iki_ms=iki,
                    target_index=pos,
                    expected_char=expected,
                    outcome="correct",
                    first_attempt=first_attempt,
                    after_pause=False,
                    handler_ms=0.2,
                    dispatch_lag_ms=0.5,
                )
            )
            seq += 1
            prev_t_down = t_down
            t_down += round(mean_iki_ms + (rng.random() - 0.5) * 40.0, 2)
            pos += 1

    return events


@dataclass(frozen=True)
class PipelineSimulationResult:
    """Summary metrics returned by run_pipeline_simulation."""

    participant_id: str
    alias: str
    status: str
    baseline_sessions: int
    practice_sessions: int
    retest_sessions: int
    total_keystrokes: int
    checks_passed: bool
    recomputed_sessions: int


def run_pipeline_simulation(
    client: TestClient,
    engine: Engine,
    db_path: Path,
    index: WordIndex,
    *,
    participant_alias: str = "pipeline-dev",
    practice_days: int = 2,
    error_rate: float = 0.05,
    seed: int = 42,
    log_fn: Any = None,
    is_builder: bool = True,
) -> PipelineSimulationResult:
    """Execute the complete experiment lifecycle from enrolment to done with scripted keystrokes."""

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    id_rng = random.Random(seed)

    def _deterministic_uuid4() -> uuid.UUID:
        return uuid.UUID(int=id_rng.getrandbits(128), version=4)

    drill_counter = [0]
    base_time = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)
    original_drill_init = Drill.__init__

    def _deterministic_drill_init(self: Any, *args: Any, **kwargs: Any) -> None:
        drill_counter[0] += 1
        if "created_at" not in kwargs or kwargs.get("created_at") is None:
            kwargs["created_at"] = base_time + timedelta(seconds=drill_counter[0])
        original_drill_init(self, *args, **kwargs)

    with (
        unittest.mock.patch("typist.models.base.uuid.uuid4", side_effect=_deterministic_uuid4),
        unittest.mock.patch.object(Drill, "__init__", _deterministic_drill_init),
    ):
        # 1. Enrolment
        _log("1. Enrolling participant...")
        resp = client.post(
            "/api/v1/participants", json={"alias": participant_alias, "is_builder": is_builder}
        )
        assert resp.status_code in (200, 201), resp.text
        pid = resp.json()["id"]

        # 2. Consent
        _log("2. Recording consent...")
        resp = client.post(f"/api/v1/participants/{pid}/consent")
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "baseline"

        # 3. Setup baseline passages Form A
        _log("3. Composing baseline passages (Form A)...")
        with Session(engine) as s:
            cfg = load_baseline_config(s)
            passages = compose_baseline(cfg, index, random.Random(seed))
            persist_baseline(s, passages, replace=True)

        total_keystrokes = 0

        # 4. Simulate baseline sessions (2 parts)
        _log("4. Typing baseline sessions...")
        for part in range(2):
            resp = client.post(f"/api/v1/participants/{pid}/sessions")
            assert resp.status_code == 200, resp.text
            session_plan = resp.json()
            sid = session_plan["session_id"]
            block = session_plan["blocks"][0]
            bid = block["block_id"]

            client.post(f"/api/v1/blocks/{bid}/start")
            events = generate_scripted_keystrokes(
                block["target_text"], error_rate=error_rate, seed=seed + part
            )
            total_keystrokes += len(events)
            for i in range(0, len(events), 500):
                client.post(
                    f"/api/v1/blocks/{bid}/events",
                    json={"events": [e.model_dump() for e in events[i : i + 500]]},
                )
            client.post(f"/api/v1/blocks/{bid}/complete")
            complete_resp = client.post(f"/api/v1/sessions/{sid}/complete")
            assert complete_resp.status_code == 200, complete_resp.text

        # 5. Configure 2-set mode and assign
        _log("5. Configuring 2-set mode and assigning participant...")
        unfreeze_config_for_testing(engine)
        with Session(engine) as s:
            row_arms = s.get(ExperimentConfig, "arms_enabled")
            if row_arms:
                row_arms.value = ["control", "heuristic"]
                s.add(row_arms)
            row_pd = s.get(ExperimentConfig, "practice_days")
            if row_pd:
                row_pd.value = practice_days
                s.add(row_pd)
            s.commit()

        resp = client.post(f"/api/v1/admin/participants/{pid}/assign")
        assert resp.status_code == 200, resp.text
        assign_data = resp.json()
        assert assign_data["status"] == "assigned"
        assert assign_data["form_b_composed"] is True
        assert set(assign_data["mapping"].keys()) == {"A", "B"}

        # 6. Replenish drill pool and run worker
        _log("6. Replenishing drill pool and running generation worker...")
        resp = client.post("/api/v1/admin/pool/replenish", json={"participant_id": pid})
        assert resp.status_code == 200, resp.text
        while run_worker_once(engine, db_path, index) is not None:
            pass

        # 7. Simulate practice sessions across Latin square
        _log(f"7. Typing {practice_days} practice sessions across Latin square...")
        for day in range(1, practice_days + 1):
            # Ensure drill pool is replenished for the upcoming practice session
            client.post("/api/v1/admin/pool/replenish", json={"participant_id": pid})
            while run_worker_once(engine, db_path, index) is not None:
                pass
            resp = client.post(f"/api/v1/participants/{pid}/sessions")
            assert resp.status_code == 200, resp.text
            session_plan = resp.json()
            sid = session_plan["session_id"]
            blocks = session_plan["blocks"]
            assert len(blocks) == 2

            for b_idx, block in enumerate(blocks):
                bid = block["block_id"]
                client.post(f"/api/v1/blocks/{bid}/start")
                events = generate_scripted_keystrokes(
                    block["target_text"], error_rate=error_rate, seed=seed + 100 * day + b_idx
                )
                total_keystrokes += len(events)
                for i in range(0, len(events), 500):
                    client.post(
                        f"/api/v1/blocks/{bid}/events",
                        json={"events": [e.model_dump() for e in events[i : i + 500]]},
                    )
                client.post(f"/api/v1/blocks/{bid}/complete")

            complete_resp = client.post(f"/api/v1/sessions/{sid}/complete")
            assert complete_resp.status_code == 200, complete_resp.text

        # 8. Simulate retest sessions (2 parts)
        _log("8. Typing retest sessions (Form B)...")
        for part in range(2):
            resp = client.post(f"/api/v1/participants/{pid}/sessions")
            assert resp.status_code == 200, resp.text
            session_plan = resp.json()
            assert session_plan["phase"] == "retest"
            sid = session_plan["session_id"]
            block = session_plan["blocks"][0]
            bid = block["block_id"]

            client.post(f"/api/v1/blocks/{bid}/start")
            events = generate_scripted_keystrokes(
                block["target_text"], error_rate=error_rate, seed=seed + 200 + part
            )
            total_keystrokes += len(events)
            for i in range(0, len(events), 500):
                client.post(
                    f"/api/v1/blocks/{bid}/events",
                    json={"events": [e.model_dump() for e in events[i : i + 500]]},
                )
            client.post(f"/api/v1/blocks/{bid}/complete")
            complete_resp = client.post(f"/api/v1/sessions/{sid}/complete")
            assert complete_resp.status_code == 200, complete_resp.text

        # 9. Verify checks
        _log("9. Running data checks...")
        resp = client.get(f"/api/v1/admin/checks/{pid}")
        assert resp.status_code == 200, resp.text
        checks_data = resp.json()
        assert checks_data["passed"] is True
        assert checks_data["status"] == "done"

        # 10. Verify analysis endpoint
        _log("10. Querying outcome analysis...")
        resp = client.get(f"/api/v1/analysis/participants/{pid}")
        assert resp.status_code == 200, resp.text
        analysis_data = resp.json()
        assert analysis_data["status"] == "done"
        assert len(analysis_data["sets"]) == 2

        # 11. Verify stats recompute
        _log("11. Verifying stats recompute idempotence...")
        with Session(engine) as s:
            recompute_res = recompute_stats(s, pid)
            assert recompute_res.recomputed == 2 + practice_days + 2
            assert recompute_res.skipped == 0

        return PipelineSimulationResult(
            participant_id=pid,
            alias=participant_alias,
            status="done",
            baseline_sessions=2,
            practice_sessions=practice_days,
            retest_sessions=2,
            total_keystrokes=total_keystrokes,
            checks_passed=checks_data["passed"],
            recomputed_sessions=recompute_res.recomputed,
        )
