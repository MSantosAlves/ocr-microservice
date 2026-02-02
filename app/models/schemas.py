from enum import Enum
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    AUTO = "auto"
    PDF_NATIVE = "pdf_native"
    PRINTED = "printed"
    HANDWRITTEN = "handwritten"
    MIXED = "mixed"


class OCRRequest(BaseModel):
    document_type: DocumentType
    language: str = Field(default="pt-BR", min_length=2, max_length=8)
    preserve_layout: bool = True
    quality_threshold: float = Field(default=0.8, ge=0.0, le=1.0)


class OCRResponse(BaseModel):
    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    document_type: DocumentType
    processor_used: str
    processing_time_ms: int = Field(ge=0)
    warnings: List[str] = Field(default_factory=list)
    metadata: Optional[Dict[str, Union[str, int, float, bool]]] = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Union[str, int, float, bool, List[str]]]] = None
    suggestion: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
