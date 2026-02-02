from datetime import datetime
from enum import Enum
from typing import Dict, Optional, Union

from pydantic import BaseModel, Field

from app.models.schemas import ErrorDetail, OCRResponse


class JobStatus(str, Enum):
    PENDING = "PENDING"
    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class OCRJob(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    input_meta: Dict[str, Union[str, int, float, bool]]
    result: Optional[OCRResponse] = None
    error: Optional[ErrorDetail] = None
    duration_ms: Optional[int] = Field(default=None, ge=0)


class JobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus
