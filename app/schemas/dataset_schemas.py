from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class DatasetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    source_type: Optional[str] = None
    row_count: int
    status: str
    created_at: Optional[datetime] = None


class DatasetCreateResponse(BaseModel):
    id: str
    name: str
    row_count: int
    status: str


class DatasetListResponse(BaseModel):
    items: list[DatasetResponse]
    total: int
