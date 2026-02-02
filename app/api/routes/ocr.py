import os
import uuid
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Tuple, Union

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image

from app.core.config import get_settings
from app.core.db import (
    create_bulk_jobs,
    create_job,
    get_children_jobs,
    get_job,
    update_job,
    update_parent_aggregate,
)
from app.core.orchestrator import OCRCoreOrchestrator, OCRProcessingError
from app.core.prompt_router import DocumentPromptRouter
from app.models.job import (
    BulkJobCreateResponse,
    ChildJobStatus,
    JobCreateResponse,
    JobStatus,
    JobType,
    OCRJob,
)
from app.models.schemas import DocumentType, ErrorResponse, OCRRequest, OCRResponse
from app.tasks.ocr_tasks import process_ocr_job


router = APIRouter(prefix="/ocr", tags=["ocr"])
settings = get_settings()
orchestrator = OCRCoreOrchestrator()
prompt_router = DocumentPromptRouter()

ALLOWED_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png"}
ALLOWED_ZIP_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}


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


def _safe_zip_name(member_name: str) -> str | None:
    cleaned = member_name.replace("\\", "/")
    if cleaned.startswith("/") or cleaned.startswith("../") or "/../" in cleaned:
        return None
    if cleaned.endswith("/"):
        return None
    return cleaned


def _extract_zip_files(
    zip_upload: UploadFile, zip_max_bytes: int, file_max_bytes: int
) -> Tuple[List[Tuple[str, Path, int, str]], List[str]]:
    os.makedirs(settings.temp_dir, exist_ok=True)
    zip_bytes = zip_upload.file.read(zip_max_bytes + 1)
    if len(zip_bytes) > zip_max_bytes:
        raise HTTPException(status_code=413, detail="ZIP exceeds max size limit")

    try:
        zip_file = zipfile.ZipFile(BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Invalid ZIP file") from exc

    extracted: List[Tuple[str, Path, int, str]] = []
    ignored: List[str] = []
    for info in zip_file.infolist():
        safe_name = _safe_zip_name(info.filename)
        if not safe_name:
            continue
        base_name = Path(safe_name).name
        if base_name.startswith("._") or base_name.startswith("."):
            ignored.append(base_name)
            continue
        suffix = Path(safe_name).suffix.lower()
        if suffix not in ALLOWED_ZIP_EXTENSIONS:
            ignored.append(base_name)
            continue

        temp_path = Path(settings.temp_dir) / f"{uuid.uuid4().hex}{suffix}"
        with zip_file.open(info) as zipped_file, temp_path.open("wb") as temp_file:
            size_bytes = 0
            while True:
                chunk = zipped_file.read(1024 * 1024)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > file_max_bytes:
                    temp_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413, detail="Extracted file exceeds max size limit"
                    )
                temp_file.write(chunk)
        extracted.append((base_name, temp_path, size_bytes, suffix))

    return extracted, ignored


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
                "job_type": JobType.SINGLE.value,
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


@router.post("/extract-async-bulk", response_model=BulkJobCreateResponse)
def extract_text_async_bulk(
    files: List[UploadFile] = File(...),
    document_type: DocumentType = Form(DocumentType.AUTO),
    language: str = Form("pt-BR"),
    preserve_layout: bool = Form(True),
    quality_threshold: float = Form(0.8),
) -> Union[BulkJobCreateResponse, JSONResponse]:
    if not files:
        return _error_response(
            status_code=400,
            code="EMPTY_BULK_REQUEST",
            message="No files uploaded",
            details=None,
            suggestion="Upload at least one file",
        )

    zip_files = [
        upload.filename
        for upload in files
        if (upload.filename or "").lower().endswith(".zip")
    ]
    if zip_files:
        return _error_response(
            status_code=415,
            code="UNSUPPORTED_ZIP_BULK",
            message="ZIP files are not supported in this endpoint",
            details={"files": zip_files},
            suggestion="Use /api/v1/ocr/extract-async-bulk-zip",
        )

    invalid_files = [
        upload.filename
        for upload in files
        if upload.content_type not in ALLOWED_MIME_TYPES
    ]
    if invalid_files:
        return _error_response(
            status_code=415,
            code="UNSUPPORTED_DOCUMENT_TYPE",
            message="Unsupported file type",
            details={"files": invalid_files},
            suggestion="Upload PDF, JPG, or PNG files",
        )

    request = OCRRequest(
        document_type=document_type,
        language=language,
        preserve_layout=preserve_layout,
        quality_threshold=quality_threshold,
    )

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    parent_job_id = uuid.uuid4().hex
    temp_files: List[Tuple[UploadFile, Path, int]] = []

    try:
        for upload in files:
            temp_path, size_bytes = _save_upload_to_temp(upload, max_bytes)
            temp_files.append((upload, temp_path, size_bytes))

        child_jobs: List[Dict[str, Union[str, int, float, bool]]] = []
        child_statuses: List[ChildJobStatus] = []
        for upload, _, size_bytes in temp_files:
            child_job_id = uuid.uuid4().hex
            child_jobs.append(
                {
                    "job_id": child_job_id,
                    "status": JobStatus.PENDING.value,
                    "job_type": JobType.BULK_CHILD.value,
                    "parent_job_id": parent_job_id,
                    "input_meta": {
                        "original_filename": upload.filename or "",
                        "content_type": upload.content_type or "",
                        "size_bytes": size_bytes,
                        "document_type": document_type.value,
                        "language": language,
                        "preserve_layout": preserve_layout,
                        "quality_threshold": quality_threshold,
                    },
                }
            )
            child_statuses.append(
                ChildJobStatus(
                    job_id=child_job_id,
                    filename=upload.filename or "",
                    status=JobStatus.PENDING,
                )
            )

        create_bulk_jobs(
            {
                "job_id": parent_job_id,
                "status": JobStatus.PENDING.value,
                "job_type": JobType.BULK_PARENT.value,
                "input_meta": {
                    "total_files": len(temp_files),
                    "document_type": document_type.value,
                    "language": language,
                    "preserve_layout": preserve_layout,
                    "quality_threshold": quality_threshold,
                },
                "children_summary": {
                    "total": len(temp_files),
                    "pending": len(temp_files),
                    "started": 0,
                    "success": 0,
                    "failed": 0,
                },
            },
            child_jobs,
        )

        for (upload, temp_path, _), child_job in zip(temp_files, child_jobs):
            try:
                process_ocr_job.delay(
                    child_job["job_id"],
                    str(temp_path),
                    upload.content_type or "",
                    request.model_dump(),
                    parent_job_id,
                )
            except Exception as error:
                update_job(
                    child_job["job_id"],
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
                if temp_path.exists():
                    temp_path.unlink()
        update_parent_aggregate(parent_job_id)
        return BulkJobCreateResponse(
            parent_job_id=parent_job_id,
            status=JobStatus.PENDING,
            children=child_statuses,
        )
    except HTTPException:
        for _, temp_path, _ in temp_files:
            if temp_path.exists():
                temp_path.unlink()
        raise
    except Exception as error:
        for _, temp_path, _ in temp_files:
            if temp_path.exists():
                temp_path.unlink()
        return _error_response(
            status_code=500,
            code="JOB_ENQUEUE_FAILED",
            message="Failed to enqueue job",
            details={"reason": str(error)},
            suggestion="Try again later",
        )


@router.post("/extract-async-bulk-zip")
def extract_text_async_bulk_zip(
    file: UploadFile = File(...),
) -> JSONResponse:
    if not (file.filename or "").lower().endswith(".zip"):
        return _error_response(
            status_code=415,
            code="UNSUPPORTED_ZIP_TYPE",
            message="Only ZIP files are supported",
            details={"filename": file.filename, "content_type": file.content_type},
            suggestion="Upload a .zip file",
        )

    request = OCRRequest(document_type=DocumentType.AUTO)
    zip_max_bytes = settings.zip_max_upload_size_mb * 1024 * 1024
    file_max_bytes = settings.max_upload_size_mb * 1024 * 1024
    parent_job_id = uuid.uuid4().hex

    extracted_files: List[Tuple[str, Path, int, str]] = []
    ignored_files: List[str] = []
    try:
        extracted_files, ignored_files = _extract_zip_files(
            file, zip_max_bytes, file_max_bytes
        )
        if not extracted_files:
            return _error_response(
                status_code=400,
                code="EMPTY_ZIP",
                message="No supported files found in ZIP",
                details={"filename": file.filename, "ignored_files": ignored_files},
                suggestion="Include PDF/JPG/PNG files in the ZIP",
            )

        child_jobs: List[Dict[str, Union[str, int, float, bool]]] = []
        child_statuses: List[ChildJobStatus] = []
        for filename, _, size_bytes, suffix in extracted_files:
            child_job_id = uuid.uuid4().hex
            if suffix == ".pdf":
                content_type = "application/pdf"
            elif suffix in {".jpg", ".jpeg"}:
                content_type = "image/jpeg"
            else:
                content_type = f"image/{suffix.lstrip('.')}"
            child_jobs.append(
                {
                    "job_id": child_job_id,
                    "status": JobStatus.PENDING.value,
                    "job_type": JobType.BULK_CHILD.value,
                    "parent_job_id": parent_job_id,
                    "input_meta": {
                        "original_filename": filename,
                        "content_type": content_type,
                        "size_bytes": size_bytes,
                        "document_type": DocumentType.AUTO.value,
                        "language": request.language,
                        "preserve_layout": request.preserve_layout,
                        "quality_threshold": request.quality_threshold,
                    },
                }
            )
            child_statuses.append(
                ChildJobStatus(
                    job_id=child_job_id,
                    filename=filename,
                    status=JobStatus.PENDING,
                )
            )

        create_bulk_jobs(
            {
                "job_id": parent_job_id,
                "status": JobStatus.PENDING.value,
                "job_type": JobType.BULK_PARENT.value,
                "input_meta": {
                    "total_files": len(extracted_files),
                    "document_type": DocumentType.AUTO.value,
                    "language": request.language,
                    "preserve_layout": request.preserve_layout,
                    "quality_threshold": request.quality_threshold,
                },
                "children_summary": {
                    "total": len(extracted_files),
                    "pending": len(extracted_files),
                    "started": 0,
                    "success": 0,
                    "failed": 0,
                },
            },
            child_jobs,
        )

        for (filename, temp_path, _, suffix), child_job in zip(extracted_files, child_jobs):
            try:
                if suffix == ".pdf":
                    content_type = "application/pdf"
                elif suffix in {".jpg", ".jpeg"}:
                    content_type = "image/jpeg"
                else:
                    content_type = f"image/{suffix.lstrip('.')}"
                process_ocr_job.delay(
                    child_job["job_id"],
                    str(temp_path),
                    content_type,
                    request.model_dump(),
                    parent_job_id,
                )
            except Exception as error:
                update_job(
                    child_job["job_id"],
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
                if temp_path.exists():
                    temp_path.unlink()
        update_parent_aggregate(parent_job_id)
        return BulkJobCreateResponse(
            parent_job_id=parent_job_id,
            status=JobStatus.PENDING,
            children=child_statuses,
            ignored_files=ignored_files or None,
        )
    except HTTPException:
        for _, temp_path, _, _ in extracted_files:
            if temp_path.exists():
                temp_path.unlink()
        raise
    except Exception as error:
        for _, temp_path, _, _ in extracted_files:
            if temp_path.exists():
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
    if job_data.get("job_type") == JobType.BULK_PARENT.value:
        update_parent_aggregate(job_id)
        job_data = get_job(job_id) or job_data
        children_docs = get_children_jobs(job_id)
        children_status = [
            ChildJobStatus(
                job_id=child["job_id"],
                filename=child.get("input_meta", {}).get("original_filename", ""),
                status=JobStatus(child["status"]),
                result=child.get("result"),
                error=child.get("error"),
                duration_ms=child.get("duration_ms"),
            )
            for child in children_docs
        ]
        job_data = {**job_data, "children": children_status}
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
