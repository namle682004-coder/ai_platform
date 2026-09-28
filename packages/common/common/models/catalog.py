"""
Official AI Inference Platform (AIP) Enterprise Model Catalog & Alias System.
Standardized for local multi-model serving on 4GB VRAM GPU.
"""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class ModelAlias(BaseModel):
    id: str = Field(..., description="Unique logical alias identifier invoked by downstream clients")
    physical_model: str = Field(..., description="Physical weights / base foundation model")
    runtime: str = Field(..., description="Target execution runtime engine (vLLM, CTranslate2, Triton, etc.)")
    namespace: str = Field(..., description="Target Kubernetes namespace")
    min_vram_gb: int = Field(..., description="Minimum dedicated GPU VRAM requirements in GB")
    timeout_seconds: int = Field(default=60, description="Inference timeout before gateway 504")
    active_version: str = Field(default="v1.0", description="Currently routed production version")
    stream_capable: bool = Field(default=False, description="Whether runtime natively supports SSE chunk streaming")
    category: Literal["llm", "embedding", "translation", "stt", "tts", "vision", "idp", "image_gen", "video_gen", "lipsync", "moderation", "lid"]
    description: str = Field(..., description="Enterprise use-case specification")
    target_url: str = Field(..., description="Internal service/runtime HTTP endpoint")
    status: str = Field(default="active", description="Operational status: active, deprecated, disabled")


# Standardized 7 Core Models matching real local weights on disk
AIP_MODEL_CATALOG: dict[str, ModelAlias] = {
    # 1. Text / LLM & Reasoning
    "chat-general-standard": ModelAlias(
        id="chat-general-standard",
        physical_model="Qwen2.5-1.5B-Instruct",
        runtime="vLLM",
        namespace="aip-text",
        min_vram_gb=2,
        timeout_seconds=120,
        active_version="v1.0",
        stream_capable=True,
        category="llm",
        description="Standard OpenAI-compatible Chat Completions (/v1/chat/completions) via Qwen2.5-1.5B-Instruct",
        target_url="http://vllm-engine:8001/v1",
        status="active",
    ),

    # 2. Embeddings & Semantic Search
    "embed-standard": ModelAlias(
        id="embed-standard",
        physical_model="Qwen/Qwen2.5-1.5B-Instruct (mean-pooled embeddings)",
        runtime="transformers-embeddings",
        namespace="aip-text",
        min_vram_gb=0,
        timeout_seconds=30,
        active_version="v1.0",
        stream_capable=False,
        category="embedding",
        description="Mean-pooled normalized embeddings from the configured Transformers model (/v1/embeddings)",
        target_url="http://vllm-engine:8001/v1",
        status="active",
    ),

    # 3. Translation & NLP
    "translate-vi-standard": ModelAlias(
        id="translate-vi-standard",
        physical_model="opus-mt-vi-en",
        runtime="ctranslate2",
        namespace="aip-text",
        min_vram_gb=1,
        timeout_seconds=30,
        active_version="v1.0",
        stream_capable=False,
        category="translation",
        description="Bidirectional Vietnamese - English machine translation (/v1/nlp/translation)",
        target_url="http://translation-server:8003/v1",
        status="active",
    ),

    # 4. Speech & Audio (STT & TTS)
    "stt-vn-standard": ModelAlias(
        id="stt-vn-standard",
        physical_model="faster-whisper-small",
        runtime="Faster-Whisper",
        namespace="aip-multimodal",
        min_vram_gb=0,
        timeout_seconds=60,
        active_version="v1.0",
        stream_capable=False,
        category="stt",
        description="Vietnamese & Multilingual Speech-to-Text inference (/v1/audio/transcriptions) via Faster-Whisper",
        target_url="http://stt-server:8002/v1",
        status="active",
    ),
    "tts-vi-standard": ModelAlias(
        id="tts-vi-standard",
        physical_model="vi-VN-Neural",
        runtime="tts-adapter",
        namespace="aip-multimodal",
        min_vram_gb=0,
        timeout_seconds=30,
        active_version="v1.0",
        stream_capable=True,
        category="tts",
        description="Natural Vietnamese neural speech synthesis (/v1/audio/speech) with male/female regional voices",
        target_url="http://tts-adapter:8007/v1",
        status="active",
    ),

    # 5. Vision & Document AI (CCCD OCR)
    "idp-standard": ModelAlias(
        id="idp-standard",
        physical_model="EasyOCR-Vietnamese-ID",
        runtime="ocr-server",
        namespace="aip-multimodal",
        min_vram_gb=2,
        timeout_seconds=30,
        active_version="v1.0",
        stream_capable=False,
        category="idp",
        description="National Citizen ID Card (CCCD) OCR & QR extraction (/v1/ocr/id-card)",
        target_url="http://ocr-server:8004/v1",
        status="active",
    ),

    # 6. Safety & Moderation
    "moderation-multimodal": ModelAlias(
        id="moderation-multimodal",
        physical_model="PhoBERT-base + Rule Engine",
        runtime="moderation-server",
        namespace="aip-multimodal",
        min_vram_gb=1,
        timeout_seconds=15,
        active_version="v1.0",
        stream_capable=False,
        category="moderation",
        description="Content moderation (/v1/moderations) for hate speech, harassment, violence, sexual, and self-harm",
        target_url="http://moderation-server:8006/v1",
        status="active",
    ),
}
