import logging
from pathlib import Path
from time import perf_counter
from typing import Any, Dict

from app.core.celery_app import celery_app
from app.core.db import update_job
from app.core.orchestrator import OCRCoreOrchestrator, OCRProcessingError
from app.models.job import JobStatus
from app.models.schemas import ErrorDetail, OCRRequest

logger = logging.getLogger(__name__)
orchestrator = OCRCoreOrchestrator()


@celery_app.task(name="ocr.process_job")
def process_ocr_job(
    job_id: str,
    file_path: str,
    content_type: str,
    request_data: Dict[str, Any],
) -> None:
    start_time = perf_counter()
    update_job(job_id, {"status": JobStatus.STARTED.value})

    temp_path = Path(file_path)
    try:
        request = OCRRequest(**request_data)
        response = orchestrator.process_document(str(temp_path), content_type, request)
        duration_ms = int((perf_counter() - start_time) * 1000)
        update_job(
            job_id,
            {
                "status": JobStatus.SUCCESS.value,
                "result": response.model_dump(),
                "duration_ms": duration_ms,
            },
        )
        logger.info("job %s completed in %sms", job_id, duration_ms)
    except OCRProcessingError as error:
        duration_ms = int((perf_counter() - start_time) * 1000)
        error_detail = ErrorDetail(
            code=error.code,
            message=error.message,
            details=error.details,
            suggestion=error.suggestion,
        )
        update_job(
            job_id,
            {
                "status": JobStatus.FAILED.value,
                "error": error_detail.model_dump(),
                "duration_ms": duration_ms,
            },
        )
        logger.warning("job %s failed: %s", job_id, error.message)
    except Exception as error:
        duration_ms = int((perf_counter() - start_time) * 1000)
        error_detail = ErrorDetail(
            code="OCR_FAILED",
            message="Failed to extract text",
            details={"reason": str(error)},
            suggestion="Try again later",
        )
        update_job(
            job_id,
            {
                "status": JobStatus.FAILED.value,
                "error": error_detail.model_dump(),
                "duration_ms": duration_ms,
            },
        )
        logger.exception("job %s crashed", job_id)
    finally:
        if temp_path.exists():
            temp_path.unlink()
