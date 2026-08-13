import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Header
from typing import Optional
from common.models.schemas import JobCreateRequest, JobStatusResponse

router = APIRouter(prefix="/v1", tags=["Async Jobs"])
_JOBS_STORE: dict[str, dict] = {}


@router.post("/jobs", response_model=JobStatusResponse, status_code=202)
async def create_async_job(
    request: JobCreateRequest,
    idempotency_key: Optional[str] = Header(None),
):
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    now = datetime.utcnow()

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

    _JOBS_STORE[job_id] = job_record
    return JobStatusResponse(**job_record)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    if job_id not in _JOBS_STORE:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(**_JOBS_STORE[job_id])


@router.get("/jobs/{job_id}/result")
async def get_job_result(job_id: str):
    if job_id not in _JOBS_STORE:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _JOBS_STORE[job_id]
    return {
        "job_id": job_id,
        "status": job["status"],
        "result_urls": [f"https://minio.internal/aip-job-artifacts/{job_id}/output.mp4"],
        "download_expires_at": "2026-08-14T15:00:00Z"
    }


@router.post("/jobs/{job_id}/cancel", status_code=200)
async def cancel_job(job_id: str):
    if job_id not in _JOBS_STORE:
        raise HTTPException(status_code=404, detail="Job not found")

    _JOBS_STORE[job_id]["status"] = "cancelled"
    _JOBS_STORE[job_id]["updated_at"] = datetime.utcnow()
    return {"message": "Job cancelled successfully", "job_id": job_id}
