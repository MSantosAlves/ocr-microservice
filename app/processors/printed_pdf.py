from __future__ import annotations

from typing import Dict, List, Tuple

from app.processors.printed_ocr import PrintedOCRProcessor
from app.utils.image_processing import pdf_to_images


class PrintedPDFProcessor:
    def __init__(
        self,
        file_path: str,
        language: str = "pt",
        preprocess: bool = True,
        max_side: int = 2000,
        dpi: int = 200,
    ) -> None:
        self.file_path = file_path
        self.dpi = dpi
        self.ocr = PrintedOCRProcessor(
            language=language, preprocess=preprocess, max_side=max_side
        )

    def extract_text(self) -> Tuple[str, float, Dict[str, int]]:
        images, page_count = pdf_to_images(self.file_path, dpi=self.dpi)
        page_texts: List[str] = []
        confidences: List[float] = []
        line_counts: List[int] = []

        for image in images:
            text, confidence, metadata = self.ocr.extract_text(image)
            page_texts.append(text)
            confidences.append(confidence)
            line_counts.append(int(metadata.get("line_count", 0)))

        total_lines = sum(line_counts)
        if total_lines > 0:
            weighted_confidence = sum(
                conf * lines for conf, lines in zip(confidences, line_counts)
            ) / total_lines
        else:
            weighted_confidence = 0.0

        combined_text = "\n".join(text for text in page_texts if text).strip()
        return (
            combined_text,
            float(weighted_confidence),
            {"page_count": page_count, "line_count": total_lines},
        )
