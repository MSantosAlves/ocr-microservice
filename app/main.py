from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.ocr import router as ocr_router
from app.core.config import get_settings


settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.allowed_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ocr_router, prefix=settings.api_v1_prefix)


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@app.get(f"{settings.api_v1_prefix}/info")
def api_info() -> dict:
    return {
        "name": settings.app_name,
        "environment": settings.environment,
        "version": "0.1.0",
    }
