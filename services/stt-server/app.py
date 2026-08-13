from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional

stt_app = FastAPI(
    title="AIP Speech-to-Text Server (Faster-Whisper)",
    version="1.0.0",
    description="Faster-Whisper & PhoWhisper Audio Transcription Microservice",
)


class TranscriptionResponse(BaseModel):
    text: str
    language: str = "vi"
    duration: float
    segments: list = []


@stt_app.post("/v1/audio/transcriptions", response_model=TranscriptionResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    model: str = Form("stt-vn-standard"),
    language: Optional[str] = Form("vi"),
    authorization: Optional[str] = Header(None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized: Bearer API key required")

    audio_bytes = await file.read()
    mock_transcript = f"Xác nhận phiên bóc băng ghi âm âm thanh file {file.filename} qua mô hình {model}."

    return TranscriptionResponse(
        text=mock_transcript,
        language=language or "vi",
        duration=18.4,
        segments=[{"id": 0, "start": 0.0, "end": 18.4, "text": mock_transcript}]
    )


@stt_app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "service": "stt-server", "backend": "Faster-Whisper v1.x"}
