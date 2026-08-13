from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    app_name: str = "AIP API Gateway"
    env: str = "development"
    debug: bool = True
    port: int = 8000
    host: str = "0.0.0.0"

    master_key_pepper: str = "change_this_master_secret_pepper_32bytes"
    mongo_uri: str = "mongodb://root:example@localhost:27017"
    mongo_db_name: str = "aip_platform"
    redis_uri: str = "redis://:example@localhost:6379/0"
    rabbitmq_uri: str = "amqp://guest:guest@localhost:5672/"
    minio_endpoint: str = "localhost:9000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


gateway_settings = GatewaySettings()
