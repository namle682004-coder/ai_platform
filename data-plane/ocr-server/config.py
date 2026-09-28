"""
Canonical Configuration settings for AIP OCR & Document Server.
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class OCRSettings(BaseSettings):
    service_name: str = "aip-ocr-server"
    version: str = "1.0.0"
    port: int = int(os.getenv("PORT", "8004"))
    host: str = os.getenv("HOST", "0.0.0.0")

    model_registry_path: str = os.getenv("AIP_MODEL_REGISTRY_PATH", "/models")
    device: str = os.getenv("COMPUTE_DEVICE", "auto")
    paddle_lang: str = os.getenv("PADDLE_LANG", "vi")
    det_model_name: str = os.getenv("OCR_DET_MODEL", "ch_PP-OCRv4_det")
    rec_model_name: str = os.getenv("OCR_REC_MODEL", "ch_PP-OCRv4_rec")

    model_config = SettingsConfigDict(env_prefix="AIP_OCR_")


settings = OCRSettings()
ocr_settings = settings  # Backward compatibility
