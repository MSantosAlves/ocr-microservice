from __future__ import annotations

from typing import List, Tuple

import cv2
import fitz
import numpy as np
from PIL import Image, ImageEnhance, ImageOps


def resize_max_side(image: Image.Image, max_side: int) -> Image.Image:
    if max_side <= 0:
        return image
    width, height = image.size
    max_dim = max(width, height)
    if max_dim <= max_side:
        return image
    scale = max_side / max_dim
    new_width = max(1, int(width * scale))
    new_height = max(1, int(height * scale))
    return image.resize((new_width, new_height), Image.LANCZOS)


def enhance_contrast(image: Image.Image, factor: float = 1.8) -> Image.Image:
    grayscale = ImageOps.grayscale(image)
    return ImageEnhance.Contrast(grayscale).enhance(factor)


def reduce_noise(image: Image.Image) -> Image.Image:
    image_array = np.array(image.convert("RGB"))
    denoised = cv2.fastNlMeansDenoisingColored(
        image_array, None, h=10, hColor=10, templateWindowSize=7, searchWindowSize=21
    )
    return Image.fromarray(denoised)


def binarize(image: Image.Image) -> Image.Image:
    gray = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    _, thresholded = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return Image.fromarray(thresholded)


def adaptive_binarize(image: Image.Image) -> Image.Image:
    gray = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    thresholded = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11
    )
    return Image.fromarray(thresholded)


def deskew(image: Image.Image) -> Image.Image:
    gray = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    _, thresh = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    coords = np.column_stack(np.where(thresh > 0))
    if coords.size == 0:
        return image
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    (height, width) = gray.shape
    center = (width // 2, height // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        np.array(image.convert("RGB")),
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return Image.fromarray(rotated)


def pdf_to_images(
    file_path: str, dpi: int = 200, max_pages: int | None = None
) -> Tuple[List[Image.Image], int]:
    images: List[Image.Image] = []
    with fitz.open(file_path) as pdf:
        page_count = pdf.page_count
        for index, page in enumerate(pdf):
            if max_pages is not None and index >= max_pages:
                break
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            mode = "RGB" if pix.n < 4 else "RGBA"
            page_image = Image.frombytes(
                mode, (pix.width, pix.height), pix.samples
            ).convert("RGB")
            images.append(page_image)
    return images, page_count
