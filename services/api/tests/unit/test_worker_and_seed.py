"""Unit tests for GenerationService helpers, seed derivation, and heartbeat helpers (T2.5)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from typist.generation.base import Arm
from typist.generation.service import derive_drill_seed
from typist.worker import heartbeat_path, read_heartbeat_age_s, write_heartbeat


def test_derive_drill_seed_is_deterministic_and_31_bit() -> None:
    seed1 = derive_drill_seed(
        assignment_seed=42,
        participant_id="p-001",
        arm=Arm.CONTROL,
        drill_number=0,
        attempt=0,
        job_retries=0,
    )
    seed2 = derive_drill_seed(
        assignment_seed=42,
        participant_id="p-001",
        arm=Arm.CONTROL,
        drill_number=0,
        attempt=0,
        job_retries=0,
    )
    assert seed1 == seed2
    assert 0 <= seed1 < 2**31

    # Changing any parameter produces a different seed
    assert derive_drill_seed(99, "p-001", Arm.CONTROL, 0, 0, 0) != seed1
    assert derive_drill_seed(42, "p-002", Arm.CONTROL, 0, 0, 0) != seed1
    assert derive_drill_seed(42, "p-001", Arm.HEURISTIC, 0, 0, 0) != seed1
    assert derive_drill_seed(42, "p-001", Arm.CONTROL, 1, 0, 0) != seed1
    assert derive_drill_seed(42, "p-001", Arm.CONTROL, 0, 1, 0) != seed1
    assert derive_drill_seed(42, "p-001", Arm.CONTROL, 0, 0, 1) != seed1


def test_heartbeat_write_and_read_age_s(tmp_path: Path) -> None:
    db_path = tmp_path / "typist.db"

    # Absent file
    assert read_heartbeat_age_s(db_path) is None

    # Write heartbeat
    written_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    hb_file = write_heartbeat(db_path, now=written_at)
    assert hb_file == heartbeat_path(db_path)
    assert hb_file.is_file()

    # Same time -> 0.0
    assert read_heartbeat_age_s(db_path, now=written_at) == 0.0

    # 4.25 seconds later
    assert read_heartbeat_age_s(db_path, now=written_at + timedelta(seconds=4.25)) == 4.25

    # Negative clock skew -> clamped to 0.0
    assert read_heartbeat_age_s(db_path, now=written_at - timedelta(seconds=2.0)) == 0.0

    # Corrupt / malformed text -> returns None
    hb_file.write_text("malformed-not-a-timestamp", encoding="utf-8")
    assert read_heartbeat_age_s(db_path, now=written_at) is None
