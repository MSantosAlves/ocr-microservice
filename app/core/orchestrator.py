import time
from typing import Optional
from pathlib import Path

from PIL import Image

from app.core.classifier import DocumentClassifier
from app.core.config import get_settings
from app.core.prompt_router import DocumentPromptRouter
from app.models.schemas import DocumentType, OCRRequest, OCRResponse
import logging

from app.processors.handwritten_anthropic import AnthropicHandwritingProcessor
from app.processors.handwritten_openai import OpenAIHandwritingProcessor
from app.processors.pdf_native import PDFNativeProcessor
from app.utils.image_processing import pdf_to_images


class OCRProcessingError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        details: Optional[dict] = None,
        suggestion: Optional[str] = None,
        status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.suggestion = suggestion
        self.status_code = status_code


class OCRCoreOrchestrator:
    BLOCKED_PROMPT_CATEGORIES = {"malicious_content", "non_related_content"}

    def __init__(self) -> None:
        self.classifier = DocumentClassifier()
        self.settings = get_settings()
        self.logger = logging.getLogger(__name__)
        self.prompt_router = DocumentPromptRouter()

    def process_document(
        self, file_path: str, content_type: str, request: OCRRequest
    ) -> OCRResponse:
        start_time = time.monotonic()

        if content_type == "application/pdf":
            return self._process_pdf(file_path, request, start_time)
        if content_type in {"image/jpeg", "image/png"}:
            return self._process_image(file_path, request, start_time)

        raise OCRProcessingError(
            code="UNSUPPORTED_DOCUMENT_TYPE",
            message="Unsupported document type for processing",
            details={"content_type": content_type},
            suggestion="Upload a PDF, JPG, or PNG document",
            status_code=415,
        )

    def _process_pdf(
        self, file_path: str, request: OCRRequest, start_time: float
    ) -> OCRResponse:
        if request.document_type not in (
            DocumentType.AUTO,
            DocumentType.PDF_NATIVE,
            DocumentType.PRINTED,
            DocumentType.MIXED,
        ):
            raise OCRProcessingError(
                code="UNSUPPORTED_DOCUMENT_TYPE",
                message="Document type not supported for PDF processing",
                details={"document_type": request.document_type.value},
                suggestion="Use document_type=pdf_native, printed, mixed, or auto",
                status_code=422,
            )

        classifier_metadata: dict = {}
        document_type = request.document_type
        if request.document_type == DocumentType.AUTO:
            document_type, classifier_metadata = self.classifier.classify(
                file_path, "application/pdf"
            )

        if document_type == DocumentType.PDF_NATIVE:
            processor = PDFNativeProcessor(file_path)
            text, confidence, metadata = processor.extract_text()
            if text:
                processing_time_ms = int((time.monotonic() - start_time) * 1000)
                return OCRResponse(
                    text=text,
                    confidence=confidence,
                    document_type=DocumentType.PDF_NATIVE,
                    processor_used="pymupdf",
                    processing_time_ms=processing_time_ms,
                    metadata={
                        **metadata,
                        **classifier_metadata,
                        "language_detected": request.language,
                        "layout_preserved": request.preserve_layout,
                    },
                )
            if request.document_type == DocumentType.PDF_NATIVE:
                raise OCRProcessingError(
                    code="OCR_FAILED",
                    message="No native text found in PDF",
                    details={"confidence": confidence, "reason": "no_native_text"},
                    suggestion="Use document_type=printed for scanned PDFs",
                    status_code=422,
                )

        return self._process_ai_pdf(file_path, request, start_time, document_type)

    def _process_image(
        self, file_path: str, request: OCRRequest, start_time: float
    ) -> OCRResponse:
        if request.document_type not in (
            DocumentType.AUTO,
            DocumentType.PRINTED,
            DocumentType.MIXED,
            DocumentType.HANDWRITTEN,
        ):
            raise OCRProcessingError(
                code="UNSUPPORTED_DOCUMENT_TYPE",
                message="Document type not supported for image processing",
                details={"document_type": request.document_type.value},
                suggestion="Use document_type=printed or auto for images",
                status_code=422,
            )

        if request.document_type == DocumentType.HANDWRITTEN:
            return self._process_handwritten_image(file_path, request, start_time)

        return self._process_ai_image(file_path, request, start_time)

    def _process_handwritten_image(
        self, file_path: str, request: OCRRequest, start_time: float
    ) -> OCRResponse:
        warnings: list[str] = []
        prompt_name = "handwritten_general.md"
        openai_processor = OpenAIHandwritingProcessor()
        anthropic_processor = AnthropicHandwritingProcessor()

        with Image.open(file_path) as image:
            try:
                text, confidence, metadata = openai_processor.extract_text(
                    image, prompt_name=prompt_name
                )
                processor_used = "openai"
            except Exception as error:
                warnings.append(f"openai_failed: {error}")
                self.logger.warning("OpenAI handwriting failed", exc_info=error)
                text, confidence, metadata = "", 0.0, {}
                processor_used = "openai"

            if not text:
                try:
                    text, confidence, metadata = anthropic_processor.extract_text(
                        image, prompt_name=prompt_name
                    )
                    processor_used = "anthropic"
                except Exception as error:
                    warnings.append(f"anthropic_failed: {error}")
                    self.logger.warning("Anthropic handwriting failed", exc_info=error)
                    text, confidence, metadata = "", 0.0, {}
                    processor_used = "anthropic"

        processing_time_ms = int((time.monotonic() - start_time) * 1000)
        if not text:
            warnings.append("no_text_detected")
        self._log_ai_extract(processor_used, metadata)

        return OCRResponse(
            text=text,
            confidence=confidence,
            document_type=DocumentType.HANDWRITTEN,
            processor_used=processor_used,
            processing_time_ms=processing_time_ms,
            warnings=warnings,
            metadata={
                **metadata,
                "prompt_name": prompt_name,
                "language_detected": request.language,
                "layout_preserved": request.preserve_layout,
            },
        )

    def _process_ai_pdf(
        self,
        file_path: str,
        request: OCRRequest,
        start_time: float,
        document_type: DocumentType,
    ) -> OCRResponse:
        images, page_count = pdf_to_images(file_path, dpi=200)
        if not images:
            raise OCRProcessingError(
                code="OCR_FAILED",
                message="Failed to render PDF pages",
                details={"reason": "no_pages_rendered"},
                suggestion="Verify the PDF file",
                status_code=422,
            )

        # Usar classificação multi-página para PDFs com múltiplas páginas
        if len(images) > 1:
            prompt_name, routing_metadata = self.prompt_router.classify_multipage(images)
        else:
            prompt_name, routing_metadata = self.prompt_router.classify(images[0])

        self._raise_if_blocked_category(file_path, routing_metadata)
        
        text, processor_used, warnings, usage = self._run_ai_pages(images, prompt_name)
        processing_time_ms = int((time.monotonic() - start_time) * 1000)

        return OCRResponse(
            text=text,
            confidence=0.0,
            document_type=document_type,
            processor_used=processor_used,
            prompt_used=prompt_name,
            processing_time_ms=processing_time_ms,
            warnings=warnings,
            metadata={
                "page_count": page_count,
                "prompt_name": prompt_name,
                "prompt_category": routing_metadata.get("category"),
                "prompt_confidence": routing_metadata.get("confidence"),
                "prompt_reasoning": routing_metadata.get("reasoning"),
                "router_model": routing_metadata.get("model"),
                "router_input_tokens": routing_metadata.get("input_tokens"),
                "router_output_tokens": routing_metadata.get("output_tokens"),
                "router_classification_time_ms": routing_metadata.get("classification_time_ms"),
                "router_attempts": routing_metadata.get("attempts"),
                "is_fallback_classification": routing_metadata.get("is_fallback", False),
                **usage,
                "language_detected": request.language,
                "layout_preserved": request.preserve_layout,
            },
        )

    def _process_ai_image(
        self, file_path: str, request: OCRRequest, start_time: float
    ) -> OCRResponse:
        with Image.open(file_path) as image:
            prompt_name, routing_metadata = self.prompt_router.classify(image)
            self._raise_if_blocked_category(file_path, routing_metadata)
            text, processor_used, warnings, usage = self._run_ai_pages([image], prompt_name)

        processing_time_ms = int((time.monotonic() - start_time) * 1000)
        return OCRResponse(
            text=text,
            confidence=0.0,
            document_type=request.document_type,
            processor_used=processor_used,
            prompt_used=prompt_name,
            processing_time_ms=processing_time_ms,
            warnings=warnings,
            metadata={
                "prompt_name": prompt_name,
                "prompt_category": routing_metadata.get("category"),
                "prompt_confidence": routing_metadata.get("confidence"),
                "prompt_reasoning": routing_metadata.get("reasoning"),
                "router_model": routing_metadata.get("model"),
                "router_input_tokens": routing_metadata.get("input_tokens"),
                "router_output_tokens": routing_metadata.get("output_tokens"),
                "router_classification_time_ms": routing_metadata.get("classification_time_ms"),
                "router_attempts": routing_metadata.get("attempts"),
                "is_fallback_classification": routing_metadata.get("is_fallback", False),
                **usage,
                "language_detected": request.language,
                "layout_preserved": request.preserve_layout,
            },
        )

    def _raise_if_blocked_category(self, file_path: str, routing_metadata: dict) -> None:
        category = str(routing_metadata.get("category") or "").strip().lower()
        if category not in self.BLOCKED_PROMPT_CATEGORIES:
            return

        deleted = self._delete_document_file(file_path)
        status_code = 403 if category == "malicious_content" else 422

        raise OCRProcessingError(
            code="DOCUMENT_REJECTED_BY_CLASSIFIER",
            message="Document rejected by content classifier",
            details={
                "blocked_category": category,
                "classifier_confidence": routing_metadata.get("confidence"),
                "classifier_reasoning": routing_metadata.get("reasoning"),
                "document_deleted": deleted,
            },
            suggestion="Upload a valid educational document.",
            status_code=status_code,
        )

    def _delete_document_file(self, file_path: str) -> bool:
        path = Path(file_path)
        if not path.exists():
            return False
        try:
            path.unlink()
            return True
        except Exception as error:
            self.logger.warning("Failed to delete blocked document: %s", error)
            return False

    def _run_ai_pages(
        self, images: list[Image.Image], prompt_name: str
    ) -> tuple[str, str, list[str], dict]:
        warnings: list[str] = []
        texts: list[str] = []
        processor_used = "openai"
        usage = {
            "openai_input_tokens": 0,
            "openai_output_tokens": 0,
            "anthropic_input_tokens": 0,
            "anthropic_output_tokens": 0,
        }

        openai_processor = OpenAIHandwritingProcessor()
        anthropic_processor = AnthropicHandwritingProcessor()

        for image in images:
            try:
                text, _, metadata = openai_processor.extract_text(
                    image, prompt_name=prompt_name
                )
                texts.append(text)
                usage["openai_input_tokens"] += metadata.get("input_tokens") or 0
                usage["openai_output_tokens"] += metadata.get("output_tokens") or 0
            except Exception as error:
                warnings.append(f"openai_failed: {error}")
                self.logger.warning("OpenAI extraction failed", exc_info=error)
                try:
                    text, _, metadata = anthropic_processor.extract_text(
                        image, prompt_name=prompt_name
                    )
                    texts.append(text)
                    processor_used = "openai+anthropic"
                    usage["anthropic_input_tokens"] += metadata.get("input_tokens") or 0
                    usage["anthropic_output_tokens"] += metadata.get("output_tokens") or 0
                except Exception as fallback_error:
                    warnings.append(f"anthropic_failed: {fallback_error}")
                    self.logger.warning(
                        "Anthropic extraction failed", exc_info=fallback_error
                    )
                    texts.append("")
                    processor_used = "openai+anthropic"

        combined_text = "\n\n".join(text for text in texts if text).strip()
        if not combined_text:
            warnings.append("no_text_detected")

        print(
            "ai_extract "
            f"processor={processor_used} "
            f"openai_input_tokens={usage['openai_input_tokens']} "
            f"openai_output_tokens={usage['openai_output_tokens']} "
            f"anthropic_input_tokens={usage['anthropic_input_tokens']} "
            f"anthropic_output_tokens={usage['anthropic_output_tokens']} "
        )

        return combined_text, processor_used, warnings, usage

    def _log_ai_extract(self, processor_used: str, metadata: dict) -> None:
        openai_input = metadata.get("input_tokens") if processor_used == "openai" else 0
        openai_output = metadata.get("output_tokens") if processor_used == "openai" else 0
        anthropic_input = (
            metadata.get("input_tokens") if processor_used == "anthropic" else 0
        )
        anthropic_output = (
            metadata.get("output_tokens") if processor_used == "anthropic" else 0
        )
