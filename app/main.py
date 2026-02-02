import logging

import pymongo
import redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.ocr import router as ocr_router
from app.core.config import get_settings


settings = get_settings()
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.allowed_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ocr_router, prefix=settings.api_v1_prefix)


@app.on_event("startup")
def verify_dependencies() -> None:
    try:
        mongo_client = pymongo.MongoClient(
            settings.mongodb_uri, serverSelectionTimeoutMS=3000
        )
        mongo_client.admin.command("ping")
        logger.info("MongoDB connection OK")
    except Exception as exc:
        logger.error("MongoDB connection failed: %s", exc)
        raise RuntimeError("MongoDB connection failed") from exc

    try:
        redis_client = redis.Redis.from_url(
            settings.redis_broker_url, socket_connect_timeout=3
        )
        redis_client.ping()
        logger.info("Redis connection OK")
    except Exception as exc:
        logger.error("Redis connection failed: %s", exc)
        raise RuntimeError("Redis connection failed") from exc


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
