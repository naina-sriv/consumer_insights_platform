import asyncio
import json
import logging
from typing import AsyncGenerator
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user, require_role
from app.db import SessionLocal, get_session, scoped
from app.models import AuditLog, Dataset, Job, User
from app.schemas.job_schemas import (
    JobCreateRequest,
    JobCreateResponse,
    JobResponse,
)
from app.worker.queue import get_arq_pool

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue an asynchronous dataset analysis job",
)
async def create_job(
    req: JobCreateRequest,
    current_user: User = Depends(require_role("admin", "analyst")),
    session: AsyncSession = Depends(get_session),
):
    # Verify dataset exists and belongs to current tenant
    dataset_query = scoped(select(Dataset), current_user.tenant_id).where(Dataset.id == req.dataset_id)
    dataset_result = await session.execute(dataset_query)
    dataset = dataset_result.scalar_one_or_none()

    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Dataset not found"}},
        )

    # Check for idempotent job submission
    if req.idempotency_key:
        idempotency_query = select(Job).where(
            Job.tenant_id == current_user.tenant_id,
            Job.idempotency_key == req.idempotency_key,
        )
        existing_result = await session.execute(idempotency_query)
        existing_job = existing_result.scalar_one_or_none()
        if existing_job:
            logger.info("Returning existing job %s for idempotency key %s", existing_job.id, req.idempotency_key)
            return JobCreateResponse(id=str(existing_job.id), status=existing_job.status)

    # Initialize new job
    job = Job(
        tenant_id=current_user.tenant_id,
        dataset_id=req.dataset_id,
        type=req.type,
        status="queued",
        attempts=0,
        progress=0,
        created_by=current_user.id,
        idempotency_key=req.idempotency_key,
    )
    session.add(job)
    await session.flush()

    audit = AuditLog(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action="job.created",
        entity_type="job",
        entity_id=job.id,
        detail={"type": req.type, "dataset_id": str(req.dataset_id)},
    )
    session.add(audit)
    await session.commit()
    await session.refresh(job)

    # Enqueue to background Redis worker queue
    try:
        pool = await get_arq_pool()
        await pool.enqueue_job("analyze_dataset", str(job.id))
        logger.info("Enqueued job %s to ARQ queue", job.id)
    except Exception as exc:
        logger.warning("Could not dispatch job %s to Redis queue (will run on scheduler/worker): %s", job.id, exc)

    return JobCreateResponse(id=str(job.id), status="queued")


@router.get(
    "/{job_id}",
    response_model=JobResponse,
    summary="Get job status, progress, and execution metadata",
)
async def get_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    query = scoped(select(Job), current_user.tenant_id).where(Job.id == job_id)
    result = await session.execute(query)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Job not found"}},
        )

    return JobResponse(
        id=str(job.id),
        status=job.status,
        progress=job.progress,
        attempts=job.attempts,
        error=job.error,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


@router.get(
    "/{job_id}/events",
    summary="Live SSE stream for job progress updates",
)
async def stream_job_events(
    job_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    # Tenant verification
    query = scoped(select(Job), current_user.tenant_id).where(Job.id == job_id)
    result = await session.execute(query)
    initial_job = result.scalar_one_or_none()

    if not initial_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Job not found"}},
        )

    tenant_id = current_user.tenant_id

    async def event_generator() -> AsyncGenerator[str, None]:
        last_state: tuple[str, int] | None = None

        while True:
            if await request.is_disconnected():
                logger.debug("Client disconnected from SSE stream for job %s", job_id)
                break

            async with SessionLocal() as poll_session:
                q = scoped(select(Job), tenant_id).where(Job.id == job_id)
                res = await poll_session.execute(q)
                current_job = res.scalar_one_or_none()

                if not current_job:
                    break

                current_state = (current_job.status, current_job.progress)
                # Only push payload when state has actually changed
                if current_state != last_state:
                    data = json.dumps({"status": current_job.status, "progress": current_job.progress})
                    yield f"data: {data}\n\n"
                    last_state = current_state

                if current_job.status in ("completed", "failed"):
                    break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
