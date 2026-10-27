"""Admin endpoints: assignment, pool status, jobs, and data checks (design doc 14; T2.8, T2.9)."""

import random
from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlmodel import Session, col, select

from typist.corpus.word_index import WordIndex
from typist.db import get_session, utc_now
from typist.models import BigramAssignment, GenerationJob, Participant
from typist.models.drills import DRILL_ARMS
from typist.schemas.admin import (
    AssignmentResponse,
    ChecksResponse,
    JobCreate,
    JobResponse,
    PoolResponse,
    ReplenishRequest,
)
from typist.services.assignment import (
    AssignmentError,
    assign_participant,
    load_assignment_config,
)
from typist.services.checks import (
    get_all_pools_status,
    get_participant_pool_status,
    run_participant_checks,
)
from typist.services.participants import ParticipantNotFoundError
from typist.services.session_planner import replenish_drill_pool
from typist.services.test_composer import (
    BaselinePassagesNotFoundError,
    compose_and_persist_retest,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def get_word_index(request: Request) -> WordIndex:
    """Dependency to load the WordIndex from the app's configured corpus_dir."""
    return WordIndex.load(request.app.state.settings.corpus_dir)


@router.post(
    "/participants/{participant_id}/assign",
    response_model=AssignmentResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "participant not found"},
        status.HTTP_409_CONFLICT: {
            "description": "invalid status, baseline incomplete, already assigned, or too few candidates"
        },
    },
)
def post_admin_assign(
    participant_id: str,
    session: Annotated[Session, Depends(get_session)],
    index: Annotated[WordIndex, Depends(get_word_index)],
) -> AssignmentResponse:
    """Rank, split, map and freeze weak bigrams; transitions participant to 'assigned'."""
    participant = session.get(Participant, participant_id)
    if participant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="participant not found")
    if participant.status != "baseline":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"participant status {participant.status!r} cannot be assigned; must be 'baseline'",
        )
    try:
        config = load_assignment_config(session)
        rng = random.Random(f"{config.seed}:{participant_id}")
        rows = assign_participant(session, participant_id, rng=rng, now=utc_now(), index=index)
    except ParticipantNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="participant not found"
        ) from error
    except AssignmentError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

    form_b_composed = False
    with suppress(BaselinePassagesNotFoundError, ValueError):
        compose_and_persist_retest(session, participant_id, index)
        form_b_composed = True

    mapping = {row.set_label: row.arm for row in rows}
    return AssignmentResponse(
        participant_id=participant_id,
        status="assigned",
        frozen_bigrams=len(rows),
        mapping=mapping,
        form_b_composed=form_b_composed,
    )


@router.get(
    "/pool",
    response_model=list[PoolResponse],
    responses={status.HTTP_404_NOT_FOUND: {"description": "participant not found"}},
)
def get_admin_pool(
    session: Annotated[Session, Depends(get_session)],
    participant_id: str | None = Query(None, description="Filter by participant ID"),
) -> list[PoolResponse]:
    """Get ready drill counts and deficit per arm for all participants or a specific participant."""
    if participant_id is not None:
        try:
            return [get_participant_pool_status(session, participant_id)]
        except ParticipantNotFoundError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="participant not found"
            ) from error
    return get_all_pools_status(session)


@router.post(
    "/pool/replenish",
    response_model=list[JobResponse],
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "participant not found"},
        status.HTTP_409_CONFLICT: {"description": "participant has no frozen assignment"},
    },
)
def post_admin_pool_replenish(
    payload: ReplenishRequest,
    session: Annotated[Session, Depends(get_session)],
) -> list[JobResponse]:
    """Top up drill pool buffers for a participant by enqueueing generation jobs."""
    participant = session.get(Participant, payload.participant_id)
    if participant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="participant not found")

    has_assignment = session.exec(
        select(BigramAssignment.bigram)
        .where(col(BigramAssignment.participant_id) == payload.participant_id)
        .limit(1)
    ).first()
    if has_assignment is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="participant has no frozen bigram assignment; assign first",
        )

    jobs = replenish_drill_pool(session, payload.participant_id)
    return [
        JobResponse(
            id=job.id,
            participant_id=job.participant_id,
            arm=job.arm,
            requested=job.requested,
            status=job.status,
            retries=job.retries,
            error=job.error,
            created_at=job.created_at or utc_now(),
            started_at=job.started_at,
            finished_at=job.finished_at,
        )
        for job in jobs
    ]


@router.get("/jobs", response_model=list[JobResponse])
def get_admin_jobs(
    session: Annotated[Session, Depends(get_session)],
    participant_id: str | None = Query(None, description="Filter by participant ID"),
    job_status: str | None = Query(None, alias="status", description="Filter by job status"),
    limit: int = Query(50, ge=1, le=200, description="Max jobs to return"),
) -> list[JobResponse]:
    """List recent generation jobs ordered newest first."""
    statement = select(GenerationJob)
    if participant_id is not None:
        statement = statement.where(col(GenerationJob.participant_id) == participant_id)
    if job_status is not None:
        statement = statement.where(col(GenerationJob.status) == job_status)
    statement = statement.order_by(
        col(GenerationJob.created_at).desc(), col(GenerationJob.id).desc()
    ).limit(limit)

    jobs = session.exec(statement).all()
    return [
        JobResponse(
            id=job.id,
            participant_id=job.participant_id,
            arm=job.arm,
            requested=job.requested,
            status=job.status,
            retries=job.retries,
            error=job.error,
            created_at=job.created_at or utc_now(),
            started_at=job.started_at,
            finished_at=job.finished_at,
        )
        for job in jobs
    ]


@router.post(
    "/jobs",
    response_model=list[JobResponse],
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "participant not found"},
        status.HTTP_409_CONFLICT: {"description": "unassigned participant for targeted arm"},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"description": "invalid arm or requested count"},
    },
)
def post_admin_jobs(
    payload: JobCreate,
    session: Annotated[Session, Depends(get_session)],
) -> list[JobResponse]:
    """Enqueue generation job(s) manually for an arm, or replenish all deficit arms if arm is omitted."""
    participant = session.get(Participant, payload.participant_id)
    if participant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="participant not found")

    if payload.arm is None:
        has_assignment = session.exec(
            select(BigramAssignment.bigram)
            .where(col(BigramAssignment.participant_id) == payload.participant_id)
            .limit(1)
        ).first()
        if has_assignment is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="participant has no frozen bigram assignment; assign first",
            )
        jobs = replenish_drill_pool(session, payload.participant_id)
        return [
            JobResponse(
                id=job.id,
                participant_id=job.participant_id,
                arm=job.arm,
                requested=job.requested,
                status=job.status,
                retries=job.retries,
                error=job.error,
                created_at=job.created_at or utc_now(),
                started_at=job.started_at,
                finished_at=job.finished_at,
            )
            for job in jobs
        ]

    if payload.arm not in DRILL_ARMS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown arm {payload.arm!r}; must be one of {DRILL_ARMS}",
        )

    if payload.arm != "control":
        arm_assignment = session.exec(
            select(BigramAssignment.bigram)
            .where(
                col(BigramAssignment.participant_id) == payload.participant_id,
                col(BigramAssignment.arm) == payload.arm,
            )
            .limit(1)
        ).first()
        if arm_assignment is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"participant has no frozen bigram assignment for arm {payload.arm!r}",
            )

    job = GenerationJob(
        participant_id=payload.participant_id,
        arm=payload.arm,
        requested=payload.requested,
        status="pending",
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    return [
        JobResponse(
            id=job.id,
            participant_id=job.participant_id,
            arm=job.arm,
            requested=job.requested,
            status=job.status,
            retries=job.retries,
            error=job.error,
            created_at=job.created_at or utc_now(),
            started_at=job.started_at,
            finished_at=job.finished_at,
        )
    ]


@router.get(
    "/checks/{participant_id}",
    response_model=ChecksResponse,
    responses={status.HTTP_404_NOT_FOUND: {"description": "participant not found"}},
)
def get_admin_checks(
    participant_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> ChecksResponse:
    """Run data quality checks and return session trends for a participant."""
    try:
        return run_participant_checks(session, participant_id)
    except ParticipantNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="participant not found"
        ) from error
