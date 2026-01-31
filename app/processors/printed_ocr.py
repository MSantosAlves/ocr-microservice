from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
from paddleocr import PaddleOCR
from PIL import Image

from app.utils.image_processing import (
    adaptive_binarize,
    binarize,
    deskew,
    enhance_contrast,
    reduce_noise,
    resize_max_side,
)


def _normalize_language(language: str) -> str:
    language = (language or "").strip().lower()
    if language in {"pt-br", "pt_br", "pt"}:
        return "pt"
    if language in {"en-us", "en_us", "en"}:
        return "en"
    if "-" in language:
        return language.split("-", 1)[0]
    if "_" in language:
        return language.split("_", 1)[0]
    return language or "pt"


class PrintedOCRProcessor:
    def __init__(
        self, language: str = "pt", preprocess: bool = True, max_side: int = 2000
    ) -> None:
        self.language = _normalize_language(language)
        self.preprocess = preprocess
        self.max_side = max_side
        self.ocr = PaddleOCR(use_angle_cls=True, lang=self.language)

    def extract_text(self, image: Image.Image) -> Tuple[str, float, Dict[str, int]]:
        base = resize_max_side(image, self.max_side)
        passes = [base]
        if self.preprocess:
            passes.append(enhance_contrast(base))
            passes.append(deskew(reduce_noise(base)))
            passes.append(binarize(base))
            passes.append(adaptive_binarize(base))

        best_text = ""
        best_confidence = 0.0
        best_line_count = 0

        for candidate in passes:
            text, confidence, line_count = self._run_ocr(candidate)
            if line_count > best_line_count or (
                line_count == best_line_count and confidence > best_confidence
            ):
                best_text = text
                best_confidence = confidence
                best_line_count = line_count

        return best_text, best_confidence, {"line_count": best_line_count}

    def _run_ocr(self, image: Image.Image) -> Tuple[str, float, int]:
        image_array = np.array(image.convert("RGB"))
        result = self.ocr.ocr(image_array)

        lines: List[str] = []
        confidences: List[float] = []

        for page in result or []:
            for item in page or []:
                text = None
                score = None

                if isinstance(item, dict):
                    text = item.get("text") or item.get("rec_text")
                    score = item.get("score") or item.get("rec_score")
                elif isinstance(item, (list, tuple)):
                    if len(item) >= 2 and isinstance(item[1], (list, tuple)):
                        text = item[1][0] if len(item[1]) > 0 else None
                        score = item[1][1] if len(item[1]) > 1 else None
                    elif len(item) >= 2 and isinstance(item[-2], str):
                        text = item[-2]
                        score = item[-1] if len(item) >= 1 else None

                if text:
                    lines.append(text)
                    if isinstance(score, (int, float)):
                        confidences.append(float(score))

        text = "\n".join(lines).strip()
        confidence = float(sum(confidences) / len(confidences)) if confidences else 0.0
        return text, confidence, len(lines)
