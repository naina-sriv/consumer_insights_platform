import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Sequence
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.models import AuditLog, Job, Record

logger = logging.getLogger(__name__)

DEFAULT_BACKOFF_DELAYS = [2.0, 8.0, 30.0]
BATCH_SIZE = 50


def utcnow() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class RetryableJobError(Exception):
    """Raised when an external transient error occurs (provider timeout, 5xx, rate limits)."""
    pass


async def _log_job_audit(
    session: AsyncSession,
    job: Job,
    action: str,
    detail: dict[str, Any],
) -> None:
    """Append a structured audit log entry for a job state change."""
    audit = AuditLog(
        tenant_id=job.tenant_id,
        user_id=job.created_by,
        action=action,
        entity_type="job",
        entity_id=job.id,
        detail=detail,
    )
    session.add(audit)


async def execute_job_lifecycle(
    job_id: str | uuid.UUID,
    force_failure: bool = False,
    backoff_delays: Optional[Sequence[float]] = None,
    max_attempts: int = 3,
) -> bool:
    """
    Executes the async job state machine with batch record processing and exponential retry backoff.

    State transitions:
    queued -> running -> completed
    queued -> running -> retrying -> running ... -> failed (if retries exhausted)
    """
    delays = backoff_delays if backoff_delays is not None else DEFAULT_BACKOFF_DELAYS
    parsed_id = uuid.UUID(str(job_id)) if not isinstance(job_id, uuid.UUID) else job_id

    while True:
        # Step 1: Transition job to 'running'
        async with SessionLocal() as session:
            result = await session.execute(select(Job).where(Job.id == parsed_id))
            job = result.scalar_one_or_none()
            if not job:
                logger.error("Job %s not found in database", parsed_id)
                return False

            job.attempts += 1
            current_attempt = job.attempts
            job.status = "running"
            if job.started_at is None:
                job.started_at = utcnow()

            await _log_job_audit(
                session,
                job,
                action="job.running",
                detail={"attempt": current_attempt, "status": "running"},
            )
            await session.commit()

        # Step 2: Attempt processing batches
        try:
            if force_failure:
                raise RetryableJobError("Simulated provider timeout / 5xx error")

            async with SessionLocal() as session:
                # Count total dataset records to calculate progress increments
                count_query = select(func.count()).select_from(Record).where(Record.dataset_id == job.dataset_id)
                total_records = (await session.execute(count_query)).scalar() or 0

                processed = 0

                if total_records > 0:
                    # Keyset pagination on record id is O(N) rather than O(N^2) offset pagination
                    last_id = None
                    while processed < total_records:
                        query = (
                            select(Record.id)
                            .where(Record.dataset_id == job.dataset_id)
                            .order_by(Record.id)
                            .limit(BATCH_SIZE)
                        )
                        if last_id is not None:
                            query = query.where(Record.id > last_id)

                        record_ids = (await session.execute(query)).scalars().all()
                        if not record_ids:
                            break

                        last_id = record_ids[-1]
                        processed += len(record_ids)
                        progress = min(100, int((processed / total_records) * 100))

                        # Update progress in DB
                        job_res = await session.execute(select(Job).where(Job.id == parsed_id))
                        j = job_res.scalar_one()
                        j.progress = progress
                        await session.commit()

                # Mark job completed
                job_res = await session.execute(select(Job).where(Job.id == parsed_id))
                j = job_res.scalar_one()
                j.progress = 100
                j.status = "completed"
                j.finished_at = utcnow()

                await _log_job_audit(
                    session,
                    j,
                    action="job.completed",
                    detail={"progress": 100, "status": "completed"},
                )
                await session.commit()
                logger.info("Job %s completed successfully (records=%d)", parsed_id, total_records)
                return True

        except Exception as exc:
            # Step 3: Handle retry or terminal failure
            async with SessionLocal() as session:
                job_res = await session.execute(select(Job).where(Job.id == parsed_id))
                j = job_res.scalar_one()
                error_msg = str(exc)

                if current_attempt < max_attempts:
                    j.status = "retrying"
                    j.error = error_msg
                    delay = delays[min(current_attempt - 1, len(delays) - 1)]

                    await _log_job_audit(
                        session,
                        j,
                        action="job.retrying",
                        detail={
                            "attempt": current_attempt,
                            "retry_in_seconds": delay,
                            "error": error_msg,
                        },
                    )
                    await session.commit()
                    logger.warning(
                        "Job %s attempt %d failed: %s. Retrying in %ss...",
                        parsed_id,
                        current_attempt,
                        error_msg,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                else:
                    j.status = "failed"
                    j.error = error_msg
                    j.finished_at = utcnow()

                    await _log_job_audit(
                        session,
                        j,
                        action="job.failed",
                        detail={
                            "attempts": current_attempt,
                            "status": "failed",
                            "error": error_msg,
                        },
                    )
                    await session.commit()
                    logger.error(
                        "Job %s permanently failed after %d attempts: %s",
                        parsed_id,
                        current_attempt,
                        error_msg,
                    )
                    return False


async def analyze_dataset(ctx: dict[str, Any], job_id: str) -> bool:
    """ARQ background worker task entrypoint."""
    return await execute_job_lifecycle(job_id)
