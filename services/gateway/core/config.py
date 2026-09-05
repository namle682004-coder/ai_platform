from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import os


class GatewaySettings(BaseSettings):
    """
    Control Plane Gateway Settings with Multi-Environment Profile Support (Dev, UAT, Production).
    Single Codebase Principle compliant with 12-Factor App methodology.
    """

    # Environment Profile (development | uat | production)
    environment: str = Field("development", validation_alias="ENVIRONMENT")

    # Gateway Server Network Settings
    host: str = Field("0.0.0.0", validation_alias="HOST")
    port: int = Field(8000, validation_alias="PORT")
    debug: bool = Field(True, validation_alias="DEBUG")

    # Master Security Pepper & Keys
    master_pepper: str = Field("default_enterprise_secret_pepper_2026", validation_alias="MASTER_PEPPER")

    # MongoDB Atlas Connection URI (ai_platform DB)
    mongo_uri: str = Field(
        "mongodb+srv://namle:1234@namle.52nsi1k.mongodb.net/ai_platform?appName=namle",
        validation_alias="MONGO_URI"
    )
    redis_host: str = Field("localhost", validation_alias="REDIS_HOST")
    redis_port: int = Field(6379, validation_alias="REDIS_PORT")
    rabbitmq_url: str = Field("amqp://guest:guest@localhost:5672/", validation_alias="RABBITMQ_URL")
    minio_endpoint: str = Field("localhost:9000", validation_alias="MINIO_ENDPOINT")

    # Default Quota Limits
    default_rpm_limit: int = Field(60, validation_alias="DEFAULT_RPM_LIMIT")
    default_tpm_limit: int = Field(100000, validation_alias="DEFAULT_TPM_LIMIT")
    default_concurrency_limit: int = Field(5, validation_alias="DEFAULT_CONCURRENCY_LIMIT")

    # Admin CIDR Protection (allows localhost, private subnets, and corporate/dev networks)
    admin_allowed_cidrs: str = Field(
        "127.0.0.1/32,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,152.16.0.0/16,171.236.0.0/16",
        validation_alias="ADMIN_ALLOWED_CIDRS",
    )

    # Microservice Target Backend URLs
    stt_server_url: str = Field("http://localhost:8002", validation_alias="STT_SERVER_URL")
    translation_server_url: str = Field("http://localhost:8003", validation_alias="TRANSLATION_SERVER_URL")
    ocr_server_url: str = Field("http://localhost:8004", validation_alias="OCR_SERVER_URL")
    moderation_server_url: str = Field("http://localhost:8006", validation_alias="MODERATION_SERVER_URL")
    tts_server_url: str = Field("http://localhost:8007", validation_alias="TTS_SERVER_URL")

    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


gateway_settings = GatewaySettings()
