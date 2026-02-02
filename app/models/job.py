from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field

from app.models.schemas import ErrorDetail, OCRResponse


class JobStatus(str, Enum):
    PENDING = "PENDING"
    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"


class JobType(str, Enum):
    SINGLE = "single"
    BULK_PARENT = "bulk_parent"
    BULK_CHILD = "bulk_child"


class ChildJobStatus(BaseModel):
    job_id: str
    filename: str
    status: JobStatus
    result: Optional[OCRResponse] = None
    error: Optional[ErrorDetail] = None
    duration_ms: Optional[int] = Field(default=None, ge=0)


class OCRJob(BaseModel):
    job_id: str
    status: JobStatus
    job_type: JobType = JobType.SINGLE
    parent_job_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    input_meta: Dict[str, Union[str, int, float, bool]]
    children: Optional[List[ChildJobStatus]] = None
    children_summary: Optional[Dict[str, int]] = None
    result: Optional[OCRResponse] = None
    error: Optional[ErrorDetail] = None
    duration_ms: Optional[int] = Field(default=None, ge=0)


class JobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus


class BulkJobCreateResponse(BaseModel):
    parent_job_id: str
    status: JobStatus
    children: List[ChildJobStatus]
