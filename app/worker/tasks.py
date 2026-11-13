import asyncio
from datetime import datetime, timezone
from uuid import UUID
from typing import Optional, List
from sqlalchemy import select, func
from app.db import SessionLocal
from app.models import Job, Record, AuditLog

BACKOFF_DELAYS = [2.0, 8.0, 30.0]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RetryableJobError(Exception):
    """Raised when an external transient error occurs (provider timeout, 5xx, 429)."""
    pass


async def _write_audit_log(
    session,
    tenant_id: UUID,
    action: str,
    entity_id: UUID,
    detail: dict,
    user_id: Optional[UUID] = None
):
    audit = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        entity_type="job",
        entity_id=entity_id,
        detail=detail,
    )
    session.add(audit)


async def execute_job_lifecycle(
    job_id: str,
    force_failure: bool = False,
    backoff_delays: Optional[List[float]] = None,
    max_attempts: int = 3
) -> bool:
    """
    Executes the job state machine with batch processing and exponential retry backoff.
    Can be run directly or within an ARQ worker context.
    """
    delays = backoff_delays if backoff_delays is not None else BACKOFF_DELAYS
    parsed_job_id = UUID(job_id) if isinstance(job_id, str) else job_id

    while True:
        async with SessionLocal() as session:
            result = await session.execute(select(Job).where(Job.id == parsed_job_id))
            job = result.scalar_one_or_none()
            if not job:
                return False

            job.attempts += 1
            current_attempt = job.attempts
            job.status = "running"
            if job.started_at is None:
                job.started_at = utcnow()

            await _write_audit_log(
                session=session,
                tenant_id=job.tenant_id,
                action="job.running",
                entity_id=job.id,
                detail={"attempt": current_attempt, "status": "running"},
                user_id=job.created_by
            )
            await session.commit()

        try:
            if force_failure:
                raise RetryableJobError("Simulated provider timeout / 5xx error")

            async with SessionLocal() as session:
                count_query = select(func.count()).select_from(Record).where(Record.dataset_id == job.dataset_id)
                total_records = (await session.execute(count_query)).scalar() or 0

                batch_size = 50
                processed = 0

                if total_records == 0:
                    job_result = await session.execute(select(Job).where(Job.id == parsed_job_id))
                    j = job_result.scalar_one()
                    j.progress = 100
                    j.status = "completed"
                    j.finished_at = utcnow()
                    await _write_audit_log(
                        session=session,
                        tenant_id=j.tenant_id,
                        action="job.completed",
                        entity_id=j.id,
                        detail={"progress": 100, "status": "completed"},
                        user_id=j.created_by
                    )
                    await session.commit()
                    return True

                while processed < total_records:
                    batch_query = (
                        select(Record)
                        .where(Record.dataset_id == job.dataset_id)
                        .offset(processed)
                        .limit(batch_size)
                    )
                    batch_records = (await session.execute(batch_query)).scalars().all()
                    if not batch_records:
                        break

                    processed += len(batch_records)
                    progress = min(100, int((processed / total_records) * 100))

                    job_result = await session.execute(select(Job).where(Job.id == parsed_job_id))
                    j = job_result.scalar_one()
                    j.progress = progress
                    await session.commit()

                job_result = await session.execute(select(Job).where(Job.id == parsed_job_id))
                j = job_result.scalar_one()
                j.progress = 100
                j.status = "completed"
                j.finished_at = utcnow()
                await _write_audit_log(
                    session=session,
                    tenant_id=j.tenant_id,
                    action="job.completed",
                    entity_id=j.id,
                    detail={"progress": 100, "status": "completed"},
                    user_id=j.created_by
                )
                await session.commit()
                return True

        except Exception as exc:
            async with SessionLocal() as session:
                job_result = await session.execute(select(Job).where(Job.id == parsed_job_id))
                j = job_result.scalar_one()

                if current_attempt < max_attempts:
                    j.status = "retrying"
                    j.error = str(exc)
                    delay = delays[min(current_attempt - 1, len(delays) - 1)]
                    await _write_audit_log(
                        session=session,
                        tenant_id=j.tenant_id,
                        action="job.retrying",
                        entity_id=j.id,
                        detail={"attempt": current_attempt, "retry_in_seconds": delay, "error": str(exc)},
                        user_id=j.created_by
                    )
                    await session.commit()

                    await asyncio.sleep(delay)
                    continue
                else:
                    j.status = "failed"
                    j.error = str(exc)
                    j.finished_at = utcnow()
                    await _write_audit_log(
                        session=session,
                        tenant_id=j.tenant_id,
                        action="job.failed",
                        entity_id=j.id,
                        detail={"attempts": current_attempt, "status": "failed", "error": str(exc)},
                        user_id=j.created_by
                    )
                    await session.commit()
                    return False


async def analyze_dataset(ctx, job_id: str):
    """ARQ task handler."""
    return await execute_job_lifecycle(job_id)
