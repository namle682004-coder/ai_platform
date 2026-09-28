"""
Canonical Configuration Settings for AIP Content Moderation Server.
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModerationSettings(BaseSettings):
    service_name: str = "aip-moderation-server"
    version: str = "1.0.0"
    port: int = int(os.getenv("PORT", "8006"))
    host: str = os.getenv("HOST", "0.0.0.0")

    model_registry_path: str = os.getenv("AIP_MODEL_REGISTRY_PATH", "/models")
    model_name: str = os.getenv("MODERATION_MODEL_NAME", "")

    device: str = os.getenv("COMPUTE_DEVICE", "auto")
    flag_threshold: float = float(os.getenv("FLAG_THRESHOLD", "0.5"))
    enable_pii_check: bool = True

    model_config = SettingsConfigDict(env_prefix="AIP_MODERATION_")


settings = ModerationSettings()
moderation_settings = settings  # Backward compatibility
