"""
Enterprise Typed Application Configuration for AIP Control Plane Gateway.
Compliant with 12-Factor App methodology and strict Pydantic v2 validation.
"""

from __future__ import annotations

import os
from functools import lru_cache
from urllib.parse import unquote, urlparse
from pydantic import BaseModel, Field, PositiveInt, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    """Settings for primary persistent document store (MongoDB Atlas / Local)."""
    mongo_root_username: str = Field(default="aip_root")
    mongo_root_password: SecretStr | None = None
    mongo_database: str = Field(default="ai_platform")
    mongodb_uri: str = Field(..., description="Full connection string for MongoDB Atlas / Local")


class RedisSettings(BaseModel):
    """Settings for in-memory token cache, rate-limiting & session store."""
    redis_password: SecretStr | None = None
    redis_url: str = Field(default="redis://localhost:6379/0")
    host: str = Field(default="localhost")
    port: PositiveInt = Field(default=6379)


class RabbitMQSettings(BaseModel):
    """Settings for asynchronous distributed event broker & message queue."""
    rabbitmq_user: str = Field(default="aip")
    rabbitmq_password: SecretStr | None = None
    rabbitmq_vhost: str = Field(default="aip")
    rabbitmq_url: str = Field(default="amqp://aip@localhost:5672/aip")


class MinIOSettings(BaseModel):
    """Settings for object storage (audio, document & image assets)."""
    minio_root_user: str = Field(default="minioadmin")
    minio_root_password: SecretStr
    minio_endpoint: str = Field(default="http://localhost:9000")
    minio_console_endpoint: str = Field(default="http://localhost:9001")
    minio_bucket_name: str = Field(default="aip-data")
    minio_region: str = Field(default="us-east-1")
    minio_use_ssl: bool = Field(default=False)


class SecuritySettings(BaseModel):
    """Enterprise security & authentication settings."""
    master_pepper: SecretStr
    jwt_secret: SecretStr
    api_key_salt_rounds: PositiveInt = Field(default=12)
    admin_allowed_cidrs: str = Field(default="127.0.0.1/32,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,152.16.0.0/16,171.236.0.0/16")


class AIRuntimesSettings(BaseModel):
    """Internal URLs for decoupled GPU/CPU AI runtime microservices."""
    stt_server_url: str = Field(default="http://localhost:8002")
    translation_server_url: str = Field(default="http://localhost:8003")
    ocr_server_url: str = Field(default="http://localhost:8004")
    moderation_server_url: str = Field(default="http://localhost:8006")
    tts_server_url: str = Field(default="http://localhost:8007")
    vllm_server_url: str = Field(default="http://localhost:8001/v1")



class QuotaSettings(BaseModel):
    """Default rate-limit and concurrency quotas for tenants."""
    default_rpm: PositiveInt = Field(default=60)
    default_tpm: PositiveInt = Field(default=100000)
    default_concurrency: PositiveInt = Field(default=5)
    rate_limit_rps: PositiveInt = Field(default=25)
    rate_limit_burst: PositiveInt = Field(default=100)
    rate_limit_window_seconds: PositiveInt = Field(default=60)


class GatewaySettings(BaseSettings):
    """
    Root Gateway Configuration loaded from environment variables and `.env` file.
    Provides fail-fast validation and typed sub-domains for high security.
    """

    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Core Environment
    environment: str = Field(default="development", alias="ENVIRONMENT")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: PositiveInt = Field(default=8000, alias="PORT")
    debug: bool = Field(default=True, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Security & Master Pepper
    master_pepper: SecretStr = Field(
        default=SecretStr("aip-default-master-pepper-change-in-production-min32"),
        alias="MASTER_PEPPER",
    )
    jwt_secret: SecretStr = Field(
        default=SecretStr("aip-default-jwt-secret-change-in-production-min32"),
        alias="JWT_SECRET",
    )
    api_key_salt_rounds: PositiveInt = Field(default=12, alias="API_KEY_SALT_ROUNDS")
    dev_api_key: SecretStr | None = Field(default=None, alias="AIP_API_KEY")
    runtime_token: SecretStr | None = Field(default=None, alias="AIP_RUNTIME_TOKEN")
    allow_in_process_fallback: bool = Field(default=False, alias="ALLOW_IN_PROCESS_FALLBACK")

    # Data Stores - MongoDB
    mongo_root_username: str = Field(default="aip_root", alias="MONGO_ROOT_USERNAME")
    mongo_root_password: SecretStr | None = Field(default=None, alias="MONGO_ROOT_PASSWORD")
    mongo_database: str = Field(default="ai_platform", alias="MONGO_DATABASE")
    mongo_uri: str = Field(default="mongodb://localhost:27017/ai_platform", alias="MONGO_URI")
    mongodb_uri: str | None = Field(default=None, alias="MONGODB_URI")

    # Redis Settings
    redis_password: SecretStr | None = Field(default=None, alias="REDIS_PASSWORD")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    redis_host: str = Field(default="localhost", alias="REDIS_HOST")
    redis_port: PositiveInt = Field(default=6379, alias="REDIS_PORT")

    # RabbitMQ Settings
    rabbitmq_user: str = Field(default="aip", alias="RABBITMQ_USER")
    rabbitmq_password: SecretStr | None = Field(default=None, alias="RABBITMQ_PASSWORD")
    rabbitmq_vhost: str = Field(default="aip", alias="RABBITMQ_VHOST")
    rabbitmq_url: str = Field(default="amqp://aip@localhost:5672/aip", alias="RABBITMQ_URL")

    # MinIO Settings
    minio_root_user: str = Field(default="minioadmin", alias="MINIO_ROOT_USER")
    minio_root_password: SecretStr = Field(default=SecretStr("minioadmin123"), alias="MINIO_ROOT_PASSWORD")
    minio_endpoint: str = Field(default="http://localhost:9000", alias="MINIO_ENDPOINT")
    minio_console_endpoint: str = Field(default="http://localhost:9001", alias="MINIO_CONSOLE_ENDPOINT")
    minio_bucket_name: str = Field(default="aip-data", alias="MINIO_BUCKET_NAME")
    minio_region: str = Field(default="us-east-1", alias="MINIO_REGION")
    minio_use_ssl: bool = Field(default=False, alias="MINIO_USE_SSL")

    # Default Quota Limits
    default_rpm_limit: PositiveInt = Field(default=60, alias="DEFAULT_RPM_LIMIT")
    default_tpm_limit: PositiveInt = Field(default=100000, alias="DEFAULT_TPM_LIMIT")
    default_concurrency_limit: PositiveInt = Field(default=5, alias="DEFAULT_CONCURRENCY_LIMIT")
    rate_limit_rps: PositiveInt = Field(default=25, alias="RATE_LIMIT_RPS")
    rate_limit_burst: PositiveInt = Field(default=100, alias="RATE_LIMIT_BURST")
    rate_limit_window_seconds: PositiveInt = Field(default=60, alias="RATE_LIMIT_WINDOW_SECONDS")

    # Operational Defaults
    request_timeout_seconds: PositiveInt = Field(default=30, alias="REQUEST_TIMEOUT_SECONDS")
    worker_concurrency: PositiveInt = Field(default=8, alias="WORKER_CONCURRENCY")
    item_retention_days: PositiveInt = Field(default=7, alias="ITEM_RETENTION_DAYS")
    config_validation_ttl_days: PositiveInt = Field(default=14, alias="CONFIG_VALIDATION_TTL_DAYS")

    # Admin CIDR Protection
    admin_allowed_cidrs: str = Field(
        default="127.0.0.1/32,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,152.16.0.0/16,171.236.0.0/16",
        alias="ADMIN_ALLOWED_CIDRS",
    )

    # Microservice Target Backend URLs
    stt_server_url: str = Field(default="http://localhost:8002", alias="STT_SERVER_URL")
    translation_server_url: str = Field(default="http://localhost:8003", alias="TRANSLATION_SERVER_URL")
    ocr_server_url: str = Field(default="http://localhost:8004", alias="OCR_SERVER_URL")
    moderation_server_url: str = Field(default="http://localhost:8006", alias="MODERATION_SERVER_URL")
    tts_server_url: str = Field(default="http://localhost:8007", alias="TTS_SERVER_URL")
    vllm_server_url: str = Field(default="http://localhost:8001/v1", alias="VLLM_SERVER_URL")


    @model_validator(mode="before")
    @classmethod
    def _reconcile_variables(cls, values: dict) -> dict:
        if isinstance(values, dict):
            # Supply safe defaults if not provided in environment
            values.setdefault("MASTER_PEPPER", "aip-default-master-pepper-change-in-production-min32")
            values.setdefault("JWT_SECRET", "aip-default-jwt-secret-change-in-production-min32")
            values.setdefault("MONGO_URI", "mongodb://localhost:27017/ai_platform")
            values.setdefault("MINIO_ROOT_PASSWORD", "minioadmin123")

            # 1. MongoDB URI reconciliation
            if values.get("MONGODB_URI") and not values.get("MONGO_URI"):
                values["MONGO_URI"] = values["MONGODB_URI"]
            elif values.get("MONGO_URI") and not values.get("MONGODB_URI"):
                values["MONGODB_URI"] = values["MONGO_URI"]

            # 2. Redis URL reconciliation
            redis_url = values.get("REDIS_URL")
            if redis_url:
                try:
                    p = urlparse(redis_url)
                    if p.hostname and not values.get("REDIS_HOST"):
                        values["REDIS_HOST"] = p.hostname
                    if p.port and not values.get("REDIS_PORT"):
                        values["REDIS_PORT"] = p.port
                    if p.password and not values.get("REDIS_PASSWORD"):
                        values["REDIS_PASSWORD"] = unquote(p.password)
                except Exception:
                    pass

            # 3. RabbitMQ URL reconciliation
            rabbitmq_url = values.get("RABBITMQ_URL")
            if rabbitmq_url:
                try:
                    p = urlparse(rabbitmq_url)
                    if p.username and not values.get("RABBITMQ_USER"):
                        values["RABBITMQ_USER"] = unquote(p.username)
                    if p.password and not values.get("RABBITMQ_PASSWORD"):
                        values["RABBITMQ_PASSWORD"] = unquote(p.password)
                    if p.path and p.path.strip("/") and not values.get("RABBITMQ_VHOST"):
                        values["RABBITMQ_VHOST"] = p.path.strip("/")
                except Exception:
                    pass

        return values

    @field_validator("environment", "mongo_uri", "rabbitmq_url", "minio_endpoint", mode="before")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Configuration value must not be empty.")
        return value.strip()

    # Typed Sub-settings Properties (AIP Enterprise Architecture Pattern)
    @property
    def database(self) -> DatabaseSettings:
        return DatabaseSettings(
            mongo_root_username=self.mongo_root_username,
            mongo_root_password=self.mongo_root_password,
            mongo_database=self.mongo_database,
            mongodb_uri=self.mongo_uri,
        )

    @property
    def redis(self) -> RedisSettings:
        return RedisSettings(
            redis_password=self.redis_password,
            redis_url=self.redis_url,
            host=self.redis_host,
            port=self.redis_port,
        )

    @property
    def rabbitmq(self) -> RabbitMQSettings:
        return RabbitMQSettings(
            rabbitmq_user=self.rabbitmq_user,
            rabbitmq_password=self.rabbitmq_password,
            rabbitmq_vhost=self.rabbitmq_vhost,
            rabbitmq_url=self.rabbitmq_url,
        )

    @property
    def minio(self) -> MinIOSettings:
        return MinIOSettings(
            minio_root_user=self.minio_root_user,
            minio_root_password=self.minio_root_password,
            minio_endpoint=self.minio_endpoint,
            minio_console_endpoint=self.minio_console_endpoint,
            minio_bucket_name=self.minio_bucket_name,
            minio_region=self.minio_region,
            minio_use_ssl=self.minio_use_ssl,
        )

    @property
    def security(self) -> SecuritySettings:
        return SecuritySettings(
            master_pepper=self.master_pepper,
            jwt_secret=self.jwt_secret,
            api_key_salt_rounds=self.api_key_salt_rounds,
            admin_allowed_cidrs=self.admin_allowed_cidrs,
        )

    @property
    def ai_runtimes(self) -> AIRuntimesSettings:
        return AIRuntimesSettings(
            stt_server_url=self.stt_server_url,
            translation_server_url=self.translation_server_url,
            ocr_server_url=self.ocr_server_url,
            moderation_server_url=self.moderation_server_url,
            tts_server_url=self.tts_server_url,
        )

    @property
    def quotas(self) -> QuotaSettings:
        return QuotaSettings(
            default_rpm=self.default_rpm_limit,
            default_tpm=self.default_tpm_limit,
            default_concurrency=self.default_concurrency_limit,
            rate_limit_rps=self.rate_limit_rps,
            rate_limit_burst=self.rate_limit_burst,
            rate_limit_window_seconds=self.rate_limit_window_seconds,
        )


@lru_cache(maxsize=1)
def get_gateway_settings() -> GatewaySettings:
    """Load and cache validated settings (fail-fast on invalid config)."""
    try:
        return GatewaySettings()
    except ValidationError as exc:
        raise RuntimeError(f"Invalid AIP Gateway configuration: {exc}") from exc


# Global shared instance maintaining backward compatibility
gateway_settings = get_gateway_settings()

