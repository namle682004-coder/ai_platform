import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Header, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
from typing import Optional

from common.models.schemas import JobCreateRequest, JobStatusResponse, AIPError, AIPErrorResponse
from common.interfaces.base import IJobRepository
from common.repositories.mongo_repositories import job_repository

router = APIRouter(prefix="/v1", tags=["Async Jobs"])
logger = logging.getLogger("aip-gateway.jobs")


def get_job_repo() -> IJobRepository:
    return job_repository


@router.post("/jobs", response_model=JobStatusResponse, status_code=202)
async def create_async_job(
    http_request: Request,
    request: JobCreateRequest,
    background_tasks: BackgroundTasks,
    idempotency_key: Optional[str] = Header(None),
    repo: IJobRepository = Depends(get_job_repo),
):
    tenant_id = (
        getattr(http_request.state, "tenant_id", None)
        or http_request.headers.get("X-Tenant-ID")
        or "TENANT_RETAIL_BANK"
    )
    if tenant_id in ("TENANT_DEFAULT", "TENANT_AUTOMATION_TEST"):
        tenant_id = "TENANT_RETAIL_BANK"

    # 1. Enforce Mandatory Idempotency-Key (SRS Section 5.1)
    effective_idemp_key = idempotency_key or http_request.headers.get("x-idempotency-key") or http_request.headers.get("Idempotency-Key")
    if not effective_idemp_key:
        request_id = http_request.headers.get("X-Request-ID") or getattr(http_request.state, "request_id", "req_idemp_missing")
        return JSONResponse(
            status_code=400,
            content=AIPErrorResponse(
                error=AIPError(
                    type="invalid_request_error",
                    code="validation_failed",
                    message="Header 'Idempotency-Key' is required for POST /v1/jobs to guarantee idempotent job creation.",
                    request_id=request_id,
                    retryable=False,
                )
            ).model_dump(),
        )
    idempotency_key = effective_idemp_key

    # 2. SSRF NetGuard Validation for Webhook URL
    if request.webhook_url:
        from common.security.netguard import is_safe_public_url
        is_safe, error_reason = await is_safe_public_url(request.webhook_url)
        if not is_safe:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid webhook_url (SSRF Protection): {error_reason}",
            )

    # Check cached response (Redis-backed, 24h window)
    from src.jobs.idempotency import idempotency_service
    cached_resp = await idempotency_service.get_cached_response(tenant_id, idempotency_key)
    if cached_resp and cached_resp.get("status") != "in_progress":
        logger.info("Returning cached response for idempotency_key=%s", idempotency_key)
        return JobStatusResponse(**cached_resp)

    claimed = await idempotency_service.claim(tenant_id, idempotency_key)
    if claimed is None:
        return JSONResponse(
            status_code=503,
            content={"detail": "Idempotency store unavailable; job was not created"},
        )
    if claimed is False:
        cached_resp = await idempotency_service.get_cached_response(tenant_id, idempotency_key)
        if cached_resp and cached_resp.get("status") != "in_progress":
            return JobStatusResponse(**cached_resp)
        return JSONResponse(
            status_code=409,
            content={"detail": "Idempotency-Key is already being processed"},
        )

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    job_record = {
        "job_id": job_id,
        "tenant_id": tenant_id,
        "job_type": request.job_type,
        "alias_name": request.alias_name,
        "status": "queued",
        "progress": 0,
        "error_message": None,
        "result_urls": None,
        "webhook_url": request.webhook_url,
        "created_at": now,
        "updated_at": now,
    }

    created = await repo.create_job(job_record)

    # Cache created job for idempotency key
    if idempotency_key:
        from src.jobs.idempotency import idempotency_service
        await idempotency_service.save_response(tenant_id, idempotency_key, created)

    # Extract optional priority from header (high, normal, batch)
    req_priority = http_request.headers.get("X-Priority", "normal").lower()
    if req_priority not in ("high", "normal", "batch"):
        req_priority = "normal"

    # Publish task via the shared TaskPublisher (Connection A, Channel 1)
    # No fallback connection — reuse app.state.task_publisher to avoid 3rd TCP connection.
    # If broker is down, job stays in 'queued' state in DB and will be retried by reconciler.
    async def _dispatch_job():
        pub = getattr(http_request.app.state, "task_publisher", None)
        try:
            if pub is None:
                from src.publisher.task_publisher import TaskPublisher
                from src.configs.settings import gateway_settings
                pub = TaskPublisher(gateway_settings.rabbitmq_url)
                await pub.connect()
                http_request.app.state.task_publisher = pub

            await pub.publish_task(
                task_id=job_id,
                tenant_id=tenant_id,
                task_type=request.job_type,
                alias_name=request.alias_name,
                priority=req_priority,
                payload=request.model_dump(),
            )
        except Exception as exc:
            logger.error(
                "Failed to dispatch job %s to RabbitMQ: %s — job stays 'queued' in DB",
                job_id,
                exc,
            )

    background_tasks.add_task(_dispatch_job)

    return JobStatusResponse(**created)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str, repo: IJobRepository = Depends(get_job_repo)):
    job = await repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(**job)


@router.get("/jobs/{job_id}/result")
async def get_job_result(job_id: str, repo: IJobRepository = Depends(get_job_repo)):
    """
    SRS Section 3.3: Client retrieves result via pre-signed URL with default 24h TTL.
    """
    from datetime import timedelta
    from common.storage import minio_storage

    job = await repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    now_dt = datetime.now(timezone.utc)
    expires_dt = now_dt + timedelta(hours=24)
    expires_at = expires_dt.isoformat()

    existing_urls = job.get("result_urls")
    presigned_urls = []

    if existing_urls and len(existing_urls) > 0:
        for u in existing_urls:
            if "aip-job-artifacts/" in u:
                obj_key = u.split("aip-job-artifacts/")[-1].split("?")[0]
                presigned = minio_storage.generate_presigned_download_url(
                    bucket="aip-job-artifacts",
                    object_name=obj_key,
                    expires_seconds=86400,
                )
                presigned_urls.append(presigned)
            else:
                presigned_urls.append(u)
    else:
        # Generate default presigned artifact URL
        obj_key = f"videos/{job_id}.mp4"
        presigned = minio_storage.generate_presigned_download_url(
            bucket="aip-job-artifacts",
            object_name=obj_key,
            expires_seconds=86400,
        )
        presigned_urls.append(presigned)

    return {
        "job_id": job_id,
        "status": job.get("status", "completed"),
        "result_urls": presigned_urls,
        "download_expires_at": expires_at,
        "ttl_seconds": 86400,
    }


@router.post("/jobs/{job_id}/cancel", status_code=200)
async def cancel_job(job_id: str, repo: IJobRepository = Depends(get_job_repo)):
    now = datetime.now(timezone.utc).isoformat()
    updated = await repo.update_job_status(job_id, "cancelled", {"updated_at": now})
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")

    return {"message": "Job cancelled successfully", "job_id": job_id}
