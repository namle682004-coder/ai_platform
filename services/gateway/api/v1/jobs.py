import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Header, BackgroundTasks
from typing import Optional

from common.models.schemas import JobCreateRequest, JobStatusResponse
from common.services.job_queue import durable_job_publisher
from common.database.mongodb import mongo_manager

router = APIRouter(prefix="/v1", tags=["Async Jobs"])
_JOBS_MEMORY_CACHE: dict[str, dict] = {}


@router.post("/jobs", response_model=JobStatusResponse, status_code=202)
async def create_async_job(
    request: JobCreateRequest,
    background_tasks: BackgroundTasks,
    idempotency_key: Optional[str] = Header(None),
):
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    job_record = {
        "job_id": job_id,
        "job_type": request.job_type,
        "alias_name": request.alias_name,
        "status": "queued",
        "progress": 0,
        "error_message": None,
        "result_urls": None,
        "created_at": now,
        "updated_at": now,
    }

    db = mongo_manager.get_database()
    if db is not None:
        try:
            await db.jobs.insert_one(job_record)
        except Exception:
            pass

    _JOBS_MEMORY_CACHE[job_id] = job_record

    # Publish durable message to RabbitMQ in background task
    background_tasks.add_task(
        durable_job_publisher.publish_job,
        job_type=request.job_type,
        job_id=job_id,
        payload=request.model_dump(),
    )

    return JobStatusResponse(**job_record)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    db = mongo_manager.get_database()
    if db is not None:
        try:
            doc = await db.jobs.find_one({"job_id": job_id}, {"_id": 0})
            if doc:
                return JobStatusResponse(**doc)
        except Exception:
            pass

    if job_id in _JOBS_MEMORY_CACHE:
        return JobStatusResponse(**_JOBS_MEMORY_CACHE[job_id])

    raise HTTPException(status_code=404, detail="Job not found")


@router.get("/jobs/{job_id}/result")
async def get_job_result(job_id: str):
    db = mongo_manager.get_database()
    if db is not None:
        try:
            doc = await db.jobs.find_one({"job_id": job_id}, {"_id": 0})
            if doc:
                return {
                    "job_id": job_id,
                    "status": doc.get("status", "completed"),
                    "result_urls": [f"https://minio.internal/aip-job-artifacts/{job_id}/output.mp4"],
                    "download_expires_at": "2026-08-15T15:00:00Z"
                }
        except Exception:
            pass

    if job_id in _JOBS_MEMORY_CACHE:
        job = _JOBS_MEMORY_CACHE[job_id]
        return {
            "job_id": job_id,
            "status": job["status"],
            "result_urls": [f"https://minio.internal/aip-job-artifacts/{job_id}/output.mp4"],
            "download_expires_at": "2026-08-15T15:00:00Z"
        }

    raise HTTPException(status_code=404, detail="Job not found")


@router.post("/jobs/{job_id}/cancel", status_code=200)
async def cancel_job(job_id: str):
    now = datetime.now(timezone.utc).isoformat()
    db = mongo_manager.get_database()
    if db is not None:
        try:
            await db.jobs.update_one(
                {"job_id": job_id},
                {"$set": {"status": "cancelled", "updated_at": now}}
            )
        except Exception:
            pass

    if job_id in _JOBS_MEMORY_CACHE:
        _JOBS_MEMORY_CACHE[job_id]["status"] = "cancelled"
        _JOBS_MEMORY_CACHE[job_id]["updated_at"] = now

    return {"message": "Job cancelled successfully", "job_id": job_id}
