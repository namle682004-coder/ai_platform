
import time

import httpx
from common.models.schemas import EmbeddingRequest, EmbeddingResponse
from fastapi import APIRouter, Header, HTTPException, Request, Response
from src.cache.inference_cache import inference_cache
from src.configs.settings import gateway_settings
from src.items.alias_router import alias_router
from src.services.runtime_auth import runtime_token_headers

router = APIRouter(prefix="/v1", tags=["Embeddings"])


@router.post("/embeddings", response_model=EmbeddingResponse, summary="Vector Embeddings Extraction")
@router.post("/nlp/embeddings", response_model=EmbeddingResponse, include_in_schema=False)
async def create_embeddings(
    request: EmbeddingRequest,
    http_request: Request,
    response: Response,
    authorization: str | None = Header(None, include_in_schema=False),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized: Bearer API key required")

    start_time = time.time()
    # 1. Check deterministic cache (TTL 7 days)
    cached_val, is_hit = await inference_cache.get(
        domain="embeddings",
        model_or_alias=request.model,
        payload_data={"input": request.input, "model": request.model},
        request=http_request,
    )
    if is_hit and cached_val:
        inference_cache.inject_headers(response, is_hit=True, duration_ms=(time.time() - start_time) * 1000)
        return EmbeddingResponse(**cached_val)

    # 2. Resolve the embedding alias before forwarding to the runtime.
    target_url = await alias_router.resolve_target_url(
        request.model,
        gateway_settings.vllm_server_url,
    )
    if not target_url:
        raise HTTPException(status_code=404, detail=f"Model alias '{request.model}' not found or disabled.")

    try:
        async with httpx.AsyncClient(timeout=gateway_settings.request_timeout_seconds) as client:
            upstream = await client.post(
                f"{target_url.rstrip('/')}/embeddings",
                json=request.model_dump(),
                headers={"Authorization": authorization, "Content-Type": "application/json", **runtime_token_headers()},
            )
            upstream.raise_for_status()
            resp_obj = EmbeddingResponse(**upstream.json())
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Embedding runtime unavailable: {exc}") from exc

    # 3. Save to Redis Cache (7 days)
    await inference_cache.set(
        domain="embeddings",
        model_or_alias=request.model,
        payload_data={"input": request.input, "model": request.model},
        response_data=resp_obj.model_dump(),
        ttl_seconds=604800,
    )

    inference_cache.inject_headers(response, is_hit=False, duration_ms=(time.time() - start_time) * 1000)
    return resp_obj

