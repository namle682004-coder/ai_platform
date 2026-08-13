from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, AsyncGenerator

tts_app = FastAPI(
    title="AIP Text-to-Speech Adapter (viXTTS & OpenVoice)",
    version="1.0.0",
    description="Text-to-Speech Audio Synthesis & Voice Cloning Microservice",
)


class TTSRequest(BaseModel):
    model: str = Field("tts-vi-standard", json_schema_extra={"example": "tts-vi-standard"})
    input: str = Field(..., json_schema_extra={"example": "Xin chào, đây là giọng đọc AI."})
    voice: Optional[str] = Field("northern_female", json_schema_extra={"example": "northern_female"})
    response_format: str = Field("mp3", json_schema_extra={"example": "mp3"})


@tts_app.post("/v1/audio/speech")
async def generate_speech(
    request: TTSRequest,
    authorization: Optional[str] = Header(None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized: Bearer API key required")

    async def audio_stream_generator() -> AsyncGenerator[bytes, None]:
        # Simulated MP3 audio chunks streaming response
        for _ in range(5):
            yield b"\xFF\xF3\x44\xC4\x00\x00"  # Mock MP3 frame bytes

    return StreamingResponse(audio_stream_generator(), media_type="audio/mpeg")


@tts_app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "service": "tts-adapter", "backend": "viXTTS / OpenVoice V2"}
