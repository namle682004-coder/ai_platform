"""
Canonical Configuration settings for AIP CTranslate2 Translation Server.
Compliant with Clean Architecture Data-Plane & SRS Section 2.3 & 6.1.
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_model_registry_path() -> str:
    env_path = os.getenv("AIP_MODEL_REGISTRY_PATH")
    if env_path:
        return env_path

    repo_default = Path(__file__).resolve().parents[2] / "models"
    if repo_default.exists():
        return str(repo_default)
    return "/models"


class TranslationSettings(BaseSettings):
    service_name: str = "aip-translation-server"
    version: str = "1.0.0"
    port: int = int(os.getenv("PORT", "8003"))
    host: str = os.getenv("HOST", "0.0.0.0")

    model_registry_path: str = _default_model_registry_path()
    model_name: str = os.getenv("TRANSLATION_MODEL_NAME", "opus-mt-vi-en")

    device: str = os.getenv("COMPUTE_DEVICE", "auto")
    compute_type: str = os.getenv("COMPUTE_TYPE", "int8")
    device_index: int = int(os.getenv("DEVICE_INDEX", "0"))
    inter_threads: int = int(os.getenv("INTER_THREADS", "2"))
    intra_threads: int = int(os.getenv("INTRA_THREADS", "4"))

    max_batch_size: int = int(os.getenv("MAX_BATCH_SIZE", "32"))
    beam_size: int = int(os.getenv("BEAM_SIZE", "4"))
    max_decoding_length: int = int(os.getenv("MAX_DECODING_LENGTH", "256"))

    model_config = SettingsConfigDict(env_prefix="AIP_TRANSLATION_")


settings = TranslationSettings()
translation_settings = settings  # Backward compatibility
