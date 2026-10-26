"""Unit tests for GenerationService helpers and seed derivation (T2.5)."""

from typist.generation.base import Arm
from typist.generation.service import derive_drill_seed


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
