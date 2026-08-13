from common.models.schemas import ChatCompletionRequest
from fastapi import APIRouter, HTTPException, Request
from gateway.services.alias_router import alias_router
from gateway.services.proxy_service import proxy_service

router = APIRouter(prefix="/v1", tags=["Chat Completions"])


@router.post("/chat/completions")
async def create_chat_completion(
    request: Request,
    payload: ChatCompletionRequest,
):
    # 1. Resolve Alias -> Target Runtime
    resolved_target = await alias_router.resolve_alias(payload.model)
    if not resolved_target:
        raise HTTPException(
            status_code=404,
            detail=f"Alias '{payload.model}' not found or disabled."
        )

    target_url = resolved_target["target_url"]

    # 2. Forward payload to Target Runtime via Proxy Service
    return await proxy_service.proxy_post(
        target_url=target_url,
        headers={"Content-Type": "application/json"},
        json_payload=payload.model_dump(),
        stream=payload.stream,
    )
