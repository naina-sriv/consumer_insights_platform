import asyncio
import json
from uuid import UUID
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_session, scoped, SessionLocal
from app.models import Job, Dataset, User, AuditLog
from app.auth.deps import get_current_user, require_role
from app.schemas.job_schemas import (
    JobCreateRequest,
    JobCreateResponse,
    JobResponse,
)
from app.worker.queue import get_arq_pool

router = APIRouter()


@router.post("", response_model=JobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    req: JobCreateRequest,
    current_user: User = Depends(require_role("admin", "analyst")),
    session: AsyncSession = Depends(get_session)
):
    dataset_query = scoped(select(Dataset), current_user.tenant_id).where(Dataset.id == req.dataset_id)
    result = await session.execute(dataset_query)
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Dataset not found"}}
        )

    if req.idempotency_key:
        idempotency_query = select(Job).where(
            Job.tenant_id == current_user.tenant_id,
            Job.idempotency_key == req.idempotency_key
        )
        existing_result = await session.execute(idempotency_query)
        existing_job = existing_result.scalar_one_or_none()
        if existing_job:
            return JobCreateResponse(id=str(existing_job.id), status=existing_job.status)

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
        detail={"type": req.type, "dataset_id": str(req.dataset_id)}
    )
    session.add(audit)
    await session.commit()
    await session.refresh(job)

    try:
        pool = await get_arq_pool()
        await pool.enqueue_job("analyze_dataset", str(job.id))
    except Exception:
        pass

    return JobCreateResponse(id=str(job.id), status="queued")


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    query = scoped(select(Job), current_user.tenant_id).where(Job.id == job_id)
    result = await session.execute(query)
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Job not found"}}
        )

    return JobResponse(
        id=str(job.id),
        status=job.status,
        progress=job.progress,
        attempts=job.attempts,
        error=job.error,
        started_at=job.started_at,
        finished_at=job.finished_at
    )


@router.get("/{job_id}/events")
async def stream_job_events(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    query = scoped(select(Job), current_user.tenant_id).where(Job.id == job_id)
    result = await session.execute(query)
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Job not found"}}
        )

    tenant_id = current_user.tenant_id

    async def event_generator() -> AsyncGenerator[str, None]:
        while True:
            async with SessionLocal() as poll_session:
                q = scoped(select(Job), tenant_id).where(Job.id == job_id)
                res = await poll_session.execute(q)
                current_job = res.scalar_one_or_none()
                if not current_job:
                    break

                data = json.dumps({"status": current_job.status, "progress": current_job.progress})
                yield f"data: {data}\n\n"

                if current_job.status in ("completed", "failed"):
                    break

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
