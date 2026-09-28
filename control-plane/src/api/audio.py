import asyncio
from datetime import datetime, timezone
import time
import uuid
import logging
from common.storage import minio_storage
from common.repositories.simulation_repository import audio_record_repository

import httpx
from typing import Optional
from fastapi import APIRouter, File, Form, Header, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

from src.configs.settings import gateway_settings
from src.items.alias_router import alias_router
from src.services.runtime_auth import runtime_token_headers
from src.services.runtime_policy import allow_in_process_fallback
from src.jobs.offloader import is_audio_heavy, is_speech_heavy, offload_job

logger = logging.getLogger("aip-gateway.audio")
router = APIRouter(prefix="/v1", tags=["Audio (STT & TTS)"])


class SpeechRequest(BaseModel):
    model: str = Field("tts-vi-standard", json_schema_extra={"example": "tts-vi-standard"})
    input: str = Field(..., json_schema_extra={"example": "Xin chào, đây là hệ thống chuyển đổi văn bản thành giọng nói."})
    voice: str | None = Field("northern_female", json_schema_extra={"example": "northern_female"})
    response_format: str = Field("mp3", json_schema_extra={"example": "mp3"})


@router.post("/audio/transcriptions", summary="Speech to Text (ASR Transcription)")
async def create_transcription(
    request: Request,
    file: UploadFile = File(...),
    model: str = Form("stt-vn-standard"),
    language: str | None = Form("vi"),
    authorization: Optional[str] = Header(None, include_in_schema=False),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Missing or malformed Bearer API key in Authorization header."
        )

    start_time = time.time()
    request_id = getattr(request.state, "request_id", None) if hasattr(request, "state") else f"req_{uuid.uuid4().hex[:12]}"

    # 0. Enforce Media Quota (SRS Section 2.2)
    file_size = getattr(file, "size", None) or 0
    from src.quota.enforcer import quota_enforcer
    tenant_id = getattr(request.state, "tenant_id", "TENANT_RETAIL_BANK")
    is_vip = any(k in tenant_id.lower() for k in ("vip", "enterprise", "bank", "pro"))
    allowed, err_msg = quota_enforcer.check_media_quota(file_size, media_type="audio", is_vip=is_vip)
    if not allowed:
        raise HTTPException(status_code=413, detail=err_msg)

    # Upload audio file to MinIO Object Storage (SRS Section 2.1 & 3.3)
    file_bytes = await file.read()
    await file.seek(0)
    audio_s3_uri = None
    if file_bytes:
        request_id = getattr(request.state, "request_id", None) if hasattr(request, "state") else f"req_{uuid.uuid4().hex[:12]}"
        safe_name = file.filename or f"{request_id}.wav"
        obj_name = f"audio/inputs/{tenant_id}/{datetime.now(timezone.utc).strftime('%Y%m%d')}/{request_id}_{safe_name}"
        audio_s3_uri, _ = minio_storage.upload_bytes(
            bucket="aip-data",
            object_name=obj_name,
            data=file_bytes,
            content_type=file.content_type or "audio/wav",
        )

    # 1. Automatic Heavy Workload Offload to RabbitMQ (audio file > 2MB)
    is_heavy, reason = is_audio_heavy(file_size, request)
    if is_heavy:
        return await offload_job(
            request=request,
            domain="stt",
            alias_name=model,
            payload={"filename": file.filename, "size_bytes": file_size, "language": language, "s3_uri": audio_s3_uri},
            reason=reason,
        )

    # 2. Attempt to call real GPU STT Microservice
    stt_target_url = await alias_router.resolve_target_url(model, f"{gateway_settings.stt_server_url}/v1")
    if not stt_target_url:
        raise HTTPException(status_code=404, detail=f"Model alias '{model}' not found or disabled.")
    try:
        auth_hdr = authorization
        async with httpx.AsyncClient(timeout=60.0) as client:
            files = {"file": (file.filename, file.file, file.content_type)}
            data = {"model": model, "language": language or "vi"}
            headers = {"Authorization": auth_hdr, **runtime_token_headers()}

            res = await client.post(
                f"{stt_target_url}/audio/transcriptions",
                files=files,
                data=data,
                headers=headers,
            )
            res.raise_for_status()
            data_resp = res.json()
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            trans_text = data_resp.get("text", "")
            resp_data = {
                "id": request_id,
                "object": "audio.transcription",
                "created": int(time.time()),
                "model": model,
                "status": "success",
                "text": trans_text,
                "language": data_resp.get("language", language or "vi"),
                "duration": data_resp.get("duration", 0.0),
                "segments": data_resp.get("segments", []),
                "usage": {
                    "duration_seconds": data_resp.get("duration", 0.0),
                    "character_count": len(trans_text),
                    "word_count": len(trans_text.split()),
                },
                "metadata": {
                    "backend": "Faster-Whisper CTranslate2 Engine",
                    "device": "cuda",
                    "latency_ms": elapsed_ms,
                    "request_id": request_id,
                }
            }
            asyncio.create_task(audio_record_repository.create_transcription({
                "record_id": request_id,
                "filename": getattr(file, "filename", "audio.wav") or "audio.wav",
                "text": trans_text,
                "language": data_resp.get("language", language or "vi"),
                "duration": data_resp.get("duration", 0.0),
                "model": model,
                "user_id": "user_staff_01",
                "tenant_id": tenant_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }))
            return resp_data
    except Exception as e:
        if not allow_in_process_fallback():
            raise HTTPException(status_code=503, detail="STT runtime unavailable") from e
        try:
            import sys
            from pathlib import Path
            _stt_path = Path(__file__).resolve().parent.parent.parent.parent / "data-plane" / "stt-server"
            if str(_stt_path) not in sys.path:
                sys.path.insert(0, str(_stt_path))
            from stt_engine import stt_engine
            transcription = await stt_engine.transcribe(
                audio_bytes=file_bytes,
                filename=file.filename or "audio.wav",
                language=language,
            )
            data_resp = transcription.model_dump()
            elapsed_ms = round((time.time() - start_time) * 1000, 2)
            trans_text = data_resp.get("text", "")
            resp_data = {
                "id": request_id,
                "object": "audio.transcription",
                "created": int(time.time()),
                "model": model,
                "status": "success",
                "text": trans_text,
                "language": data_resp.get("language", language or "vi"),
                "duration": data_resp.get("duration", 0.0),
                "segments": data_resp.get("segments", []),
                "usage": {
                    "duration_seconds": data_resp.get("duration", 0.0),
                    "character_count": len(trans_text),
                    "word_count": len(trans_text.split()),
                },
                "metadata": {
                    "backend": "Faster-Whisper In-Process Engine",
                    "device": "cpu",
                    "latency_ms": elapsed_ms,
                    "request_id": request_id,
                }
            }
            asyncio.create_task(audio_record_repository.create_transcription({
                "record_id": request_id,
                "filename": getattr(file, "filename", "audio.wav") or "audio.wav",
                "text": trans_text,
                "language": data_resp.get("language", language or "vi"),
                "duration": data_resp.get("duration", 0.0),
                "model": model,
                "user_id": "user_staff_01",
                "tenant_id": tenant_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }))
            return resp_data
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"GPU Inference Node Offline (STT Server): {str(e)}",
            ) from e


@router.get("/audio/speech", summary="Quick Browser Audio Synthesis (GET)")
async def create_speech_browser(
    input: str = "Xin chào, đây là hệ thống chuyển đổi văn bản thành giọng nói.",
    voice: str = "northern_female",
    response_format: str = "mp3",
):
    ext = response_format.lower()
    media_type = "audio/mpeg" if ext == "mp3" else f"audio/{ext}"

    try:
        import sys
        from pathlib import Path
        _tts_path = Path(__file__).resolve().parent.parent.parent.parent / "data-plane" / "tts-adapter"
        if str(_tts_path) not in sys.path:
            sys.path.insert(0, str(_tts_path))
        from tts_engine import tts_engine
        chunks = []
        async for chunk in tts_engine.generate_speech_stream(
            text=input,
            voice=voice,
            response_format=response_format,
        ):
            chunks.append(chunk)
        audio_bytes = b"".join(chunks)

        # Save to MinIO (Production Key Taxonomy)
        req_id = f"req_{uuid.uuid4().hex[:12]}"
        obj_name = f"audio/speech/TENANT_DEFAULT/{datetime.now(timezone.utc).strftime('%Y%m%d')}/{req_id}.{ext}"
        try:
            minio_storage.upload_bytes(bucket="aip-job-artifacts", object_name=obj_name, data=audio_bytes, content_type=media_type)
            minio_storage.upload_bytes(bucket="aip-data", object_name=obj_name, data=audio_bytes, content_type=media_type)
        except Exception:
            pass

        return Response(content=audio_bytes, media_type=media_type, headers={"X-AIP-Storage-Key": obj_name})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/audio/speech", summary="Text to Speech (Audio Synthesis)")
async def create_speech(
    request: Request,
    payload: SpeechRequest,
    authorization: Optional[str] = Header(None, include_in_schema=False),
):
    auth_hdr = authorization or request.headers.get("Authorization")
    if not auth_hdr or not auth_hdr.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Missing or malformed Bearer API key in Authorization header."
        )

    # 0. Automatic Heavy Workload Offload to RabbitMQ (TTS input > 300 chars)
    is_heavy, reason = is_speech_heavy(payload.input, request)
    if is_heavy:
        return await offload_job(
            request=request,
            domain="tts",
            alias_name=payload.model,
            payload=payload.model_dump(),
            reason=reason,
        )

    tenant_id = getattr(request.state, "tenant_id", "TENANT_RETAIL_BANK")
    ext = payload.response_format.lower() if payload.response_format else "mp3"
    media_type = "audio/mpeg" if ext == "mp3" else f"audio/{ext}"

    # 1. Attempt to call real GPU TTS Microservice
    tts_target_url = await alias_router.resolve_target_url(payload.model, f"{gateway_settings.tts_server_url}/v1")
    if not tts_target_url:
        raise HTTPException(status_code=404, detail=f"Model alias '{payload.model}' not found or disabled.")
    audio_bytes = None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                f"{tts_target_url}/audio/speech",
                json=payload.model_dump(),
                headers={"Authorization": auth_hdr, "Content-Type": "application/json", **runtime_token_headers()},
            )
            res.raise_for_status()
            audio_bytes = res.content
    except Exception as e:
        if not allow_in_process_fallback():
            raise HTTPException(status_code=503, detail="TTS runtime unavailable") from e
        try:
            import sys
            from pathlib import Path
            _tts_path = Path(__file__).resolve().parent.parent.parent.parent / "data-plane" / "tts-adapter"
            if str(_tts_path) not in sys.path:
                sys.path.insert(0, str(_tts_path))
            from tts_engine import tts_engine
            chunks = []
            async for chunk in tts_engine.generate_speech_stream(
                text=payload.input,
                voice=payload.voice,
                response_format=payload.response_format,
            ):
                chunks.append(chunk)
            audio_bytes = b"".join(chunks)
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"GPU Inference Node Offline (TTS Server): {str(e)}",
            ) from e

    # 2. Upload synthesized audio artifact into MinIO (SRS Section 2.1 & 3.3)
    request_id = getattr(request.state, "request_id", None) if hasattr(request, "state") else f"req_{uuid.uuid4().hex[:12]}"
    obj_name = f"audio/speech/{tenant_id}/{datetime.now(timezone.utc).strftime('%Y%m%d')}/{request_id}.{ext}"
    if audio_bytes:
        try:
            minio_storage.upload_bytes(
                bucket="aip-job-artifacts",
                object_name=obj_name,
                data=audio_bytes,
                content_type=media_type,
            )
            minio_storage.upload_bytes(
                bucket="aip-data",
                object_name=obj_name,
                data=audio_bytes,
                content_type=media_type,
            )
        except Exception as m_err:
            logger.warning(f"Could not archive audio to MinIO: {m_err}")

        asyncio.create_task(audio_record_repository.create_synthesis({
            "record_id": request_id,
            "text": payload.input,
            "voice": payload.voice,
            "format": ext,
            "model": payload.model,
            "user_id": "user_staff_01",
            "tenant_id": tenant_id,
            "s3_key": obj_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }))

    return Response(
        content=audio_bytes,
        media_type=media_type,
        headers={
            "X-AIP-Storage-Bucket": "aip-job-artifacts",
            "X-AIP-Storage-Key": obj_name,
        }
    )
