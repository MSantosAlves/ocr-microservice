from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, Optional

from pymongo import MongoClient, ReturnDocument

from app.core.config import get_settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@lru_cache()
def get_mongo_client() -> MongoClient:
    settings = get_settings()
    return MongoClient(settings.mongodb_uri)


def get_collection():
    settings = get_settings()
    client = get_mongo_client()
    return client[settings.mongodb_db][settings.mongodb_collection]


def _strip_mongo_id(document: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not document:
        return None
    document.pop("_id", None)
    return document


def create_job(job: Dict[str, Any]) -> Dict[str, Any]:
    now = _utcnow()
    job.setdefault("created_at", now)
    job.setdefault("updated_at", now)
    collection = get_collection()
    collection.insert_one(job)
    return job


def update_job(job_id: str, update: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    update = {**update, "updated_at": _utcnow()}
    collection = get_collection()
    document = collection.find_one_and_update(
        {"job_id": job_id},
        {"$set": update},
        return_document=ReturnDocument.AFTER,
    )
    return _strip_mongo_id(document)


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    collection = get_collection()
    document = collection.find_one({"job_id": job_id})
    return _strip_mongo_id(document)
