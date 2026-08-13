from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Optional

router = APIRouter(prefix="/v1", tags=["Audio Transcriptions (STT)"])


@router.post("/audio/transcriptions")
async def create_transcription(
    file: UploadFile = File(...),
    model: str = Form("stt-vn-standard"),
    language: Optional[str] = Form("vi"),
):
    audio_bytes = await file.read()
    return {
        "text": f"Xác nhận bóc băng ghi âm file {file.filename} (Kích thước: {len(audio_bytes)} bytes) qua mô hình {model}.",
        "language": language or "vi",
        "duration": 15.2,
    }
