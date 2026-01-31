from __future__ import annotations

from typing import List, Tuple

import cv2
import numpy as np
from PIL import Image


class LayoutAnalyzer:
    def __init__(self, min_region_area: int = 500) -> None:
        self.min_region_area = min_region_area

    def detect_regions(self, image: Image.Image) -> List[Tuple[int, int, int, int]]:
        gray = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 5))
        merged = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)

        contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        regions: List[Tuple[int, int, int, int]] = []

        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w * h < self.min_region_area:
                continue
            regions.append((x, y, w, h))

        regions.sort(key=lambda box: (box[1], box[0]))
        return regions
