import asyncio
import logging
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aip-seed")

MONGO_URI = "mongodb+srv://namle:1234@namle.52nsi1k.mongodb.net/ai_platform?appName=namle"
DB_NAME = "ai_platform"

DEFAULT_ALIASES = [
    {"alias_name": "chat-general-standard", "model_name": "Qwen3-8B", "runtime": "vllm", "min_vram_gb": 24, "status": "enabled"},
    {"alias_name": "chat-general-high-quality", "model_name": "Qwen3-14B", "runtime": "vllm", "min_vram_gb": 32, "status": "enabled"},
    {"alias_name": "embed-standard", "model_name": "Qwen3-Embedding-8B", "runtime": "vllm", "min_vram_gb": 24, "status": "enabled"},
    {"alias_name": "embed-cost-optimized", "model_name": "bge-m3", "runtime": "triton", "min_vram_gb": 8, "status": "enabled"},
    {"alias_name": "translate-vi-standard", "model_name": "NLLB-200 3.3B", "runtime": "ctranslate2", "min_vram_gb": 16, "status": "enabled"},
    {"alias_name": "stt-vn-standard", "model_name": "PhoWhisper", "runtime": "faster-whisper", "min_vram_gb": 16, "status": "enabled"},
    {"alias_name": "tts-vi-standard", "model_name": "viXTTS", "runtime": "tts-adapter", "min_vram_gb": 16, "status": "enabled"},
    {"alias_name": "idp-standard", "model_name": "PaddleOCR-VL", "runtime": "ocr-server", "min_vram_gb": 16, "status": "enabled"},
    {"alias_name": "image-gen-standard", "model_name": "FLUX.1-schnell", "runtime": "image-worker", "min_vram_gb": 24, "status": "enabled"},
    {"alias_name": "video-gen-standard", "model_name": "Wan2.2 T2V-A14B", "runtime": "video-worker", "min_vram_gb": 80, "status": "enabled"},
    {"alias_name": "moderation-multimodal", "model_name": "Llama Guard 4", "runtime": "moderation-server", "min_vram_gb": 24, "status": "enabled"},
]

DEFAULT_ENDPOINTS = [
    {"endpoint_id": "chat_completions", "path": "/v1/chat/completions", "method": "POST", "status": "enabled", "description": "LLM Chat Completions API"},
    {"endpoint_id": "text_completions", "path": "/v1/completions", "method": "POST", "status": "enabled", "description": "Text Completion API"},
    {"endpoint_id": "embeddings", "path": "/v1/embeddings", "method": "POST", "status": "enabled", "description": "Vector Embeddings API"},
    {"endpoint_id": "audio_transcriptions", "path": "/v1/audio/transcriptions", "method": "POST", "status": "enabled", "description": "Speech-to-Text API"},
    {"endpoint_id": "audio_speech", "path": "/v1/audio/speech", "method": "POST", "status": "enabled", "description": "Text-to-Speech API"},
    {"endpoint_id": "images_generations", "path": "/v1/images/generations", "method": "POST", "status": "enabled", "description": "Image Generation API"},
    {"endpoint_id": "moderations", "path": "/v1/moderations", "method": "POST", "status": "enabled", "description": "Content Moderation API"},
    {"endpoint_id": "predictions", "path": "/v1/predictions", "method": "POST", "status": "enabled", "description": "Custom Predictions API"},
    {"endpoint_id": "async_jobs", "path": "/v1/jobs", "method": "POST", "status": "enabled", "description": "Async Jobs Creation API"},
]


async def seed_mongodb():
    logger.info("Connecting to MongoDB Atlas Database 'ai_platform'...")
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]

    # 1. Seed Model Aliases
    logger.info("Seeding Model Aliases collection...")
    for alias in DEFAULT_ALIASES:
        alias["updated_at"] = datetime.now(timezone.utc)
        await db.aliases.update_one(
            {"alias_name": alias["alias_name"]},
            {"$set": alias},
            upsert=True
        )

    # 2. Seed Export Endpoints
    logger.info("Seeding Export Endpoints collection...")
    for ep in DEFAULT_ENDPOINTS:
        ep["updated_at"] = datetime.now(timezone.utc)
        await db.endpoints.update_one(
            {"endpoint_id": ep["endpoint_id"]},
            {"$set": ep},
            upsert=True
        )

    # 3. Seed Default Tenant API Key
    logger.info("Seeding Default Tenant API Key...")
    default_key = {
        "key_id": "key_01HXDEFAULT",
        "tenant_id": "TENANT_RETAIL_BANK",
        "prefix": "aip_live_test_...",
        "rpm_limit": 120,
        "tpm_limit": 200000,
        "concurrency_limit": 10,
        "status": "enabled",
        "created_at": datetime.now(timezone.utc),
    }
    await db.api_keys.update_one(
        {"key_id": default_key["key_id"]},
        {"$set": default_key},
        upsert=True
    )

    logger.info("MongoDB Atlas 'ai_platform' Seeding Completed Successfully! 🚀")


if __name__ == "__main__":
    asyncio.run(seed_mongodb())
