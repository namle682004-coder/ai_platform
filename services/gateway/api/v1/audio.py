
from fastapi import APIRouter, File, Form, UploadFile

router = APIRouter(prefix="/v1", tags=["Audio Transcriptions (STT)"])


@router.post("/audio/transcriptions")
async def create_transcription(
    file: UploadFile = File(...),
    model: str = Form("stt-vn-standard"),
    language: str | None = Form("vi"),
):
    audio_bytes = await file.read()
    return {
        "text": f"Xác nhận bóc băng ghi âm file {file.filename} (Kích thước: {len(audio_bytes)} bytes) qua mô hình {model}.",
        "language": language or "vi",
        "duration": 15.2,
    }
