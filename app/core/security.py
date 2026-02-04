from hmac import compare_digest

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


def verify_ocr_api_key(x_api_key: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.ocr_api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OCR API key not configured",
        )
    if not x_api_key or not compare_digest(x_api_key, settings.ocr_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid OCR API key",
        )
