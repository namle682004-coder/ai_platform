"""
Canonical Configuration settings for AIP Text-to-Speech Adapter.
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class TTSSettings(BaseSettings):
    service_name: str = "aip-tts-adapter"
    version: str = "1.0.0"
    port: int = int(os.getenv("PORT", "8007"))
    host: str = os.getenv("HOST", "0.0.0.0")

    model_registry_path: str = os.getenv("AIP_MODEL_REGISTRY_PATH", "/models")
    model_name: str = os.getenv("TTS_MODEL_NAME", "vi-VN-Neural")

    device: str = os.getenv("COMPUTE_DEVICE", "cpu")
    sample_rate: int = int(os.getenv("SAMPLE_RATE", "24000"))
    default_voice: str = os.getenv("DEFAULT_VOICE", "northern_female")
    default_format: str = os.getenv("DEFAULT_FORMAT", "mp3")

    model_config = SettingsConfigDict(env_prefix="AIP_TTS_")


settings = TTSSettings()
tts_settings = settings  # Backward compatibility
