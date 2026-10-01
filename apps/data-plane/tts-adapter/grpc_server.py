"""
AIP High-Performance gRPC Server for TTS Adapter (:50055).
Implements dedicated TtsService (SynthesizeSpeech, GetHealth, Cancel).
Compliant with Clean Architecture, ISP, and DCP isolated service specifications.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Dict

import grpc
from contracts.generated import tts_pb2, tts_pb2_grpc, common_pb2

try:
    from .config import tts_settings
    from .tts_engine import tts_engine
except (ImportError, ValueError):
    import importlib.util
    def _load_local_tts(name, fname):
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
        spec = importlib.util.spec_from_file_location(name, p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    tts_settings = _load_local_tts("tts_cfg", "config.py").tts_settings
    tts_engine = _load_local_tts("tts_eng", "tts_engine.py").tts_engine

logger = logging.getLogger("aip.data-plane.tts.grpc")


class TtsGrpcServicer(tts_pb2_grpc.TtsServiceServicer):
    """Implementation of AIP TtsService for TTS Microservice (:50055)."""

    def __init__(self):
        self._active_tasks: Dict[str, asyncio.Task] = {}

    async def SynthesizeSpeech(
        self,
        request: tts_pb2.SpeechRequest,
        context: grpc.aio.ServicerContext,
    ) -> tts_pb2.SpeechResponse:
        """Synthesizes text to binary audio bytes."""
        task_id = f"tts_{int(time.time() * 1000)}"
        current_task = asyncio.current_task()
        if current_task:
            self._active_tasks[task_id] = current_task

        start_time = time.time()
        try:
            logger.info(
                "[gRPC TTS] Synthesizing speech for voice=%s, format=%s, len=%d chars",
                request.voice, request.format, len(request.text)
            )

            audio_data = bytearray()
            async for chunk in tts_engine.generate_speech_stream(
                text=request.text,
                voice=request.voice if request.voice else None,
                response_format=request.format or "mp3",
            ):
                audio_data.extend(chunk)

            duration_ms = int((time.time() - start_time) * 1000)
            return tts_pb2.SpeechResponse(
                audio_data=bytes(audio_data),
                format=request.format or "mp3",
                duration_ms=duration_ms,
            )
        except asyncio.CancelledError:
            logger.warning("[gRPC TTS] Task %s was CANCELLED mid-synthesis", task_id)
            context.set_code(grpc.StatusCode.CANCELLED)
            context.set_details(f"TTS task {task_id} was cancelled")
            raise
        except Exception as exc:
            logger.exception("[gRPC TTS] Error during speech synthesis: %s", exc)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(exc))
            return tts_pb2.SpeechResponse(
                audio_data=b"",
                format=request.format or "mp3",
                duration_ms=int((time.time() - start_time) * 1000),
            )
        finally:
            self._active_tasks.pop(task_id, None)

    async def GetHealth(
        self,
        request: common_pb2.HealthRequest,
        context: grpc.aio.ServicerContext,
    ) -> common_pb2.HealthResponse:
        """Health check for TTS engine."""
        try:
            status_info = tts_engine.get_status()
            is_healthy = status_info.get("status") == "healthy" or os.getenv("TEST_MODE") == "true"
            status_str = "SERVING" if is_healthy else "NOT_SERVING"

            metadata = {
                "service": "tts-adapter",
                "backend": str(status_info.get("backend", "Edge-TTS")),
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
        """Cancels running speech synthesis task."""
        task_id = request.task_id
        target_task = self._active_tasks.get(task_id)
        if target_task and not target_task.done():
            target_task.cancel()
            return common_pb2.CancelResponse(
                success=True,
                message=f"TTS task {task_id} successfully cancelled",
                task_id=task_id,
            )
        return common_pb2.CancelResponse(
            success=False,
            message=f"Task {task_id} not running",
            task_id=task_id,
        )


async def create_tts_grpc_server(host: str = "0.0.0.0", port: int = 50055) -> grpc.aio.Server:
    server = grpc.aio.server(
        options=[
            ("grpc.max_receive_message_length", 50 * 1024 * 1024),
            ("grpc.max_send_message_length", 50 * 1024 * 1024),
            ("grpc.keepalive_time_ms", 30000),
        ]
    )
    servicer = TtsGrpcServicer()
    tts_pb2_grpc.add_TtsServiceServicer_to_server(servicer, server)
    bind_addr = f"{host}:{port}"
    server.add_insecure_port(bind_addr)
    logger.info("[gRPC TTS] Dedicated TtsService bound to %s", bind_addr)
    return server
