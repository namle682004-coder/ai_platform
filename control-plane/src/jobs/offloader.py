"""
Enterprise Workload Auto-Offloading Service for AIP Platform.

Detects heavy workloads across all AI services (Chat, Translation, STT, TTS, Images)
and automatically offloads them to RabbitMQ as asynchronous background jobs with
native priority queuing, returning an HTTP 202 Accepted response.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Request
from fastapi.responses import JSONResponse

from common.repositories.mongo_repositories import job_repository

logger = logging.getLogger("aip-gateway.offloader")

# ── Heavy Workload Thresholds ─────────────────────────────────────────
THRESHOLD_TRANSLATION_CHARS: int = 500      # > 500 chars -> offload to translation queue
THRESHOLD_CHAT_CHARS: int = 3000            # > 3,000 prompt chars -> offload to chat queue
THRESHOLD_CHAT_MAX_TOKENS: int = 2048       # > 2,048 gen tokens -> offload to chat queue
THRESHOLD_AUDIO_BYTES: int = 2 * 1024 * 1024  # > 2 MB audio -> offload to stt queue
THRESHOLD_TTS_CHARS: int = 300              # > 300 speech chars -> offload to tts queue
THRESHOLD_IMAGE_N: int = 1                  # > 1 image -> offload to image queue


def is_explicit_async_requested(request: Request) -> bool:
    """Check if client explicitly requested async dispatch via headers."""
    prefer = request.headers.get("Prefer", "").lower()
    dispatch = request.headers.get("X-Dispatch-Mode", "").lower()
    return "respond-async" in prefer or dispatch == "async"


def is_translation_heavy(text: str, request: Request) -> tuple[bool, str]:
    """Determine if a translation request exceeds synchronous capacity."""
    if is_explicit_async_requested(request):
        return True, "Client explicitly requested async processing (Prefer: respond-async)"
    char_len = len(text.strip())
    if char_len > THRESHOLD_TRANSLATION_CHARS:
        return True, f"Văn bản dài {char_len} ký tự (ngưỡng an toàn tức thì: {THRESHOLD_TRANSLATION_CHARS} ký tự)"
    return False, ""


def is_chat_heavy(messages: list[Any], max_tokens: Optional[int], request: Request) -> tuple[bool, str]:
    """Determine if a chat completion request exceeds synchronous capacity."""
    if is_explicit_async_requested(request):
        return True, "Client explicitly requested async processing (Prefer: respond-async)"
    
    total_chars = 0
    for m in messages:
        if isinstance(m, dict):
            total_chars += len(str(m.get("content", "")))
        elif hasattr(m, "content"):
            total_chars += len(str(m.content or ""))
            
    if total_chars > THRESHOLD_CHAT_CHARS:
        return True, f"Tổng độ dài ngữ cảnh hội thoại {total_chars} ký tự (ngưỡng: {THRESHOLD_CHAT_CHARS} ký tự)"
    
    if max_tokens and max_tokens > THRESHOLD_CHAT_MAX_TOKENS:
        return True, f"Số lượng tokens sinh {max_tokens} vượt ngưỡng sinh tức thời ({THRESHOLD_CHAT_MAX_TOKENS} tokens)"
        
    return False, ""


def is_speech_heavy(input_text: str, request: Request) -> tuple[bool, str]:
    """Determine if a TTS speech synthesis request exceeds synchronous capacity."""
    if is_explicit_async_requested(request):
        return True, "Client explicitly requested async processing (Prefer: respond-async)"
    char_len = len(input_text.strip())
    if char_len > THRESHOLD_TTS_CHARS:
        return True, f"Văn bản đọc {char_len} ký tự (ngưỡng an toàn tức thì: {THRESHOLD_TTS_CHARS} ký tự)"
    return False, ""


def is_audio_heavy(file_size_bytes: int, request: Request) -> tuple[bool, str]:
    """Determine if an audio transcription request exceeds synchronous capacity."""
    if is_explicit_async_requested(request):
        return True, "Client explicitly requested async processing (Prefer: respond-async)"
    if file_size_bytes > THRESHOLD_AUDIO_BYTES:
        mb_size = file_size_bytes / (1024 * 1024)
        return True, f"Kích thước tệp âm thanh {mb_size:.2f} MB (ngưỡng an toàn: {THRESHOLD_AUDIO_BYTES / (1024*1024):.0f} MB)"
    return False, ""


def is_image_heavy(n: int, request: Request) -> tuple[bool, str]:
    """Determine if an image generation request exceeds synchronous capacity."""
    if is_explicit_async_requested(request):
        return True, "Client explicitly requested async processing (Prefer: respond-async)"
    if n > THRESHOLD_IMAGE_N:
        return True, f"Yêu cầu sinh đồng thời {n} hình ảnh (ngưỡng an toàn tức thì: {THRESHOLD_IMAGE_N} ảnh)"
    return False, ""


async def offload_job(
    request: Request,
    domain: str,
    alias_name: str,
    payload: dict[str, Any],
    reason: str,
) -> JSONResponse:
    """
    Persist job to MongoDB, dispatch task to RabbitMQ with priority,
    and return a standardized HTTP 202 Accepted response.
    """
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    tenant_id = (
        getattr(request.state, "tenant_id", None)
        or request.headers.get("X-Tenant-ID")
        or "TENANT_RETAIL_BANK"
    )
    if tenant_id in ("TENANT_DEFAULT", "TENANT_AUTOMATION_TEST"):
        tenant_id = "TENANT_RETAIL_BANK"

    # ── Intelligent Auto-Priority Scoring Engine ───────────────────────
    # Người dùng thông thường không biết gắn header X-Priority.
    # Hệ thống tự động đánh giá mức độ ưu tiên thông minh dựa trên:
    # 1. Header chỉ định nếu có (Override)
    # 2. Người dùng tương tác trực tiếp trên Web UI (cần kết quả ngay -> HIGH)
    # 3. Gói cước Tenant SLA (Enterprise/VIP -> HIGH)
    # 4. Kích thước công việc (Vừa phải -> HIGH để trả nhanh; Siêu dài -> BATCH)
    explicit_pri = request.headers.get("X-Priority")
    if explicit_pri and explicit_pri.lower() in ("high", "normal", "batch"):
        req_priority = explicit_pri.lower()
    else:
        # Tự động tính điểm ưu tiên (Auto-Priority)
        origin = request.headers.get("Origin", "") + request.headers.get("Referer", "")
        sec_fetch = request.headers.get("Sec-Fetch-Mode", "")
        is_interactive_ui = ("5173" in origin or "staff" in origin or sec_fetch == "cors")
        
        tenant_lower = tenant_id.lower()
        is_vip_tenant = any(k in tenant_lower for k in ("vip", "enterprise", "corp", "pro", "marketing", "bank"))

        if is_interactive_ui or is_vip_tenant:
            # Người dùng thật đang chờ trên màn hình Web Portal -> ƯU TIÊN CAO
            req_priority = "high"
        elif domain in ("video", "lipsync") or len(str(payload.get("text", ""))) > 5000:
            # Tác vụ siêu nặng chạy nền số lượng lớn -> Xếp vào BATCH
            req_priority = "batch"
        else:
            # Tác vụ thông thường -> HIGH nếu vừa phải để trả nhanh cho khách, hoặc NORMAL
            req_priority = "high" if len(str(payload.get("text", ""))) <= 2000 else "normal"
    priority_level = 9 if req_priority == "high" else (1 if req_priority == "batch" else 5)

    # 0. Job Concurrency Quota Check (SRS Section 2.2)
    from src.quota.enforcer import quota_enforcer
    job_limit = 30 if any(k in tenant_id.lower() for k in ("vip", "enterprise", "bank", "pro")) else 10
    acquired, active_count = await quota_enforcer.acquire_job_concurrency(tenant_id, limit=job_limit)
    if not acquired:
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "type": "rate_limit_error",
                    "code": "job_concurrency_exceeded",
                    "message": f"Tenant '{tenant_id}' has reached the limit of {job_limit} active asynchronous jobs ({active_count} active). Please wait for ongoing jobs to finish.",
                    "request_id": f"req_{job_id}",
                    "retryable": True,
                }
            },
            headers={"Retry-After": "10"}
        )

    # 1. Save to MongoDB
    job_record = {
        "job_id": job_id,
        "tenant_id": tenant_id,
        "job_type": f"tasks.{domain}",
        "alias_name": alias_name,
        "status": "queued",
        "progress": 0,
        "error_message": None,
        "result_urls": None,
        "payload": payload,
        "priority": req_priority,
        "offload_reason": reason,
        "created_at": now,
        "updated_at": now,
    }
    try:
        await job_repository.create_job(job_record)
    except Exception as exc:
        logger.warning(f"Failed to persist offloaded job {job_id} to MongoDB: {exc}")

    # 2. Publish to RabbitMQ
    pub = getattr(request.app.state, "task_publisher", None)
    if pub is None:
        try:
            from src.publisher.task_publisher import TaskPublisher
            from src.configs.settings import gateway_settings
            pub = TaskPublisher(gateway_settings.rabbitmq_url)
            await pub.connect()
            request.app.state.task_publisher = pub
        except Exception as exc:
            logger.error(f"Failed to initialize TaskPublisher for offload: {exc}")

    if pub is not None:
        try:
            await pub.publish_task(
                task_id=job_id,
                tenant_id=tenant_id,
                task_type=f"tasks.{domain}",
                alias_name=alias_name,
                priority=req_priority,
                payload=payload,
            )
            logger.info(
                "Heavy workload auto-offloaded to RabbitMQ",
                extra={
                    "job_id": job_id,
                    "domain": domain,
                    "alias": alias_name,
                    "priority": req_priority,
                    "reason": reason,
                },
            )
        except Exception as exc:
            logger.error(f"Failed to publish offloaded task {job_id} to RabbitMQ: {exc}")

    # 3. Return HTTP 202 Accepted envelope
    return JSONResponse(
        status_code=202,
        content={
            "status": "queued",
            "mode": "async_job",
            "job_id": job_id,
            "job_type": f"tasks.{domain}",
            "alias_name": alias_name,
            "priority": req_priority,
            "priority_level": priority_level,
            "reason": reason,
            "message": f"Tác vụ vượt ngưỡng xử lý tức thời ({reason}). Hệ thống đã tự động điều phối vào hàng đợi RabbitMQ (q.aip.tasks.{domain}).",
            "check_status_url": f"/v1/jobs/{job_id}",
            "created_at": now,
        },
    )
