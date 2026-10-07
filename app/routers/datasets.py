from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db import get_session, scoped
from app.models import Dataset, User, Record
from app.auth.deps import get_current_user, require_role
from app.services.ingestion import parse_and_validate_file
from app.schemas.dataset_schemas import DatasetCreateResponse

router = APIRouter()

@router.post("", response_model=DatasetCreateResponse, status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    name: str = Form(...),
    source_type: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(require_role("admin", "analyst")),
    session: AsyncSession = Depends(get_session)
):
    if source_type not in ("reviews", "survey", "transcript"):
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "validation_error", "message": "Invalid source_type"}}
        )
    
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    if file_size > 20 * 1024 * 1024:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "validation_error", "message": "File exceeds 20MB limit"}}
        )
        
    valid_rows, bad_rows = parse_and_validate_file(file)
    
    if bad_rows:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "validation_error", "message": "Invalid rows in file", "bad_rows": bad_rows[:10]}}
        )
        
    if not valid_rows:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "validation_error", "message": "No valid rows found in file"}}
        )
        
    if len(valid_rows) > 20000:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "validation_error", "message": "Exceeds 20000 row limit"}}
        )
        
    dataset = Dataset(
        tenant_id=current_user.tenant_id,
        name=name,
        source_type=source_type,
        row_count=len(valid_rows),
        status="uploaded"
    )
    session.add(dataset)
    await session.flush()
    
    records_to_insert = [
        Record(
            tenant_id=current_user.tenant_id,
            dataset_id=dataset.id,
            external_id=row["external_id"],
            text=row["text"],
            metadata_=row["metadata"]
        ) for row in valid_rows
    ]
    session.add_all(records_to_insert)
    
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "validation_error", "message": "Duplicate external_id or db error"}}
        )
        
    await session.refresh(dataset)
    
    return {
        "id": str(dataset.id),
        "name": dataset.name,
        "row_count": dataset.row_count,
        "status": dataset.status
    }

@router.get("/{dataset_id}")
async def get_dataset(
    dataset_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    query = scoped(select(Dataset), current_user.tenant_id).where(Dataset.id == dataset_id)
    result = await session.execute(query)
    dataset = result.scalar_one_or_none()
    
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "not_found", "message": "Dataset not found"}}
        )
        
    return {
        "id": str(dataset.id),
        "name": dataset.name,
        "row_count": dataset.row_count,
        "status": dataset.status
    }
