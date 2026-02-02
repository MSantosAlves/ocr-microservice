from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional

from pymongo import MongoClient, ReturnDocument

from app.core.config import get_settings
from app.models.job import JobStatus, JobType


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


def create_bulk_jobs(
    parent_job: Dict[str, Any], child_jobs: Iterable[Dict[str, Any]]
) -> Dict[str, Any]:
    now = _utcnow()
    parent_job.setdefault("created_at", now)
    parent_job.setdefault("updated_at", now)
    parent_job.setdefault("job_type", JobType.BULK_PARENT.value)
    parent_job.setdefault(
        "children_summary",
        {
            "total": 0,
            "pending": 0,
            "started": 0,
            "success": 0,
            "failed": 0,
        },
    )

    prepared_children: List[Dict[str, Any]] = []
    for child_job in child_jobs:
        child_job.setdefault("created_at", now)
        child_job.setdefault("updated_at", now)
        child_job.setdefault("job_type", JobType.BULK_CHILD.value)
        prepared_children.append(child_job)

    collection = get_collection()
    collection.insert_one(parent_job)
    if prepared_children:
        collection.insert_many(prepared_children)
    return parent_job


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


def get_children_jobs(parent_job_id: str) -> List[Dict[str, Any]]:
    collection = get_collection()
    cursor = collection.find({"parent_job_id": parent_job_id})
    return [_strip_mongo_id(document) for document in cursor]


def update_parent_aggregate(parent_job_id: str) -> Optional[Dict[str, Any]]:
    children = get_children_jobs(parent_job_id)
    if not children:
        return update_job(
            parent_job_id,
            {
                "status": JobStatus.PENDING.value,
                "children_summary": {
                    "total": 0,
                    "pending": 0,
                    "started": 0,
                    "success": 0,
                    "failed": 0,
                },
            },
        )

    total = len(children)
    pending = sum(1 for child in children if child.get("status") == JobStatus.PENDING.value)
    started = sum(1 for child in children if child.get("status") == JobStatus.STARTED.value)
    success = sum(1 for child in children if child.get("status") == JobStatus.SUCCESS.value)
    failed = sum(1 for child in children if child.get("status") == JobStatus.FAILED.value)

    finished = success + failed
    if success == total:
        status = JobStatus.SUCCESS.value
    elif failed == total:
        status = JobStatus.FAILED.value
    elif finished == total:
        status = JobStatus.PARTIAL_SUCCESS.value
    elif started > 0 or success > 0 or failed > 0:
        status = JobStatus.STARTED.value
    else:
        status = JobStatus.PENDING.value

    duration_ms = None
    if finished == total:
        durations = [
            child.get("duration_ms")
            for child in children
            if isinstance(child.get("duration_ms"), int)
        ]
        if durations:
            duration_ms = max(durations)

    return update_job(
        parent_job_id,
        {
            "status": status,
            "children_summary": {
                "total": total,
                "pending": pending,
                "started": started,
                "success": success,
                "failed": failed,
            },
            "duration_ms": duration_ms,
        },
    )
