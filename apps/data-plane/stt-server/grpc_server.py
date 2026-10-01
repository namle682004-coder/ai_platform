"""
AIP High-Performance gRPC Server for Faster-Whisper Speech-to-Text (:50052).
Implements dedicated SttService (TranscribeAudio, GetHealth, Cancel).
Compliant with Clean Architecture, ISP, and DCP isolated service specifications.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Dict

import grpc
from contracts.generated import stt_pb2, stt_pb2_grpc, common_pb2

try:
    from .config import stt_settings
    from .stt_engine import stt_engine
except (ImportError, ValueError):
    import importlib.util
    import sys
    def _load_local_stt(name, fname):
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
        spec = importlib.util.spec_from_file_location(name, p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    _cfg = _load_local_stt("stt_cfg", "config.py")
    sys.modules["config"] = _cfg
    stt_settings = _cfg.stt_settings
    stt_engine = _load_local_stt("stt_eng", "stt_engine.py").stt_engine

logger = logging.getLogger("aip.data-plane.stt.grpc")


class SttGrpcServicer(stt_pb2_grpc.SttServiceServicer):
    """Implementation of AIP SttService for STT Microservice (:50052)."""

    def __init__(self):
        self._active_tasks: Dict[str, asyncio.Task] = {}

    async def TranscribeAudio(
        self,
        request: stt_pb2.TranscriptionRequest,
        context: grpc.aio.ServicerContext,
    ) -> stt_pb2.TranscriptionResponse:
        """Transcribes binary raw audio bytes via Faster-Whisper."""
        task_id = f"stt_{int(time.time() * 1000)}"
        current_task = asyncio.current_task()
        if current_task:
            self._active_tasks[task_id] = current_task

        start_time = time.time()
        try:
            logger.info(
                "[gRPC STT] Transcribing audio len=%d bytes, format=%s, lang=%s",
                len(request.audio_data), request.format, request.language
            )

            res = await stt_engine.transcribe(
                audio_bytes=request.audio_data,
                filename=f"audio.{request.format or 'wav'}",
                language=request.language if request.language else None,
            )

            duration = (time.time() - start_time)
            return stt_pb2.TranscriptionResponse(
                text=res.text if hasattr(res, "text") else str(res),
                detected_language=res.language if hasattr(res, "language") else (request.language or "vi"),
                duration_seconds=float(duration),
            )
        except asyncio.CancelledError:
            logger.warning("[gRPC STT] Task %s was CANCELLED mid-transcription", task_id)
            context.set_code(grpc.StatusCode.CANCELLED)
            context.set_details(f"STT task {task_id} was cancelled")
            raise
        except Exception as exc:
            logger.exception("[gRPC STT] Error during transcription: %s", exc)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(exc))
            return stt_pb2.TranscriptionResponse(
                text="",
                detected_language="vi",
                duration_seconds=0.0,
            )
        finally:
            self._active_tasks.pop(task_id, None)

    async def GetHealth(
        self,
        request: common_pb2.HealthRequest,
        context: grpc.aio.ServicerContext,
    ) -> common_pb2.HealthResponse:
        """Health check for STT engine."""
        try:
            status_info = stt_engine.get_status()
            is_healthy = status_info.get("status") == "healthy" or os.getenv("TEST_MODE") == "true"
            status_str = "SERVING" if is_healthy else "NOT_SERVING"

            metadata = {
                "service": "stt-server",
                "backend": str(status_info.get("backend", "Faster-Whisper")),
                "device": str(status_info.get("device", "cpu")),
            }
            return common_pb2.HealthResponse(
                status=status_str,
                active_tasks=len(self._active_tasks),
                metadata=metadata,
            )
        except Exception as exc:
            return common_pb2.HealthResponse(
                status="NOT_SERVING",
                active_tasks=len(self._active_tasks),
                metadata={"error": str(exc)},
            )

    async def Cancel(
        self,
        request: common_pb2.CancelRequest,
        context: grpc.aio.ServicerContext,
    ) -> common_pb2.CancelResponse:
        """Cancels running audio transcription."""
        task_id = request.task_id
        target_task = self._active_tasks.get(task_id)
        if target_task and not target_task.done():
            target_task.cancel()
            return common_pb2.CancelResponse(
                success=True,
                message=f"STT task {task_id} successfully cancelled",
                task_id=task_id,
            )
        return common_pb2.CancelResponse(
            success=False,
            message=f"Task {task_id} not running",
            task_id=task_id,
        )


async def create_stt_grpc_server(host: str = "0.0.0.0", port: int = 50052) -> grpc.aio.Server:
    server = grpc.aio.server(
        options=[
            ("grpc.max_receive_message_length", 100 * 1024 * 1024),
            ("grpc.max_send_message_length", 100 * 1024 * 1024),
            ("grpc.keepalive_time_ms", 30000),
        ]
    )
    servicer = SttGrpcServicer()
    stt_pb2_grpc.add_SttServiceServicer_to_server(servicer, server)
    bind_addr = f"{host}:{port}"
    server.add_insecure_port(bind_addr)
    logger.info("[gRPC STT] Dedicated SttService bound to %s", bind_addr)
    return server
