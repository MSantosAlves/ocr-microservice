import os
import uuid
from pathlib import Path
from typing import Dict, List, Tuple, Union

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image

from app.core.config import get_settings
from app.core.db import create_job, get_job, update_job
from app.core.orchestrator import OCRCoreOrchestrator, OCRProcessingError
from app.core.prompt_router import DocumentPromptRouter
from app.models.job import JobCreateResponse, JobStatus, OCRJob
from app.models.schemas import DocumentType, ErrorResponse, OCRRequest, OCRResponse
from app.tasks.ocr_tasks import process_ocr_job


router = APIRouter(prefix="/ocr", tags=["ocr"])
settings = get_settings()
orchestrator = OCRCoreOrchestrator()
prompt_router = DocumentPromptRouter()

ALLOWED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png"}


def _save_upload_to_temp(upload_file: UploadFile, max_bytes: int) -> Tuple[Path, int]:
    os.makedirs(settings.temp_dir, exist_ok=True)
    suffix = Path(upload_file.filename or "").suffix
    temp_path = Path(settings.temp_dir) / f"{uuid.uuid4().hex}{suffix}"

    size_bytes = 0
    with temp_path.open("wb") as temp_file:
        while True:
            chunk = upload_file.file.read(1024 * 1024)
            if not chunk:
                break
            size_bytes += len(chunk)
            if size_bytes > max_bytes:
                raise HTTPException(status_code=413, detail="File exceeds max size limit")
            temp_file.write(chunk)

    return temp_path, size_bytes


@router.post("/extract", response_model=OCRResponse)
def extract_text(
    file: UploadFile = File(...),
    document_type: DocumentType = Form(DocumentType.AUTO),
    language: str = Form("pt-BR"),
    preserve_layout: bool = Form(True),
    quality_threshold: float = Form(0.8),
) -> Union[OCRResponse, JSONResponse]:
    """
    Extrai texto de um documento.
    
    Args:
        file: Arquivo PDF, JPG ou PNG
        document_type: Tipo do documento. Use 'auto' (padrão) para classificação automática via router.
        language: Código do idioma (padrão: pt-BR)
        preserve_layout: Preservar layout original (padrão: True)
        quality_threshold: Limiar de qualidade mínima (0.0 a 1.0, padrão: 0.8)
    
    Returns:
        OCRResponse com texto extraído e metadados
    """
    if file.content_type not in ALLOWED_MIME_TYPES:
        return _error_response(
            status_code=415,
            code="UNSUPPORTED_DOCUMENT_TYPE",
            message="Unsupported file type",
            details={"content_type": file.content_type},
            suggestion="Upload a PDF, JPG, or PNG file",
        )

    request = OCRRequest(
        document_type=document_type,
        language=language,
        preserve_layout=preserve_layout,
        quality_threshold=quality_threshold,
    )

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    temp_path = None
    try:
        temp_path, size_bytes = _save_upload_to_temp(file, max_bytes)
        response = orchestrator.process_document(
            str(temp_path), file.content_type or "", request
        )
        response.metadata = {
            **(response.metadata or {}),
            "original_filename": file.filename or "",
            "content_type": file.content_type or "",
            "size_bytes": size_bytes,
        }
        return response
    except OCRProcessingError as error:
        return _error_response(
            status_code=error.status_code,
            code=error.code,
            message=error.message,
            details=error.details,
            suggestion=error.suggestion,
        )
    except Exception as error:
        return _error_response(
            status_code=500,
            code="OCR_FAILED",
            message="Failed to extract text",
            details={"reason": str(error)},
            suggestion="Try again later",
        )
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


@router.post("/extract-async", response_model=JobCreateResponse)
def extract_text_async(
    file: UploadFile = File(...),
    document_type: DocumentType = Form(DocumentType.AUTO),
    language: str = Form("pt-BR"),
    preserve_layout: bool = Form(True),
    quality_threshold: float = Form(0.8),
) -> Union[JobCreateResponse, JSONResponse]:
    if file.content_type not in ALLOWED_MIME_TYPES:
        return _error_response(
            status_code=415,
            code="UNSUPPORTED_DOCUMENT_TYPE",
            message="Unsupported file type",
            details={"content_type": file.content_type},
            suggestion="Upload a PDF, JPG, or PNG file",
        )

    request = OCRRequest(
        document_type=document_type,
        language=language,
        preserve_layout=preserve_layout,
        quality_threshold=quality_threshold,
    )

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    temp_path = None
    job_id = uuid.uuid4().hex
    job_created = False

    try:
        temp_path, size_bytes = _save_upload_to_temp(file, max_bytes)
        create_job(
            {
                "job_id": job_id,
                "status": JobStatus.PENDING.value,
                "input_meta": {
                    "original_filename": file.filename or "",
                    "content_type": file.content_type or "",
                    "size_bytes": size_bytes,
                    "document_type": document_type.value,
                    "language": language,
                    "preserve_layout": preserve_layout,
                    "quality_threshold": quality_threshold,
                },
            }
        )
        job_created = True
        process_ocr_job.delay(
            job_id,
            str(temp_path),
            file.content_type or "",
            request.model_dump(),
        )
        return JobCreateResponse(job_id=job_id, status=JobStatus.PENDING)
    except Exception as error:
        if job_created:
            update_job(
                job_id,
                {
                    "status": JobStatus.FAILED.value,
                    "error": {
                        "code": "JOB_ENQUEUE_FAILED",
                        "message": "Failed to enqueue job",
                        "details": {"reason": str(error)},
                        "suggestion": "Try again later",
                    },
                },
            )
        if temp_path and temp_path.exists():
            temp_path.unlink()
        return _error_response(
            status_code=500,
            code="JOB_ENQUEUE_FAILED",
            message="Failed to enqueue job",
            details={"reason": str(error)},
            suggestion="Try again later",
        )


@router.get("/jobs/{job_id}", response_model=OCRJob)
def get_job_status(job_id: str) -> OCRJob:
    job_data = get_job(job_id)
    if not job_data:
        raise HTTPException(status_code=404, detail="Job not found")
    return OCRJob(**job_data)


@router.get("/categories")
def get_categories():
    """
    Retorna as categorias de documentos disponíveis para classificação.
    
    Útil para entender quais tipos de documentos o sistema pode classificar
    e qual prompt será usado para cada categoria.
    """
    return {
        "categories": prompt_router.get_available_categories(),
        "default_category": "general",
        "classification_model": prompt_router.model,
    }


@router.post("/classify")
def classify_document(
    file: UploadFile = File(...),
):
    """
    Classifica um documento sem realizar a extração de texto.
    
    Útil para testar a classificação e entender qual prompt seria usado
    antes de fazer a extração completa.
    """
    if file.content_type not in {"image/jpeg", "image/png"}:
        return _error_response(
            status_code=415,
            code="UNSUPPORTED_FILE_TYPE",
            message="Only JPEG and PNG images are supported for classification",
            details={"content_type": file.content_type},
            suggestion="Upload a JPG or PNG file",
        )
    
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    temp_path = None
    
    try:
        temp_path, size_bytes = _save_upload_to_temp(file, max_bytes)
        
        with Image.open(temp_path) as image:
            prompt_name, metadata = prompt_router.classify(image)
        
        return {
            "prompt_file": prompt_name,
            "category": metadata.get("category"),
            "confidence": metadata.get("confidence"),
            "reasoning": metadata.get("reasoning"),
            "model_used": metadata.get("model"),
            "classification_time_ms": metadata.get("classification_time_ms"),
            "tokens": {
                "input": metadata.get("input_tokens"),
                "output": metadata.get("output_tokens"),
            },
            "is_fallback": metadata.get("is_fallback", False),
            "file_info": {
                "filename": file.filename,
                "content_type": file.content_type,
                "size_bytes": size_bytes,
            },
        }
        
    except Exception as error:
        return _error_response(
            status_code=500,
            code="CLASSIFICATION_FAILED",
            message="Failed to classify document",
            details={"reason": str(error)},
            suggestion="Try again with a different image",
        )
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def _error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict | None = None,
    suggestion: str | None = None,
) -> JSONResponse:
    error_response = ErrorResponse(
        error={
            "code": code,
            "message": message,
            "details": details,
            "suggestion": suggestion,
        }
    )
    return JSONResponse(status_code=status_code, content=error_response.model_dump())
