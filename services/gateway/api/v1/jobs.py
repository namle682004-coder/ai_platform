import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Header, BackgroundTasks, Depends
from typing import Optional

from common.models.schemas import JobCreateRequest, JobStatusResponse
from common.services.job_queue import durable_job_publisher
from common.interfaces.base import IJobRepository
from common.repositories.mongo_repositories import job_repository

router = APIRouter(prefix="/v1", tags=["Async Jobs"])


def get_job_repo() -> IJobRepository:
    return job_repository


@router.post("/jobs", response_model=JobStatusResponse, status_code=202)
async def create_async_job(
    request: JobCreateRequest,
    background_tasks: BackgroundTasks,
    idempotency_key: Optional[str] = Header(None),
    repo: IJobRepository = Depends(get_job_repo),
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

    created = await repo.create_job(job_record)

    # Publish durable message to RabbitMQ in background task
    background_tasks.add_task(
        durable_job_publisher.publish_job,
        job_type=request.job_type,
        job_id=job_id,
        payload=request.model_dump(),
    )

    return JobStatusResponse(**created)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str, repo: IJobRepository = Depends(get_job_repo)):
    job = await repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(**job)


@router.get("/jobs/{job_id}/result")
async def get_job_result(job_id: str, repo: IJobRepository = Depends(get_job_repo)):
    job = await repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": job_id,
        "status": job.get("status", "completed"),
        "result_urls": [f"https://minio.internal/aip-job-artifacts/{job_id}/output.mp4"],
        "download_expires_at": "2026-08-15T15:00:00Z"
    }


@router.post("/jobs/{job_id}/cancel", status_code=200)
async def cancel_job(job_id: str, repo: IJobRepository = Depends(get_job_repo)):
    now = datetime.now(timezone.utc).isoformat()
    updated = await repo.update_job_status(job_id, "cancelled", {"updated_at": now})
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")

    return {"message": "Job cancelled successfully", "job_id": job_id}
