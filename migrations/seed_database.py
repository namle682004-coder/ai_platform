import asyncio
import logging
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aip-seed")

MONGO_URI = "mongodb+srv://namle:1234@namle.52nsi1k.mongodb.net/ai_platform?appName=namle"
DB_NAME = "ai_platform"

DEFAULT_ALIASES = [
    {
        "alias_name": "chat-general-standard",
        "model_name": "Qwen2.5-1.5B-Instruct",
        "physical_model": "Qwen/Qwen2.5-1.5B-Instruct",
        "runtime": "vllm",
        "target_url": "http://vllm-engine:8001/v1",
        "min_vram_gb": 2,
        "timeout_seconds": 120,
        "category": "Generative AI",
        "status": "enabled",
        "description": "Standard OpenAI-compatible Chat Completions (/v1/chat/completions) via Qwen2.5-1.5B-Instruct",
    },
    {
        "alias_name": "stt-vn-standard",
        "model_name": "faster-whisper-small",
        "physical_model": "Systran/faster-whisper-small",
        "runtime": "faster-whisper",
        "target_url": "http://stt-server:8002/v1",
        "min_vram_gb": 0,
        "timeout_seconds": 60,
        "category": "Speech Recognition",
        "status": "enabled",
        "description": "Vietnamese & Multilingual Speech-to-Text inference (/v1/audio/transcriptions)",
    },
    {
        "alias_name": "tts-vi-standard",
        "model_name": "vi-VN-Neural",
        "physical_model": "Neural Speech Synthesizer",
        "runtime": "tts-adapter",
        "target_url": "http://tts-adapter:8007/v1",
        "min_vram_gb": 0,
        "timeout_seconds": 30,
        "category": "Speech Synthesis",
        "status": "enabled",
        "description": "Natural Vietnamese neural speech synthesis (/v1/audio/speech)",
    },
    {
        "alias_name": "idp-standard",
        "model_name": "EasyOCR-Vietnamese-ID",
        "physical_model": "EasyOCR Latin + CRAFT + OpenCV QR Engine",
        "runtime": "ocr-server",
        "target_url": "http://ocr-server:8004/v1",
        "min_vram_gb": 2,
        "timeout_seconds": 30,
        "category": "OCR & Reader",
        "status": "enabled",
        "description": "National Citizen ID Card (CCCD) OCR & QR extraction (/v1/ocr/id-card)",
    },
    {
        "alias_name": "moderation-multimodal",
        "model_name": "PhoBERT-base + Rule Engine",
        "physical_model": "vinai/phobert-base + Deterministic Rule Classifier",
        "runtime": "moderation-server",
        "target_url": "http://moderation-server:8006/v1",
        "min_vram_gb": 1,
        "timeout_seconds": 15,
        "category": "Trust & Safety",
        "status": "enabled",
        "description": "Content moderation (/v1/moderations) for hate, harassment, sexual, and violence",
    },
    {
        "alias_name": "translate-vi-standard",
        "model_name": "opus-mt-vi-en",
        "physical_model": "Helsinki-NLP/opus-mt-vi-en",
        "runtime": "ctranslate2",
        "target_url": "http://translation-server:8003/v1",
        "min_vram_gb": 1,
        "timeout_seconds": 30,
        "category": "Natural Language Processing",
        "status": "enabled",
        "description": "Bidirectional Vietnamese - English machine translation (/v1/nlp/translation)",
    },
    {
        "alias_name": "embed-standard",
        "model_name": "Qwen2.5-1.5B-Instruct (mean-pooled embeddings)",
        "physical_model": "Qwen/Qwen2.5-1.5B-Instruct",
        "runtime": "transformers-embeddings",
        "target_url": "http://vllm-engine:8001/v1",
        "min_vram_gb": 0,
        "timeout_seconds": 30,
        "category": "Natural Language Processing",
        "status": "enabled",
        "description": "Mean-pooled normalized embeddings from the configured Transformers model (/v1/embeddings)",
    },
]

DEFAULT_ENDPOINTS = [
    {"endpoint_id": "/v1/chat/completions", "path": "/v1/chat/completions", "method": "POST", "status": "active", "description": "LLM Chat Completions API"},
    {"endpoint_id": "/v1/audio/transcriptions", "path": "/v1/audio/transcriptions", "method": "POST", "status": "active", "description": "Speech-to-Text API"},
    {"endpoint_id": "/v1/audio/speech", "path": "/v1/audio/speech", "method": "POST", "status": "active", "description": "Text-to-Speech API"},
    {"endpoint_id": "/v1/ocr/id-card", "path": "/v1/ocr/id-card", "method": "POST", "status": "active", "description": "Citizen ID Card OCR & QR API"},
    {"endpoint_id": "/v1/moderations", "path": "/v1/moderations", "method": "POST", "status": "active", "description": "Content Moderation API"},
    {"endpoint_id": "/v1/embeddings", "path": "/v1/embeddings", "method": "POST", "status": "active", "description": "Vector Text Embeddings API"},
    {"endpoint_id": "/v1/nlp/translation", "path": "/v1/nlp/translation", "method": "POST", "status": "active", "description": "Translation API"},
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

    logger.info("MongoDB Atlas 'ai_platform' Seeding Completed Successfully! 🚀")

if __name__ == "__main__":
    asyncio.run(seed_mongodb())
