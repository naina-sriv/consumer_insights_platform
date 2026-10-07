from pydantic import BaseModel
from typing import Literal

class DatasetResponse(BaseModel):
    id: str
    name: str
    row_count: int
    status: str

class DatasetCreateResponse(DatasetResponse):
    pass
