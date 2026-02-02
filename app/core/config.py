from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "OCR Microservice"
    api_v1_prefix: str = "/api/v1"
    environment: str = "development"
    log_level: str = "INFO"
    allowed_origins: str = "*"
    max_upload_size_mb: int = 20
    temp_dir: str = "/tmp/ocr-service"
    openai_api_key: Optional[str] = None
    openai_model: Optional[str] = None
    openai_timeout_seconds: int = 60
    openai_max_retries: int = 3
    anthropic_api_key: Optional[str] = None
    anthropic_model: Optional[str] = None
    anthropic_classifier_model: Optional[str] = None
    anthropic_timeout_seconds: int = 60
    anthropic_max_retries: int = 3
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "ocr_service"
    mongodb_collection: str = "ocr_jobs"
    redis_broker_url: str = "redis://localhost:6379/0"
    redis_backend_url: str = "redis://localhost:6379/1"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
