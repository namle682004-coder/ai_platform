"""
Enterprise Asynchronous gRPC Client Manager for AIP Control Plane.
Compliant with clean architecture contracts, HTTP/2 multiplexing, and binary Protocol Buffers.
"""

from __future__ import annotations

import logging
import grpc

from contracts.generated.inference_pb2_grpc import InferenceServiceStub
from contracts.generated.jobs_pb2_grpc import JobServiceStub
from contracts.generated import inference_pb2, jobs_pb2

logger = logging.getLogger("aip-grpc.client")

# Channel options for high-throughput AI streaming and binary payload transport
GRPC_CHANNEL_OPTIONS = [
    ("grpc.max_receive_message_length", 100 * 1024 * 1024),  # 100 MB max for audio/video payloads
    ("grpc.max_send_message_length", 100 * 1024 * 1024),
    ("grpc.keepalive_time_ms", 30000),                      # 30s keepalive ping
    ("grpc.keepalive_timeout_ms", 10000),                   # 10s keepalive timeout
    ("grpc.http2.min_time_between_pings_ms", 10000),
    ("grpc.http2.max_pings_without_data", 0),
]


class GrpcClientManager:
    """
    Enterprise Async gRPC Client Manager for AIP Control Plane.
    Manages connection pooling, HTTP/2 multiplexing, and typed RPC stubs to private data-plane runtimes.
    """

    def __init__(self):
        self._channels: dict[str, grpc.aio.Channel] = {}
        self._inference_stubs: dict[str, InferenceServiceStub] = {}
        self._job_stubs: dict[str, JobServiceStub] = {}

    def _normalize_target(self, target_url: str) -> str:
        """Strip http:// or https:// scheme for gRPC channel target."""
        clean = target_url.strip()
        if clean.startswith("http://"):
            clean = clean[len("http://"):]
        elif clean.startswith("https://"):
            clean = clean[len("https://"):]
        if clean.endswith("/"):
            clean = clean[:-1]
        return clean

    def get_channel(self, target_url: str) -> grpc.aio.Channel:
        """Get or initialize a multiplexed async gRPC channel."""
        target = self._normalize_target(target_url)
        if target not in self._channels:
            logger.info(f"[gRPC] Initializing persistent async gRPC channel to {target}")
            self._channels[target] = grpc.aio.insecure_channel(target, options=GRPC_CHANNEL_OPTIONS)
        return self._channels[target]

    def get_inference_stub(self, target_url: str) -> InferenceServiceStub:
        """Returns typed InferenceServiceStub for synchronous fast-lane inference."""
        target = self._normalize_target(target_url)
        if target not in self._inference_stubs:
            channel = self.get_channel(target)
            self._inference_stubs[target] = InferenceServiceStub(channel)
        return self._inference_stubs[target]

    def get_job_stub(self, target_url: str) -> JobServiceStub:
        """Returns typed JobServiceStub for asynchronous job coordination."""
        target = self._normalize_target(target_url)
        if target not in self._job_stubs:
            channel = self.get_channel(target)
            self._job_stubs[target] = JobServiceStub(channel)
        return self._job_stubs[target]

    async def translate(
        self,
        target_url: str,
        text: str,
        source_lang: str,
        target_lang: str,
        model_alias: str = "translate-vi-standard",
        timeout: float = 30.0,
    ) -> inference_pb2.TranslationResponse:
        """Execute synchronous gRPC translation against target runtime."""
        stub = self.get_inference_stub(target_url)
        request = inference_pb2.TranslationRequest(
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
    ) -> inference_pb2.ChatResponse:
        """Execute synchronous gRPC chat completion."""
        stub = self.get_inference_stub(target_url)
        proto_messages = [
            inference_pb2.ChatMessage(role=m.get("role", "user"), content=m.get("content", ""))
            for m in messages
        ]
        request = inference_pb2.ChatRequest(
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
    ) -> inference_pb2.TranscriptionResponse:
        """Execute binary raw-bytes audio transcription via gRPC."""
        stub = self.get_inference_stub(target_url)
        request = inference_pb2.TranscriptionRequest(
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
    ) -> inference_pb2.SpeechResponse:
        """Execute binary speech synthesis via gRPC."""
        stub = self.get_inference_stub(target_url)
        request = inference_pb2.SpeechRequest(
            text=text,
            voice=voice,
            format=format,
            model_alias=model_alias,
        )
        return await stub.SynthesizeSpeech(request, timeout=timeout)

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
        """Submit asynchronous job via gRPC."""
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
        """Query job status via gRPC."""
        stub = self.get_job_stub(target_url)
        request = jobs_pb2.JobQueryRequest(job_id=job_id)
        return await stub.GetJobStatus(request, timeout=timeout)

    async def cancel_job(
        self,
        target_url: str,
        job_id: str,
        timeout: float = 5.0,
    ) -> jobs_pb2.JobCancelResponse:
        """Cancel asynchronous job via gRPC."""
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
        self._inference_stubs.clear()
        self._job_stubs.clear()


grpc_manager = GrpcClientManager()
