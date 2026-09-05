import httpx
from collections.abc import AsyncGenerator
from fastapi import APIRouter, Request, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional
from gateway.core.config import gateway_settings

router = APIRouter(prefix="/v1", tags=["Audio Speech (TTS)"])


class SpeechRequest(BaseModel):
    model: str = Field("tts-vi-standard", json_schema_extra={"example": "tts-vi-standard"})
    input: str = Field(..., json_schema_extra={"example": "Xin chào, đây là hệ thống chuyển đổi văn bản thành giọng nói."})
    voice: str | None = Field("northern_female", json_schema_extra={"example": "northern_female"})
    response_format: str = Field("mp3", json_schema_extra={"example": "mp3"})


@router.post("/audio/speech")
async def create_speech(
    request: Request,
    payload: SpeechRequest,
    authorization: Optional[str] = Header(None)
):
    # 1. Attempt to call real GPU TTS Microservice
    try:
        auth_hdr = authorization or "Bearer SSAmMKZJHIgM82n0NTnFQq6Q3CkIjLR"
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(
                f"{gateway_settings.tts_server_url}/v1/audio/speech",
                json=payload.model_dump(),
                headers={"Authorization": auth_hdr, "Content-Type": "application/json"}
            )
            res.raise_for_status()
            # Stream the response chunks directly
            return StreamingResponse(
                res.aiter_bytes(),
                media_type=res.headers.get("content-type", "audio/mpeg")
            )
    except httpx.HTTPError as e:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=502,
            detail=f"GPU Inference Node Offline (TTS Server): {str(e)}"
        ) from e
