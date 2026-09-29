"""
Enterprise Reverse Proxy Service for Upstream AI Inference Engines (vLLM / Triton).
Forwards request payload to runtime endpoints and streams SSE chunks back to clients.
Compliant with Clean Architecture Control-Plane & SRS Section 2.2, 3.1, 3.2, 3.4, 5.2, 5.3, 7.1.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional, Dict, Any

import httpx
from common.models.schemas import AIPError, AIPErrorResponse
from fastapi.responses import JSONResponse, StreamingResponse
from src.configs.settings import gateway_settings
from src.usage.meter import usage_meter

logger = logging.getLogger("aip-proxy")


class StreamingProxyService:
    """
    Reverse Proxy Service connecting Control-Plane Gateway to Data-Plane Inference Nodes (vLLM, Triton, etc.).
    Preserves raw SSE stream deltas from vLLM and handles upstream network resilience.
    Asynchronously records inference token usage without blocking client responses (SRS Section 7 & 8).
    """

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=120.0)

    async def proxy_post(
        self,
        target_url: str,
        headers: dict,
        json_payload: dict,
        stream: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        request_id = headers.get("X-Request-ID") or "req_proxy_forward"
        model_name = json_payload.get("model", "chat-general-standard")
        full_url = target_url if target_url.endswith("/chat/completions") else f"{target_url.rstrip('/')}/chat/completions"

        req_headers = {"Content-Type": "application/json"}
        if "Authorization" in headers:
            req_headers["Authorization"] = headers["Authorization"]
        if "X-Request-ID" in headers:
            req_headers["X-Request-ID"] = request_id
        if gateway_settings.runtime_token:
            req_headers["X-AIP-Runtime-Token"] = gateway_settings.runtime_token.get_secret_value()

        meta = metadata or {}
        start_time = time.time()
        timeout_sec = float(metadata.get("timeout_seconds", 120.0)) if metadata else float(gateway_settings.request_timeout_seconds)

        try:
            if not stream:
                res = await self.client.post(
                    full_url,
                    headers=req_headers,
                    json=json_payload,
                    timeout=timeout_sec,
                )
                duration = time.time() - start_time
                latency_ms = round(duration * 1000, 2)

                if res.status_code == 200:
                    data = res.json()
                    usage_info = data.get("usage", {})
                    p_tokens = usage_info.get("prompt_tokens", 0)
                    c_tokens = usage_info.get("completion_tokens", 0)
                    t_tokens = usage_info.get("total_tokens", p_tokens + c_tokens)

                    # Asynchronous fire-and-forget usage recording
                    asyncio.create_task(
                        usage_meter.record_inference_usage(
                            request_id=request_id,
                            tenant_id=meta.get("tenant_id", "TENANT_RETAIL_BANK"),
                            cost_center=meta.get("cost_center", "CC_DIGITAL_BANKING"),
                            api_key_prefix=meta.get("api_key_prefix"),
                            domain=meta.get("domain", "chat"),
                            model_alias=model_name,
                            physical_model=meta.get("physical_model", "Qwen3-8B"),
                            prompt_tokens=p_tokens,
                            completion_tokens=c_tokens,
                            total_tokens=t_tokens,
                            latency_ms=latency_ms,
                            status_code=200,
                            stream=False,
                            client_ip=meta.get("client_ip", "unknown"),
                        )
                    )
                    return data

                # Check if upstream returned 503 capacity or 429
                if res.status_code == 503:
                    error_body = AIPErrorResponse(
                        error=AIPError(
                            type="service_unavailable",
                            code="capacity_exhausted",
                            message=f"Inference GPU capacity exhausted for model '{model_name}'. Please retry shortly.",
                            request_id=request_id,
                            retryable=True,
                        )
                    )
                    return JSONResponse(status_code=503, content=error_body.model_dump())

                return JSONResponse(
                    status_code=res.status_code,
                    content=res.json() if "application/json" in res.headers.get("content-type", "") else {"detail": res.text},
                )
            else:
                # SSE Streaming Flow (SRS Section 3.2)
                req = self.client.build_request("POST", full_url, headers=req_headers, json=json_payload)
                res = await self.client.send(req, stream=True)
                if res.status_code == 200:
                    async def vllm_stream():
                        chunk_count = 0
                        emitted_done = False
                        try:
                            async for chunk in res.aiter_bytes():
                                chunk_count += 1
                                if b"data: [DONE]" in chunk:
                                    emitted_done = True
                                yield chunk
                            # Guard: emit data: [DONE] if upstream finished without emitting it (SRS 3.2)
                            if not emitted_done:
                                yield b"data: [DONE]\n\n"
                        finally:
                            await res.aclose()
                            duration = time.time() - start_time
                            latency_ms = round(duration * 1000, 2)

                            messages = json_payload.get("messages", [])
                            p_len = sum(len(str(m.get("content", ""))) for m in messages if isinstance(m, dict))
                            p_tokens = max(1, p_len // 4)
                            c_tokens = max(1, chunk_count)
                            t_tokens = p_tokens + c_tokens

                            asyncio.create_task(
                                usage_meter.record_inference_usage(
                                    request_id=request_id,
                                    tenant_id=meta.get("tenant_id", "TENANT_RETAIL_BANK"),
                                    cost_center=meta.get("cost_center", "CC_DIGITAL_BANKING"),
                                    api_key_prefix=meta.get("api_key_prefix"),
                                    domain=meta.get("domain", "chat"),
                                    model_alias=model_name,
                                    physical_model=meta.get("physical_model", "Qwen3-8B"),
                                    prompt_tokens=p_tokens,
                                    completion_tokens=c_tokens,
                                    total_tokens=t_tokens,
                                    latency_ms=latency_ms,
                                    status_code=200,
                                    stream=True,
                                    client_ip=meta.get("client_ip", "unknown"),
                                )
                            )

                    return StreamingResponse(vllm_stream(), media_type="text/event-stream")

                await res.aclose()
                return JSONResponse(
                    status_code=res.status_code,
                    content={"detail": f"Upstream vLLM node returned status {res.status_code}"},
                )

        except httpx.TimeoutException as exc:
            # SRS Section 3.4: Runtime timeout -> HTTP 504, runtime_timeout, retryable=True
            logger.warning(f"Target inference node for '{model_name}' timed out after {timeout_sec}s: {exc}")
            error_body = AIPErrorResponse(
                error=AIPError(
                    type="timeout_error",
                    code="runtime_timeout",
                    message=f"Runtime inference timeout after {timeout_sec}s for model '{model_name}'.",
                    request_id=request_id,
                    retryable=True,
                )
            )
            return JSONResponse(status_code=504, content=error_body.model_dump())

        except Exception as exc:
            # SRS Section 3.4: Runtime unavailable -> HTTP 503, runtime_unavailable, retryable=True
            logger.warning(f"Target inference node '{model_name}' ({full_url}) offline or unreachable: {exc}")
            error_body = AIPErrorResponse(
                error=AIPError(
                    type="server_error",
                    code="runtime_unavailable",
                    message=(
                        f"Target vLLM inference node for '{model_name}' ({full_url}) is offline or unreachable. "
                        "Please ensure the inference engine is running."
                    ),
                    request_id=request_id,
                    retryable=True,
                )
            )
            return JSONResponse(status_code=503, content=error_body.model_dump())


proxy_service = StreamingProxyService()
