from typing import Optional, Literal
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


class JobCreateRequest(BaseModel):
    dataset_id: UUID
    type: Literal["analyze", "embed"] = "analyze"
    prompt_name: Optional[str] = None
    idempotency_key: Optional[str] = None


class JobCreateResponse(BaseModel):
    id: str
    status: str


class JobResponse(BaseModel):
    id: str
    status: str
    progress: int
    attempts: int
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class JobEvent(BaseModel):
    status: str
    progress: int
