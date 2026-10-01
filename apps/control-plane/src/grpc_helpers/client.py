"""
Enterprise Asynchronous gRPC Client Manager for AIP Control Plane.
Compliant with Clean Architecture contracts, HTTP/2 multiplexing, ISP, and dedicated per-service Protocol Buffers stubs.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional
import grpc

from contracts.generated import (
    common_pb2,
    jobs_pb2,
    jobs_pb2_grpc,
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

logger = logging.getLogger("aip-grpc.client")

# Channel options for high-throughput AI streaming and binary payload transport
GRPC_CHANNEL_OPTIONS = [
    ("grpc.max_receive_message_length", 100 * 1024 * 1024),
    ("grpc.max_send_message_length", 100 * 1024 * 1024),
    ("grpc.keepalive_time_ms", 30000),
    ("grpc.keepalive_timeout_ms", 10000),
    ("grpc.http2.min_time_between_pings_ms", 10000),
    ("grpc.http2.max_pings_without_data", 0),
]


class GrpcClientManager:
    """
    Enterprise Async gRPC Client Manager for AIP Control Plane.
    Manages connection pooling, HTTP/2 multiplexing, and typed RPC stubs to private data-plane runtimes.
    """

    def __init__(self):
        self._channels: Dict[str, grpc.aio.Channel] = {}
        self._llm_stubs: Dict[str, llm_pb2_grpc.LlmServiceStub] = {}
        self._trans_stubs: Dict[str, translation_pb2_grpc.TranslationServiceStub] = {}
        self._stt_stubs: Dict[str, stt_pb2_grpc.SttServiceStub] = {}
        self._tts_stubs: Dict[str, tts_pb2_grpc.TtsServiceStub] = {}
        self._ocr_stubs: Dict[str, ocr_pb2_grpc.OcrServiceStub] = {}
        self._job_stubs: Dict[str, jobs_pb2_grpc.JobServiceStub] = {}
        self._inference_stubs: Dict[str, Any] = {}

    def _normalize_target(self, target_url: str) -> str:
        clean = target_url.strip()
        if clean.startswith("http://"):
            clean = clean[len("http://"):]
        elif clean.startswith("https://"):
            clean = clean[len("https://"):]
        if clean.endswith("/"):
            clean = clean[:-1]
        return clean

    def get_channel(self, target_url: str) -> grpc.aio.Channel:
        target = self._normalize_target(target_url)
        if target not in self._channels:
            logger.info(f"[gRPC] Initializing persistent async gRPC channel to {target}")
            self._channels[target] = grpc.aio.insecure_channel(target, options=GRPC_CHANNEL_OPTIONS)
        return self._channels[target]

    def get_llm_stub(self, target_url: str) -> llm_pb2_grpc.LlmServiceStub:
        target = self._normalize_target(target_url)
        if target not in self._llm_stubs:
            self._llm_stubs[target] = llm_pb2_grpc.LlmServiceStub(self.get_channel(target))
        return self._llm_stubs[target]

    def get_translation_stub(self, target_url: str) -> translation_pb2_grpc.TranslationServiceStub:
        target = self._normalize_target(target_url)
        if target not in self._trans_stubs:
            self._trans_stubs[target] = translation_pb2_grpc.TranslationServiceStub(self.get_channel(target))
        return self._trans_stubs[target]

    def get_stt_stub(self, target_url: str) -> stt_pb2_grpc.SttServiceStub:
        target = self._normalize_target(target_url)
        if target not in self._stt_stubs:
            self._stt_stubs[target] = stt_pb2_grpc.SttServiceStub(self.get_channel(target))
        return self._stt_stubs[target]

    def get_tts_stub(self, target_url: str) -> tts_pb2_grpc.TtsServiceStub:
        target = self._normalize_target(target_url)
        if target not in self._tts_stubs:
            self._tts_stubs[target] = tts_pb2_grpc.TtsServiceStub(self.get_channel(target))
        return self._tts_stubs[target]

    def get_ocr_stub(self, target_url: str) -> ocr_pb2_grpc.OcrServiceStub:
        target = self._normalize_target(target_url)
        if target not in self._ocr_stubs:
            self._ocr_stubs[target] = ocr_pb2_grpc.OcrServiceStub(self.get_channel(target))
        return self._ocr_stubs[target]

    def get_job_stub(self, target_url: str) -> jobs_pb2_grpc.JobServiceStub:
        target = self._normalize_target(target_url)
        if target not in self._job_stubs:
            self._job_stubs[target] = jobs_pb2_grpc.JobServiceStub(self.get_channel(target))
        return self._job_stubs[target]

    def get_inference_stub(self, target_url: str):
        target = self._normalize_target(target_url)
        if target not in self._inference_stubs:
            from contracts.generated.inference_pb2_grpc import InferenceServiceStub
            self._inference_stubs[target] = InferenceServiceStub(self.get_channel(target))
        return self._inference_stubs[target]

    async def translate(
        self,
        target_url: str,
        text: str,
        source_lang: str,
        target_lang: str,
        model_alias: str = "translate-vi-standard",
        timeout: float = 30.0,
    ) -> translation_pb2.TranslationResponse:
        """Execute synchronous gRPC translation against target runtime."""
        stub = self.get_translation_stub(target_url)
        request = translation_pb2.TranslationRequest(
            text=text,
            source_lang=source_lang,
            target_lang=target_lang,
            model_alias=model_alias,
        )
        return await stub.Translate(request, timeout=timeout)

    async def chat_completion(
        self,
        target_url: str,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 512,
        timeout: float = 60.0,
    ) -> llm_pb2.ChatResponse:
        """Execute synchronous gRPC chat completion."""
        stub = self.get_llm_stub(target_url)
        proto_messages = [
            llm_pb2.ChatMessage(role=m.get("role", "user"), content=m.get("content", ""))
            for m in messages
        ]
        request = llm_pb2.ChatRequest(
            model=model,
            messages=proto_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return await stub.ChatCompletion(request, timeout=timeout)

    async def transcribe_audio(
        self,
        target_url: str,
        audio_data: bytes,
        format: str = "wav",
        language: str = "vi",
        model_alias: str = "stt-vn-standard",
        timeout: float = 60.0,
    ) -> stt_pb2.TranscriptionResponse:
        """Execute binary raw-bytes audio transcription via gRPC."""
        stub = self.get_stt_stub(target_url)
        request = stt_pb2.TranscriptionRequest(
            audio_data=audio_data,
            format=format,
            language=language,
            model_alias=model_alias,
        )
        return await stub.TranscribeAudio(request, timeout=timeout)

    async def synthesize_speech(
        self,
        target_url: str,
        text: str,
        voice: str = "vi-VN-Neural",
        format: str = "mp3",
        model_alias: str = "tts-vi-standard",
        timeout: float = 30.0,
    ) -> tts_pb2.SpeechResponse:
        """Execute binary speech synthesis via gRPC."""
        stub = self.get_tts_stub(target_url)
        request = tts_pb2.SpeechRequest(
            text=text,
            voice=voice,
            format=format,
            model_alias=model_alias,
        )
        return await stub.SynthesizeSpeech(request, timeout=timeout)

    async def cancel_inference(
        self,
        target_url: str,
        task_id: str,
        domain: str = "translation",
        reason: str = "Client requested cancellation",
        timeout: float = 5.0,
    ) -> common_pb2.CancelResponse:
        """Cancel running inference on specific Data-Plane runtime via gRPC."""
        request = common_pb2.CancelRequest(task_id=task_id, reason=reason)
        if domain in ("llm", "chat"):
            return await self.get_llm_stub(target_url).Cancel(request, timeout=timeout)
        elif domain == "translation":
            return await self.get_translation_stub(target_url).Cancel(request, timeout=timeout)
        elif domain == "stt":
            return await self.get_stt_stub(target_url).Cancel(request, timeout=timeout)
        elif domain == "tts":
            return await self.get_tts_stub(target_url).Cancel(request, timeout=timeout)
        elif domain == "ocr":
            return await self.get_ocr_stub(target_url).Cancel(request, timeout=timeout)
        else:
            return common_pb2.CancelResponse(success=False, message=f"Unknown domain {domain}", task_id=task_id)

    async def get_health(
        self,
        target_url: str,
        domain: str = "translation",
        service: str = "data-plane",
        timeout: float = 5.0,
    ) -> common_pb2.HealthResponse:
        """Query typed health status of Data-Plane runtime via gRPC."""
        request = common_pb2.HealthRequest(service=service)
        if domain in ("llm", "chat"):
            return await self.get_llm_stub(target_url).GetHealth(request, timeout=timeout)
        elif domain == "translation":
            return await self.get_translation_stub(target_url).GetHealth(request, timeout=timeout)
        elif domain == "stt":
            return await self.get_stt_stub(target_url).GetHealth(request, timeout=timeout)
        elif domain == "tts":
            return await self.get_tts_stub(target_url).GetHealth(request, timeout=timeout)
        elif domain == "ocr":
            return await self.get_ocr_stub(target_url).GetHealth(request, timeout=timeout)
        else:
            return common_pb2.HealthResponse(status="UNKNOWN_DOMAIN", active_tasks=0)

    async def submit_job(
        self,
        target_url: str,
        job_type: str,
        alias_name: str,
        payload_bytes: bytes,
        priority: str = "normal",
        webhook_url: str = "",
        idempotency_key: str = "",
        timeout: float = 10.0,
    ) -> jobs_pb2.JobStatusResponse:
        stub = self.get_job_stub(target_url)
        request = jobs_pb2.JobSubmitRequest(
            job_type=job_type,
            alias_name=alias_name,
            priority=priority,
            webhook_url=webhook_url,
            idempotency_key=idempotency_key,
            payload_json=payload_bytes,
        )
        return await stub.SubmitJob(request, timeout=timeout)

    async def get_job_status(
        self,
        target_url: str,
        job_id: str,
        timeout: float = 5.0,
    ) -> jobs_pb2.JobStatusResponse:
        stub = self.get_job_stub(target_url)
        request = jobs_pb2.JobQueryRequest(job_id=job_id)
        return await stub.GetJobStatus(request, timeout=timeout)

    async def cancel_job(
        self,
        target_url: str,
        job_id: str,
        timeout: float = 5.0,
    ) -> jobs_pb2.JobCancelResponse:
        stub = self.get_job_stub(target_url)
        request = jobs_pb2.JobCancelRequest(job_id=job_id)
        return await stub.CancelJob(request, timeout=timeout)

    async def close(self):
        """Gracefully close all open gRPC channels."""
        logger.info(f"[gRPC] Closing {len(self._channels)} active gRPC channels...")
        for target, channel in self._channels.items():
            try:
                await channel.close()
            except Exception as exc:
                logger.debug(f"[gRPC] Error closing channel to {target}: {exc}")
        self._channels.clear()
        self._llm_stubs.clear()
        self._trans_stubs.clear()
        self._stt_stubs.clear()
        self._tts_stubs.clear()
        self._ocr_stubs.clear()
        self._job_stubs.clear()
        self._inference_stubs.clear()


grpc_manager = GrpcClientManager()
