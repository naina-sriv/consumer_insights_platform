import logging
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user, require_role
from app.config import settings
from app.db import get_session, scoped
from app.models import AuditLog, Dataset, Record, User
from app.schemas.dataset_schemas import (
    DatasetCreateResponse,
    DatasetListResponse,
    DatasetResponse,
)
from app.services.ingestion import parse_and_validate_file

logger = logging.getLogger(__name__)
router = APIRouter()

ALLOWED_SOURCE_TYPES = {"reviews", "survey", "transcript"}
BATCH_INSERT_SIZE = 1000


@router.post(
    "",
    response_model=DatasetCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest a consumer dataset (CSV, JSON, or JSONL)",
)
async def upload_dataset(
    name: str = Form(..., min_length=1, max_length=200, description="Name of the dataset"),
    source_type: str = Form(..., description="Type of data: reviews, survey, or transcript"),
    file: UploadFile = File(..., description="Dataset file (.csv, .json, or .jsonl)"),
    current_user: User = Depends(require_role("admin", "analyst")),
    session: AsyncSession = Depends(get_session),
):
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "validation_error",
                    "message": f"Invalid source_type. Allowed: {sorted(ALLOWED_SOURCE_TYPES)}",
                }
            },
        )

    # Check file size without loading full file multiple times
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "validation_error",
                    "message": f"File exceeds maximum allowed size of {settings.max_upload_mb}MB",
                }
            },
        )

    valid_rows, bad_rows = parse_and_validate_file(file)

    if bad_rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "validation_error",
                    "message": "Invalid rows in file",
                    "bad_rows": bad_rows[:10],
                }
            },
        )

    if not valid_rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "validation_error",
                    "message": "No valid rows found in file",
                }
            },
        )

    if len(valid_rows) > settings.max_rows_per_dataset:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "validation_error",
                    "message": f"Exceeds {settings.max_rows_per_dataset} row limit",
                }
            },
        )

    # Create dataset entity
    dataset = Dataset(
        tenant_id=current_user.tenant_id,
        name=name.strip(),
        source_type=source_type,
        row_count=len(valid_rows),
        status="uploaded",
        uploaded_by=current_user.id,
    )
    session.add(dataset)
    await session.flush()

    # Batch insert records to maintain low memory pressure and fast write throughput
    for i in range(0, len(valid_rows), BATCH_INSERT_SIZE):
        batch = valid_rows[i : i + BATCH_INSERT_SIZE]
        records_to_insert = [
            Record(
                tenant_id=current_user.tenant_id,
                dataset_id=dataset.id,
                external_id=row["external_id"],
                text=row["text"],
                metadata_=row.get("metadata"),
            )
            for row in batch
        ]
        session.add_all(records_to_insert)

    # Write audit log entry
    audit = AuditLog(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action="dataset.uploaded",
        entity_type="dataset",
        entity_id=dataset.id,
        detail={
            "name": dataset.name,
            "source_type": dataset.source_type,
            "row_count": dataset.row_count,
        },
    )
    session.add(audit)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        logger.error("Integrity error persisting dataset %s: %s", dataset.name, exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "validation_error",
                    "message": "Duplicate external_id or db constraint violation",
                }
            },
        )

    await session.refresh(dataset)
    logger.info(
        "Tenant %s uploaded dataset %s (%d rows)",
        current_user.tenant_id,
        dataset.id,
        dataset.row_count,
    )

    return DatasetCreateResponse(
        id=str(dataset.id),
        name=dataset.name,
        row_count=dataset.row_count,
        status=dataset.status,
    )


@router.get(
    "",
    response_model=DatasetListResponse,
    summary="List all datasets for current tenant",
)
async def list_datasets(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    query = scoped(select(Dataset), current_user.tenant_id).order_by(Dataset.created_at.desc())
    result = await session.execute(query)
    datasets = result.scalars().all()

    items = [
        DatasetResponse(
            id=str(d.id),
            name=d.name,
            source_type=d.source_type,
            row_count=d.row_count,
            status=d.status,
            created_at=d.created_at,
        )
        for d in datasets
    ]
    return DatasetListResponse(items=items, total=len(items))


@router.get(
    "/{dataset_id}",
    response_model=DatasetResponse,
    summary="Get details for a specific dataset",
)
async def get_dataset(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    try:
        parsed_id = uuid.UUID(dataset_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Dataset not found"}},
        )

    query = scoped(select(Dataset), current_user.tenant_id).where(Dataset.id == parsed_id)
    result = await session.execute(query)
    dataset = result.scalar_one_or_none()

    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Dataset not found"}},
        )

    return DatasetResponse(
        id=str(dataset.id),
        name=dataset.name,
        source_type=dataset.source_type,
        row_count=dataset.row_count,
        status=dataset.status,
        created_at=dataset.created_at,
    )
