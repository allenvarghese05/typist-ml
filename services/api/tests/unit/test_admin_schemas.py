"""Unit tests for admin schemas (T2.9)."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from typist.schemas.admin import (
    CheckDetail,
    ChecksResponse,
    DataChecksResult,
    DwellCheckDetail,
    JobCreate,
    MissingKeyupsDetail,
    SessionTrendEntry,
)


def test_job_create_validation() -> None:
    job = JobCreate(participant_id="p-1")
    assert job.requested == 1
    assert job.arm is None

    with pytest.raises(ValidationError):
        JobCreate(participant_id="p-1", requested=0)

    with pytest.raises(ValidationError):
        JobCreate(participant_id="p-1", requested=-5)


def test_checks_response_serialization() -> None:
    now = datetime.now(UTC)
    response = ChecksResponse(
        participant_id="p-1",
        alias="pilot-1",
        status="assigned",
        passed=True,
        checks=DataChecksResult(
            seq_gaps=CheckDetail(passed=True, count=0, details=[]),
            dwell_anomalies=DwellCheckDetail(
                passed=True, negative_count=0, over_1000ms_count=0, details=[]
            ),
            short_blocks=CheckDetail(passed=True, count=0, details=[]),
            missing_keyups=MissingKeyupsDetail(
                passed=True, total_events=100, missing_count=0, missing_share=0.0, details=[]
            ),
            in_progress_sessions=CheckDetail(passed=True, count=0, details=[]),
        ),
        trend=[
            SessionTrendEntry(
                session_id="s-1",
                phase="practice",
                day_index=1,
                started_at=now,
                wpm=65.2,
                accuracy=0.98,
                per_set_error_rate={"A": 0.05, "B": None},
                per_set_attempts={"A": 20, "B": 0},
                per_set_errors={"A": 1, "B": 0},
            )
        ],
    )
    json_data = response.model_dump_json()
    assert "pilot-1" in json_data
    assert "65.2" in json_data

    deserialized = ChecksResponse.model_validate_json(json_data)
    assert deserialized.participant_id == "p-1"
    assert deserialized.checks.seq_gaps.passed is True
    assert deserialized.trend[0].per_set_error_rate["A"] == 0.05
