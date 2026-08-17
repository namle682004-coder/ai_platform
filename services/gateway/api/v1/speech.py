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
            if res.status_code == 200:
                # Stream the response chunks directly
                return StreamingResponse(
                    res.aiter_bytes(),
                    media_type=res.headers.get("content-type", "audio/mpeg")
                )
    except Exception:
        # Fallback to local simulated logic if backend tts-adapter is offline/not started
        pass

    # 2. Local Fallback Simulation
    async def audio_stream_generator() -> AsyncGenerator[bytes, None]:
        for _ in range(5):
            yield b"\xFF\xF3\x44\xC4\x00\x00"

    return StreamingResponse(audio_stream_generator(), media_type="audio/mpeg")
