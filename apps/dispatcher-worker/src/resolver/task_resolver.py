"""
AIP Task Resolver.
Maps domain tasks and model aliases to appropriate gRPC service endpoints in the Data Plane.
Compliant with DCP architectural principles and SRS Section 2.3 & 6.1.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RuntimeTarget:
    """Resolved runtime endpoint target metadata."""
    domain: str
    alias_name: str
    grpc_target: str
    rpc_method: str
    timeout_seconds: float = 30.0


# Default gRPC endpoint mappings for local 4GB VRAM GPU topology
DEFAULT_RUNTIME_ENDPOINTS = {
    "llm": os.getenv("VLLM_GRPC_TARGET", "vllm-engine:50051"),
    "chat": os.getenv("VLLM_GRPC_TARGET", "vllm-engine:50051"),
    "translation": os.getenv("TRANSLATION_GRPC_TARGET", "translation-server:50053"),
    "stt": os.getenv("STT_GRPC_TARGET", "stt-server:50052"),
    "tts": os.getenv("TTS_GRPC_TARGET", "tts-adapter:50055"),
    "ocr": os.getenv("OCR_GRPC_TARGET", "ocr-server:50054"),
    "moderation": os.getenv("MODERATION_GRPC_TARGET", "moderation-server:50056"),
}

# Method routing
DOMAIN_METHOD_MAP = {
    "llm": "ChatCompletion",
    "chat": "ChatCompletion",
    "translation": "Translate",
    "stt": "TranscribeAudio",
    "tts": "SynthesizeSpeech",
    "ocr": "ExtractDocument",
    "moderation": "CheckContent",
}


class TaskResolver:
    """Resolves task domain or alias to target gRPC endpoint."""

    def __init__(self, endpoint_overrides: Optional[dict[str, str]] = None):
        self._endpoints = {**DEFAULT_RUNTIME_ENDPOINTS, **(endpoint_overrides or {})}

    def resolve(self, domain: str, alias_name: Optional[str] = None) -> RuntimeTarget:
        """
        Resolve domain or alias to a target gRPC endpoint.
        Falls back to domain default if alias is unknown.
        """
        clean_domain = (domain or "llm").lower().replace("tasks.", "").replace("q.aip.tasks.", "")
        grpc_target = self._endpoints.get(clean_domain, "vllm-engine:50051")
        rpc_method = DOMAIN_METHOD_MAP.get(clean_domain, "ChatCompletion")

        return RuntimeTarget(
            domain=clean_domain,
            alias_name=alias_name or f"{clean_domain}-default",
            grpc_target=grpc_target,
            rpc_method=rpc_method,
            timeout_seconds=60.0 if clean_domain in ("llm", "stt") else 30.0,
        )


task_resolver = TaskResolver()
