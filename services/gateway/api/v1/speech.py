from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

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
):
    async def audio_stream_generator() -> AsyncGenerator[bytes, None]:
        for _ in range(5):
            yield b"\xFF\xF3\x44\xC4\x00\x00"

    return StreamingResponse(audio_stream_generator(), media_type="audio/mpeg")
