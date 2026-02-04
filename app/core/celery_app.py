from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "ocr_service",
    broker=settings.redis_broker_url,
    backend=settings.redis_backend_url,
    include=["app.tasks.ocr_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    worker_concurrency=settings.celery_worker_concurrency,
)
