from __future__ import annotations

from typing import Dict, Tuple

import cv2
import fitz
import numpy as np
from PIL import Image

from app.models.schemas import DocumentType
from app.utils.image_processing import pdf_to_images


class DocumentClassifier:
    def __init__(self, blur_threshold: float = 120.0) -> None:
        self.blur_threshold = blur_threshold

    def classify(self, file_path: str, content_type: str) -> Tuple[DocumentType, Dict[str, object]]:
        metadata: Dict[str, object] = {}

        if content_type == "application/pdf":
            has_native_text = self._pdf_has_native_text(file_path)
            metadata["native_text_detected"] = has_native_text
            if has_native_text:
                return DocumentType.PDF_NATIVE, metadata

            quality_score, quality_label = self._pdf_quality(file_path)
            metadata["quality_score"] = quality_score
            metadata["quality_label"] = quality_label
            return DocumentType.PRINTED, metadata

        if content_type in {"image/jpeg", "image/png"}:
            quality_score, quality_label = self._image_quality(Image.open(file_path))
            metadata["quality_score"] = quality_score
            metadata["quality_label"] = quality_label
            return DocumentType.PRINTED, metadata

        return DocumentType.AUTO, metadata

    def _pdf_has_native_text(self, file_path: str, max_pages: int = 2) -> bool:
        with fitz.open(file_path) as pdf:
            for index, page in enumerate(pdf):
                if index >= max_pages:
                    break
                if page.get_text("text").strip():
                    return True
        return False

    def _image_quality(self, image: Image.Image) -> Tuple[float, str]:
        gray = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
        score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        label = "low" if score < self.blur_threshold else "ok"
        return score, label

    def _pdf_quality(self, file_path: str) -> Tuple[float, str]:
        images, _ = pdf_to_images(file_path, dpi=150, max_pages=1)
        if not images:
            return 0.0, "low"
        return self._image_quality(images[0])
