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

    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


gateway_settings = GatewaySettings()
