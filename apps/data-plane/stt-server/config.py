"""
Canonical Configuration settings for AIP Speech-to-Text (Faster-Whisper) Server.
Compliant with Clean Architecture Data-Plane & SRS Section 2.3 & 6.1.
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class STTSettings(BaseSettings):
    service_name: str = "aip-stt-server"
    version: str = "1.0.0"
    port: int = int(os.getenv("PORT", "8002"))
    host: str = os.getenv("HOST", "0.0.0.0")

    model_registry_path: str = os.getenv("AIP_MODEL_REGISTRY_PATH", "/models")
    whisper_model_name: str = os.getenv("WHISPER_MODEL_NAME", "small")

    device: str = os.getenv("COMPUTE_DEVICE", "cpu")
    compute_type: str = os.getenv("COMPUTE_TYPE", "int8")
    device_index: int = int(os.getenv("DEVICE_INDEX", "0"))
    num_workers: int = int(os.getenv("NUM_WORKERS", "1"))

    beam_size: int = int(os.getenv("BEAM_SIZE", "5"))
    vad_filter: bool = os.getenv("VAD_FILTER", "true").lower() in ("true", "1", "yes")
    vad_min_silence_duration_ms: int = int(os.getenv("VAD_MIN_SILENCE_MS", "500"))
    default_language: str = os.getenv("DEFAULT_LANGUAGE", "vi")

    model_config = SettingsConfigDict(env_prefix="AIP_STT_")


settings = STTSettings()
stt_settings = settings  # Backward compatibility
