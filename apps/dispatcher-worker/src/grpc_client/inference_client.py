"""
AIP Asynchronous gRPC Inference Client for Dispatcher Worker.
Communicates with Data Plane microservices using dedicated domain Protocol Buffers stubs.
Compliant with Clean Architecture, ISP, and DCP isolated service specifications.
"""

from __future__ import annotations

import logging
import os
from typing import Any, AsyncIterator, Dict, List

import grpc

try:
    from contracts.generated import (
        common_pb2,
        llm_pb2,
        llm_pb2_grpc,
        ocr_pb2,
        ocr_pb2_grpc,
        stt_pb2,
        stt_pb2_grpc,
        translation_pb2,
        translation_pb2_grpc,
        tts_pb2,
        tts_pb2_grpc,
    )
except (ImportError, ModuleNotFoundError):
    common_pb2 = None
    llm_pb2 = None
    llm_pb2_grpc = None
    ocr_pb2 = None
    ocr_pb2_grpc = None
    stt_pb2 = None
    stt_pb2_grpc = None
    translation_pb2 = None
    translation_pb2_grpc = None
    tts_pb2 = None
    tts_pb2_grpc = None

logger = logging.getLogger("aip-dispatcher.grpc-client")


class InferenceError(Exception):
    """Base exception for all inference execution failures."""
    pass


class InferenceTransientError(InferenceError):
    """Transient network/resource error eligible for delayed retry with backoff."""
    pass


class InferenceTerminalError(InferenceError):
    """Terminal business or argument error that should NOT be retried."""
    pass


class InferenceGrpcClient:
    """Dispatches binary gRPC requests from Worker to dedicated Data Plane microservices."""

    def __init__(self):
        self._channels: dict[str, grpc.aio.Channel] = {}
        self._llm_stubs: dict[str, llm_pb2_grpc.LlmServiceStub] = {}
        self._trans_stubs: dict[str, translation_pb2_grpc.TranslationServiceStub] = {}
        self._stt_stubs: dict[str, stt_pb2_grpc.SttServiceStub] = {}
        self._tts_stubs: dict[str, tts_pb2_grpc.TtsServiceStub] = {}
        self._ocr_stubs: dict[str, ocr_pb2_grpc.OcrServiceStub] = {}

    def _normalize(self, target: str) -> str:
        return target.replace("http://", "").replace("https://", "").rstrip("/")

    def _get_channel(self, target: str) -> grpc.aio.Channel:
        clean = self._normalize(target)
        if clean not in self._channels:
            logger.info("[Dispatcher gRPC] Connecting persistent channel to %s", clean)
            self._channels[clean] = grpc.aio.insecure_channel(
                clean,
                options=[
                    ("grpc.max_receive_message_length", 100 * 1024 * 1024),
                    ("grpc.max_send_message_length", 100 * 1024 * 1024),
                    ("grpc.keepalive_time_ms", 30000),
                ],
            )
        return self._channels[clean]

    def get_llm_stub(self, target: str) -> llm_pb2_grpc.LlmServiceStub:
        clean = self._normalize(target)
        if clean not in self._llm_stubs:
            self._llm_stubs[clean] = llm_pb2_grpc.LlmServiceStub(self._get_channel(clean))
        return self._llm_stubs[clean]

    def get_trans_stub(self, target: str) -> translation_pb2_grpc.TranslationServiceStub:
        clean = self._normalize(target)
        if clean not in self._trans_stubs:
            self._trans_stubs[clean] = translation_pb2_grpc.TranslationServiceStub(self._get_channel(clean))
        return self._trans_stubs[clean]

    def get_stt_stub(self, target: str) -> stt_pb2_grpc.SttServiceStub:
        clean = self._normalize(target)
        if clean not in self._stt_stubs:
            self._stt_stubs[clean] = stt_pb2_grpc.SttServiceStub(self._get_channel(clean))
        return self._stt_stubs[clean]

    def get_tts_stub(self, target: str) -> tts_pb2_grpc.TtsServiceStub:
        clean = self._normalize(target)
        if clean not in self._tts_stubs:
            self._tts_stubs[clean] = tts_pb2_grpc.TtsServiceStub(self._get_channel(clean))
        return self._tts_stubs[clean]

    def get_ocr_stub(self, target: str) -> ocr_pb2_grpc.OcrServiceStub:
        clean = self._normalize(target)
        if clean not in self._ocr_stubs:
            self._ocr_stubs[clean] = ocr_pb2_grpc.OcrServiceStub(self._get_channel(clean))
        return self._ocr_stubs[clean]

    async def execute_inference(
        self,
        target_endpoint: str,
        rpc_method: str,
        domain: str,
        alias_name: str,
        data: dict[str, Any],
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """
        Executes domain-specific RPC call to Data Plane.
        Strictly categorizes errors as Transient vs Terminal.
        """
        test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        if test_mode:
            logger.debug("[Dispatcher gRPC] TEST_MODE active: returning simulation for %s", domain)
            return {
                "output_text": f"Simulated gRPC response for domain={domain} (alias={alias_name})",
                "result_urls": [f"https://minio.internal/aip-job-artifacts/{domain}/output.dat"],
                "protocol": "grpc_simulation",
            }

        try:
            if rpc_method == "Translate":
                stub = self.get_trans_stub(target_endpoint)
                req = translation_pb2.TranslationRequest(
                    text=data.get("text", ""),
                    source_lang=data.get("source_lang", "vi"),
                    target_lang=data.get("target_lang", "en"),
                    model_alias=alias_name,
                )
                resp = await stub.Translate(req, timeout=timeout)
                return {
                    "translated_text": resp.translated_text,
                    "source_lang": resp.source_lang,
                    "target_lang": resp.target_lang,
                    "latency_ms": resp.latency_ms,
                    "engine": resp.engine,
                    "status": resp.status,
                    "protocol": "grpc",
                }

            elif rpc_method == "ChatCompletion":
                stub = self.get_llm_stub(target_endpoint)
                messages = [
                    llm_pb2.ChatMessage(role=m.get("role", "user"), content=m.get("content", ""))
                    for m in data.get("messages", [])
                ]
                req = llm_pb2.ChatRequest(
                    model=alias_name,
                    messages=messages,
                    temperature=float(data.get("temperature", 0.7)),
                    max_tokens=int(data.get("max_tokens", 256)),
                )
                resp = await stub.ChatCompletion(req, timeout=timeout)
                return {
                    "content": resp.content,
                    "finish_reason": resp.finish_reason,
                    "prompt_tokens": resp.prompt_tokens,
                    "completion_tokens": resp.completion_tokens,
                    "latency_ms": resp.latency_ms,
                    "protocol": "grpc",
                }

            elif rpc_method == "TranscribeAudio":
                stub = self.get_stt_stub(target_endpoint)
                audio_bytes = data.get("audio_data") or b""
                if isinstance(audio_bytes, str):
                    audio_bytes = audio_bytes.encode("utf-8")
                req = stt_pb2.TranscriptionRequest(
                    audio_data=audio_bytes,
                    format=data.get("format", "wav"),
                    language=data.get("language", "vi"),
                    model_alias=alias_name,
                )
                resp = await stub.TranscribeAudio(req, timeout=timeout)
                return {
                    "text": resp.text,
                    "detected_language": resp.detected_language,
                    "duration_seconds": resp.duration_seconds,
                    "protocol": "grpc",
                }

            elif rpc_method == "SynthesizeSpeech":
                stub = self.get_tts_stub(target_endpoint)
                req = tts_pb2.SpeechRequest(
                    text=data.get("text", ""),
                    voice=data.get("voice", "vi-VN-Neural"),
                    format=data.get("format", "mp3"),
                    model_alias=alias_name,
                )
                resp = await stub.SynthesizeSpeech(req, timeout=timeout)
                return {
                    "audio_length": len(resp.audio_data),
                    "format": resp.format,
                    "duration_ms": resp.duration_ms,
                    "protocol": "grpc",
                }

            elif rpc_method == "ExtractDocument":
                stub = self.get_ocr_stub(target_endpoint)
                doc_bytes = data.get("document_data") or b""
                if isinstance(doc_bytes, str):
                    doc_bytes = doc_bytes.encode("utf-8")
                req = ocr_pb2.OcrRequest(
                    document_data=doc_bytes,
                    file_type=data.get("file_type", "pdf"),
                    model_alias=alias_name,
                )
                resp = await stub.ExtractDocument(req, timeout=timeout)
                return {
                    "full_text": resp.full_text,
                    "blocks_count": len(resp.blocks),
                    "latency_ms": resp.latency_ms,
                    "protocol": "grpc",
                }

            else:
                raise InferenceTerminalError(f"Unsupported RPC method: {rpc_method} for domain: {domain}")

        except grpc.aio.AioRpcError as rpc_err:
            code = rpc_err.code()
            details = rpc_err.details() or str(rpc_err)
            logger.error("[Dispatcher gRPC] Call %s to %s failed [%s]: %s", rpc_method, target_endpoint, code, details)

            if code in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED, grpc.StatusCode.RESOURCE_EXHAUSTED):
                raise InferenceTransientError(f"Transient gRPC failure ({code.name}): {details}") from rpc_err
            elif code in (grpc.StatusCode.INVALID_ARGUMENT, grpc.StatusCode.NOT_FOUND, grpc.StatusCode.UNIMPLEMENTED, grpc.StatusCode.PERMISSION_DENIED):
                raise InferenceTerminalError(f"Terminal gRPC failure ({code.name}): {details}") from rpc_err
            else:
                raise InferenceError(f"Inference error ({code.name}): {details}") from rpc_err

        except (InferenceTransientError, InferenceTerminalError, InferenceError):
            raise
        except Exception as exc:
            logger.error("[Dispatcher gRPC] Unexpected error in %s to %s: %s", rpc_method, target_endpoint, exc)
            raise InferenceTransientError(f"Unexpected connection error to {target_endpoint}: {exc}") from exc

    async def stream_chat_completion(
        self,
        target_endpoint: str,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 512,
        timeout: float = 60.0,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Streams Chat completion token chunks asynchronously via dedicated LlmService."""
        test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        if test_mode:
            chunks = ["Xin ", "chào, ", "tôi ", "là ", "trợ ", "lý ", "AI."]
            for c in chunks:
                yield {
                    "id": "stream_sim",
                    "model": model,
                    "delta_content": c,
                    "is_final": c == chunks[-1],
                }
            return

        try:
            stub = self.get_llm_stub(target_endpoint)
            proto_messages = [
                llm_pb2.ChatMessage(role=m.get("role", "user"), content=m.get("content", ""))
                for m in messages
            ]
            req = llm_pb2.ChatRequest(
                model=model,
                messages=proto_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            async for chunk in stub.StreamChatCompletion(req, timeout=timeout):
                yield {
                    "id": chunk.id,
                    "model": chunk.model,
                    "delta_content": chunk.delta_content,
                    "is_final": chunk.is_final,
                    "finish_reason": chunk.finish_reason,
                }
        except grpc.aio.AioRpcError as rpc_err:
            code = rpc_err.code()
            details = rpc_err.details()
            logger.error("[Dispatcher gRPC Stream] Error [%s]: %s", code, details)
            if code in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
                raise InferenceTransientError(f"Streaming interrupted ({code.name}): {details}") from rpc_err
            raise InferenceError(f"Streaming error ({code.name}): {details}") from rpc_err

    async def cancel_inference(
        self,
        target_endpoint: str,
        domain: str,
        task_id: str,
        reason: str = "Client cancelled",
        timeout: float = 5.0,
    ) -> Dict[str, Any]:
        """Cancels running GPU inference task on targeted microservice."""
        try:
            req = common_pb2.CancelRequest(task_id=task_id, reason=reason)
            if domain in ("llm", "chat"):
                resp = await self.get_llm_stub(target_endpoint).Cancel(req, timeout=timeout)
            elif domain == "translation":
                resp = await self.get_trans_stub(target_endpoint).Cancel(req, timeout=timeout)
            elif domain == "stt":
                resp = await self.get_stt_stub(target_endpoint).Cancel(req, timeout=timeout)
            elif domain == "tts":
                resp = await self.get_tts_stub(target_endpoint).Cancel(req, timeout=timeout)
            elif domain == "ocr":
                resp = await self.get_ocr_stub(target_endpoint).Cancel(req, timeout=timeout)
            else:
                return {"success": False, "message": f"Unknown domain {domain}", "task_id": task_id}

            return {"success": resp.success, "message": resp.message, "task_id": resp.task_id}
        except Exception as exc:
            logger.warning("[Dispatcher gRPC Cancel] Failed to cancel %s on %s: %s", task_id, target_endpoint, exc)
            return {"success": False, "message": str(exc), "task_id": task_id}

    async def get_health(
        self,
        target_endpoint: str,
        domain: str = "llm",
        service_name: str = "data-plane",
        timeout: float = 5.0,
    ) -> Dict[str, Any]:
        """Queries health status of targeted Data-Plane microservice."""
        try:
            req = common_pb2.HealthRequest(service=service_name)
            if domain in ("llm", "chat"):
                resp = await self.get_llm_stub(target_endpoint).GetHealth(req, timeout=timeout)
            elif domain == "translation":
                resp = await self.get_trans_stub(target_endpoint).GetHealth(req, timeout=timeout)
            elif domain == "stt":
                resp = await self.get_stt_stub(target_endpoint).GetHealth(req, timeout=timeout)
            elif domain == "tts":
                resp = await self.get_tts_stub(target_endpoint).GetHealth(req, timeout=timeout)
            elif domain == "ocr":
                resp = await self.get_ocr_stub(target_endpoint).GetHealth(req, timeout=timeout)
            else:
                return {"status": "UNKNOWN_DOMAIN", "active_tasks": 0}

            return {
                "status": resp.status,
                "active_tasks": resp.active_tasks,
                "metadata": dict(resp.metadata),
            }
        except Exception as exc:
            logger.warning("[Dispatcher gRPC Health] Check failed for %s: %s", target_endpoint, exc)
            return {"status": "UNAVAILABLE", "active_tasks": 0, "error": str(exc)}

    async def close(self) -> None:
        """Gracefully close all open gRPC channels."""
        for channel in list(self._channels.values()):
            try:
                await channel.close()
            except Exception:
                pass
        self._channels.clear()
        self._llm_stubs.clear()
        self._trans_stubs.clear()
        self._stt_stubs.clear()
        self._tts_stubs.clear()
        self._ocr_stubs.clear()


inference_grpc_client = InferenceGrpcClient()
