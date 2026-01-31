from typing import Dict, Tuple

import fitz


class PDFNativeProcessor:
    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def extract_text(self) -> Tuple[str, float, Dict[str, int]]:
        text_parts = []
        has_text = False

        with fitz.open(self.file_path) as pdf:
            for page in pdf:
                page_text = page.get_text("text")
                if page_text.strip():
                    has_text = True
                    text_parts.append(page_text)

            page_count = pdf.page_count

        text = "\n".join(text_parts).strip()
        confidence = 1.0 if has_text else 0.0
        return text, confidence, {"page_count": page_count}
