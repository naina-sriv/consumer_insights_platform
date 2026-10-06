from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db import get_session, scoped
from app.models import Dataset, User
from app.auth.deps import get_current_user

router = APIRouter()

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
