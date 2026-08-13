from fastapi import FastAPI, HTTPException, Header, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional

stt_app = FastAPI(
    title="AIP Speech-to-Text Microservice (Faster-Whisper)",
    version="1.0.0",
    description="Speech-to-Text Pipeline Server",
)


class TranscriptionResponse(BaseModel):
    text: str
    language: str
    duration: float


@stt_app.post("/v1/audio/transcriptions", response_model=TranscriptionResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    model: str = Form("stt-vn-standard"),
    language: Optional[str] = Form("vi"),
    authorization: Optional[str] = Header(None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized: Bearer API key required")

    mock_transcript = f"Xác nhận phiên bóc băng ghi âm âm thanh file {file.filename} qua mô hình {model}."

    return TranscriptionResponse(
        text=mock_transcript,
        language=language or "vi",
        duration=12.5,
    )


@stt_app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "service": "stt-server", "backend": "Faster-Whisper v1.x"}
