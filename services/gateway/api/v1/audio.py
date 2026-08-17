
import httpx
from fastapi import APIRouter, File, Form, UploadFile, Header
from typing import Optional
from gateway.core.config import gateway_settings

router = APIRouter(prefix="/v1", tags=["Audio Transcriptions (STT)"])


@router.post("/audio/transcriptions")
async def create_transcription(
    file: UploadFile = File(...),
    model: str = Form("stt-vn-standard"),
    language: str | None = Form("vi"),
    authorization: Optional[str] = Header(None)
):
    audio_bytes = await file.read()
    
    # 1. Attempt to call real GPU STT Microservice
    try:
        auth_hdr = authorization or "Bearer SSAmMKZJHIgM82n0NTnFQq6Q3CkIjLR"
        async with httpx.AsyncClient(timeout=15.0) as client:
            # We must reset file seek to read again
            await file.seek(0)
            files = {"file": (file.filename, file.file, file.content_type)}
            data = {"model": model, "language": language or "vi"}
            headers = {"Authorization": auth_hdr}
            
            res = await client.post(
                f"{gateway_settings.stt_server_url}/v1/audio/transcriptions",
                files=files,
                data=data,
                headers=headers
            )
            res.raise_for_status()
            return res.json()
    except httpx.HTTPError as e:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=502,
            detail=f"GPU Inference Node Offline (STT Server): {str(e)}"
        )
