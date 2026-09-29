"""
Enterprise Chat Completions Endpoint compliant with OpenAI format & SRS Section 5.2.
"""

from common.models.schemas import ChatCompletionRequest, AIPErrorResponse, AIPError
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from src.items.alias_router import alias_router
from src.api.proxy import proxy_service
from src.configs.settings import gateway_settings

router = APIRouter(prefix="/v1", tags=["Chat Completions"])


@router.post(
    "/chat/completions",
    summary="Create Chat Completion (OpenAI-compatible, SSE Streaming Supported)",
)
async def create_chat_completion(
    request: Request,
    payload: ChatCompletionRequest,
):
    request_id = request.headers.get("X-Request-ID") or "req_chat_gen"
    allowed_aliases = getattr(request.state, "allowed_aliases", ["*"])

    # 1. Alias Authorization Check (SRS Section 3.4)
    if "*" not in allowed_aliases and payload.model not in allowed_aliases:
        error_payload = AIPErrorResponse(
            error=AIPError(
                type="permission_error",
                code="forbidden_alias",
                message=f"Access to alias '{payload.model}' is not authorized for this API key.",
                request_id=request_id,
                retryable=False,
            )
        )
        return JSONResponse(status_code=403, content=error_payload.model_dump())

    # 2. Resolve Logical Alias -> Concrete Target Runtime
    resolved_target = await alias_router.resolve_alias(payload.model)
    if not resolved_target:
        error_payload = AIPErrorResponse(
            error=AIPError(
                type="not_found_error",
                code="alias_not_found",
                message=f"Model alias '{payload.model}' not found or currently disabled.",
                request_id=request_id,
                retryable=False,
            )
        )
        return JSONResponse(status_code=404, content=error_payload.model_dump())

    # SRS Section 6.2: Deprecated Aliases flag
    if resolved_target.get("status") == "deprecated":
        request.state.alias_deprecated = True

    target_url = await alias_router.resolve_target_url(
        payload.model,
        f"{gateway_settings.vllm_server_url}",
    )
    if not target_url:
        error_payload = AIPErrorResponse(
            error=AIPError(
                type="service_unavailable_error",
                code="runtime_unavailable",
                message=f"Runtime target for model alias '{payload.model}' is unavailable.",
                request_id=request_id,
                retryable=True,
            )
        )
        return JSONResponse(status_code=503, content=error_payload.model_dump())

    # 3. Automatic Heavy Workload Offload to RabbitMQ (chat > 3000 chars or max_tokens > 2048)
    if not payload.stream:
        from src.jobs.offloader import is_chat_heavy, offload_job

        is_heavy, reason = is_chat_heavy(payload.messages, payload.max_tokens, request)
        if is_heavy:
            return await offload_job(
                request=request,
                domain="chat",
                alias_name=payload.model,
                payload=payload.model_dump(),
                reason=reason,
            )

    # 4. Conditional Deterministic Cache Check (SRS Section 5.2: temperature == 0.0 or X-AIP-Cache header)
    eligible_for_cache = not payload.stream and (
        payload.temperature == 0.0
        or request.headers.get("X-AIP-Cache", "").lower() == "true"
    )
    if eligible_for_cache:
        from src.cache.inference_cache import inference_cache

        cached_val, is_hit = await inference_cache.get(
            domain="chat",
            model_or_alias=payload.model,
            payload_data=payload.model_dump(),
            request=request,
        )
        if is_hit and cached_val:
            return JSONResponse(
                content=cached_val,
                headers={"X-Cache": "HIT", "X-Cache-Node": "redis-cache"},
            )

    # Extract metadata for async usage metering (SRS Section 7 & 8)
    tenant_id = getattr(request.state, "tenant_id", "TENANT_RETAIL_BANK")
    cost_center = getattr(request.state, "cost_center", "CC_DIGITAL_BANKING")
    raw_key = getattr(request.state, "raw_api_key", "")
    key_prefix = (raw_key[:12] + "...") if raw_key else None
    client_ip = request.client.host if request.client else "unknown"

    meta = {
        "tenant_id": tenant_id,
        "cost_center": cost_center,
        "api_key_prefix": key_prefix,
        "domain": "chat",
        "physical_model": resolved_target.get("physical_model", "Qwen3-8B"),
        "client_ip": client_ip,
    }

    # 5. Forward Payload to Target Runtime via Proxy Service
    proxy_res = await proxy_service.proxy_post(
        target_url=target_url,
        headers={
            "Content-Type": "application/json",
            "Authorization": request.headers.get("Authorization", ""),
            "X-Request-ID": request_id,
        },
        json_payload=payload.model_dump(),
        stream=payload.stream,
        metadata=meta,
    )

    if eligible_for_cache and isinstance(proxy_res, dict):
        from src.cache.inference_cache import inference_cache

        await inference_cache.set(
            domain="chat",
            model_or_alias=payload.model,
            payload_data=payload.model_dump(),
            response_data=proxy_res,
            ttl_seconds=3600,
        )
        return JSONResponse(content=proxy_res, headers={"X-Cache": "MISS"})

    if isinstance(proxy_res, dict):
        return JSONResponse(content=proxy_res, headers={"X-Cache": "BYPASS"})

    return proxy_res
