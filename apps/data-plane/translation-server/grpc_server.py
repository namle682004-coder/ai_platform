"""
AIP High-Performance gRPC Server for Translation Data-Plane Microservice (:50053).
Implements dedicated TranslationService (Translate, GetHealth, Cancel).
Compliant with Clean Architecture, ISP, and DCP isolated service specifications.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict

import grpc
from contracts.generated import translation_pb2, translation_pb2_grpc, common_pb2

try:
    from .config import translation_settings
    from .translation_engine import translation_engine
except (ImportError, ValueError):
    from config import translation_settings
    from translation_engine import translation_engine

logger = logging.getLogger("aip.data-plane.translation.grpc")


class TranslationGrpcServicer(translation_pb2_grpc.TranslationServiceServicer):
    """Implementation of AIP TranslationService for Translation Microservice (:50053)."""

    def __init__(self):
        self._active_tasks: Dict[str, asyncio.Task] = {}

    async def Translate(
        self,
        request: translation_pb2.TranslationRequest,
        context: grpc.aio.ServicerContext,
    ) -> translation_pb2.TranslationResponse:
        """Executes binary gRPC translation inference."""
        task_id = f"trans_{int(time.time() * 1000)}"
        current_task = asyncio.current_task()
        if current_task:
            self._active_tasks[task_id] = current_task

        start_time = time.time()
        try:
            logger.info(
                "[gRPC Translation] Received task_id=%s, src=%s, tgt=%s, len=%d",
                task_id,
                request.source_lang,
                request.target_lang,
                len(request.text),
            )

            src = "vie_Latn" if request.source_lang == "vi" else ("eng_Latn" if request.source_lang == "en" else request.source_lang)
            tgt = "eng_Latn" if request.target_lang == "en" else ("vie_Latn" if request.target_lang == "vi" else request.target_lang)

            res = await translation_engine.translate_text(
                text=request.text,
                source_lang=src,
                target_lang=tgt,
                beam_size=4,
            )

            duration_ms = int((time.time() - start_time) * 1000)

            return translation_pb2.TranslationResponse(
                status="success",
                translated_text=res["translated_text"],
                engine=res.get("backend", "CTranslate2 Native"),
                duration_ms=duration_ms,
                source_lang=request.source_lang,
                target_lang=request.target_lang,
                latency_ms=duration_ms,
            )
        except asyncio.CancelledError:
            logger.warning("[gRPC Translation] Task %s was CANCELLED mid-execution", task_id)
            context.set_code(grpc.StatusCode.CANCELLED)
            context.set_details(f"Translation task {task_id} was cancelled by client")
            raise
        except Exception as exc:
            logger.exception("[gRPC Translation] Error during inference: %s", exc)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(exc))
            return translation_pb2.TranslationResponse(
                status="error",
                translated_text="",
                engine="CTranslate2",
                duration_ms=int((time.time() - start_time) * 1000),
            )
        finally:
            self._active_tasks.pop(task_id, None)

    async def GetHealth(
        self,
        request: common_pb2.HealthRequest,
        context: grpc.aio.ServicerContext,
    ) -> common_pb2.HealthResponse:
        """Health check endpoint for Translation Microservice."""
        try:
            status_info = translation_engine.get_status()
            is_healthy = status_info.get("status") == "healthy"
            status_str = "SERVING" if is_healthy else "NOT_SERVING"

            metadata = {
                "service": translation_settings.service_name,
                "model": translation_settings.model_name,
                "backend": str(status_info.get("backend", "CTranslate2")),
                "device": str(status_info.get("device", "cpu")),
            }

            return common_pb2.HealthResponse(
                status=status_str,
                active_tasks=len(self._active_tasks),
                metadata=metadata,
            )
        except Exception as exc:
            logger.error("[gRPC Translation] Health check failed: %s", exc)
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
        """Stops active inference execution on GPU to free compute resources."""
        task_id = request.task_id
        target_task = self._active_tasks.get(task_id)
        if target_task and not target_task.done():
            target_task.cancel()
            return common_pb2.CancelResponse(
                success=True,
                message=f"Inference task {task_id} successfully cancelled",
                task_id=task_id,
            )

        return common_pb2.CancelResponse(
            success=False,
            message=f"Task {task_id} not found in active running tasks or already completed",
            task_id=task_id,
        )


async def create_grpc_server(host: str = "0.0.0.0", port: int = 50053) -> grpc.aio.Server:
    server = grpc.aio.server(
        options=[
            ("grpc.max_receive_message_length", 50 * 1024 * 1024),
            ("grpc.max_send_message_length", 50 * 1024 * 1024),
            ("grpc.keepalive_time_ms", 30000),
            ("grpc.keepalive_timeout_ms", 10000),
        ]
    )
    servicer = TranslationGrpcServicer()
    translation_pb2_grpc.add_TranslationServiceServicer_to_server(servicer, server)

    bind_address = f"{host}:{port}"
    server.add_insecure_port(bind_address)
    logger.info("[gRPC Translation] Dedicated TranslationService bound to %s", bind_address)
    return server
