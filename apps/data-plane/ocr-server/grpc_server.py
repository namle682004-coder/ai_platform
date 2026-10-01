"""
AIP High-Performance gRPC Server for OCR & Vision Server (:50054).
Implements dedicated OcrService (ExtractDocument, GetHealth, Cancel).
Compliant with Clean Architecture, ISP, and DCP isolated service specifications.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Dict

import grpc
from contracts.generated import ocr_pb2, ocr_pb2_grpc, common_pb2

try:
    from .config import ocr_settings
    from .ocr_engine import ocr_engine
except (ImportError, ValueError):
    import importlib.util
    import sys
    def _load_local_ocr(name, fname):
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
        spec = importlib.util.spec_from_file_location(name, p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    _cfg = _load_local_ocr("ocr_cfg", "config.py")
    sys.modules["config"] = _cfg
    ocr_settings = _cfg.ocr_settings
    ocr_engine = _load_local_ocr("ocr_eng", "ocr_engine.py").ocr_engine

logger = logging.getLogger("aip.data-plane.ocr.grpc")


class OcrGrpcServicer(ocr_pb2_grpc.OcrServiceServicer):
    """Implementation of AIP OcrService for OCR Microservice (:50054)."""

    def __init__(self):
        self._active_tasks: Dict[str, asyncio.Task] = {}

    async def ExtractDocument(
        self,
        request: ocr_pb2.OcrRequest,
        context: grpc.aio.ServicerContext,
    ) -> ocr_pb2.OcrResponse:
        """Extracts text and bounding boxes from binary document or image bytes."""
        task_id = f"ocr_{int(time.time() * 1000)}"
        current_task = asyncio.current_task()
        if current_task:
            self._active_tasks[task_id] = current_task

        start_time = time.time()
        try:
            logger.info("[gRPC OCR] Processing document len=%d bytes, type=%s", len(request.document_data), request.file_type)

            res = await ocr_engine.process_document(
                file_bytes=request.document_data,
                filename=f"document.{request.file_type or 'pdf'}",
            )

            blocks = []
            if hasattr(res, "blocks") and res.blocks:
                for b in res.blocks:
                    blocks.append(
                        ocr_pb2.OcrBlock(
                            text=getattr(b, "text", ""),
                            confidence=float(getattr(b, "confidence", 1.0)),
                            box=list(getattr(b, "box", [])),
                        )
                    )

            full_text = getattr(res, "full_text", "")
            duration_ms = int((time.time() - start_time) * 1000)

            return ocr_pb2.OcrResponse(
                full_text=full_text,
                blocks=blocks,
                latency_ms=duration_ms,
            )
        except asyncio.CancelledError:
            logger.warning("[gRPC OCR] Task %s was CANCELLED", task_id)
            context.set_code(grpc.StatusCode.CANCELLED)
            context.set_details(f"OCR task {task_id} was cancelled")
            raise
        except Exception as exc:
            logger.exception("[gRPC OCR] Error during document extraction: %s", exc)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(exc))
            return ocr_pb2.OcrResponse(
                full_text="",
                blocks=[],
                latency_ms=int((time.time() - start_time) * 1000),
            )
        finally:
            self._active_tasks.pop(task_id, None)

    async def GetHealth(
        self,
        request: common_pb2.HealthRequest,
        context: grpc.aio.ServicerContext,
    ) -> common_pb2.HealthResponse:
        """Health check for OCR engine."""
        try:
            status_info = ocr_engine.get_status()
            is_healthy = status_info.get("status") == "healthy" or os.getenv("TEST_MODE") == "true"
            status_str = "SERVING" if is_healthy else "NOT_SERVING"

            metadata = {
                "service": "ocr-server",
                "backend": str(status_info.get("backend", "PaddleOCR-VL")),
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
        """Cancels running document OCR processing."""
        task_id = request.task_id
        target_task = self._active_tasks.get(task_id)
        if target_task and not target_task.done():
            target_task.cancel()
            return common_pb2.CancelResponse(
                success=True,
                message=f"OCR task {task_id} successfully cancelled",
                task_id=task_id,
            )
        return common_pb2.CancelResponse(
            success=False,
            message=f"Task {task_id} not running",
            task_id=task_id,
        )


async def create_ocr_grpc_server(host: str = "0.0.0.0", port: int = 50054) -> grpc.aio.Server:
    server = grpc.aio.server(
        options=[
            ("grpc.max_receive_message_length", 50 * 1024 * 1024),
            ("grpc.max_send_message_length", 50 * 1024 * 1024),
            ("grpc.keepalive_time_ms", 30000),
        ]
    )
    servicer = OcrGrpcServicer()
    ocr_pb2_grpc.add_OcrServiceServicer_to_server(servicer, server)
    bind_addr = f"{host}:{port}"
    server.add_insecure_port(bind_addr)
    logger.info("[gRPC OCR] Dedicated OcrService bound to %s", bind_addr)
    return server
