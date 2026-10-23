"""
Configuration for the AIP Embedding & Reranking Server (BGE-M3 + BGE-Reranker-v2-m3).

Serves the `embed-standard` and `rerank-standard` aliases registered in the
MongoDB `aliases` collection (target_url = http://<host>:8012/v1).
"""

from __future__ import annotations

from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbeddingServerSettings(BaseSettings):
    service_name: str = "aip-embedding-server"
    version: str = "1.0.0"
    host: str = "0.0.0.0"
    port: int = 8012

    # Model weights on disk (defaults match /home/lenam/models layout on the GPU host)
    embedding_model_path: str = "/home/lenam/models/bge-m3"
    reranker_model_path: str = "/home/lenam/models/bge-reranker"

    # Logical names accepted in the `model` request field (alias + physical id)
    embedding_model_names: list[str] = Field(default_factory=lambda: ["embed-standard", "BAAI/bge-m3", "bge-m3"])
    reranker_model_names: list[str] = Field(
        default_factory=lambda: ["rerank-standard", "BAAI/bge-reranker-v2-m3", "bge-reranker-v2-m3", "bge-reranker"]
    )

    use_fp16: bool = True
    embedding_dim: int = 1024
    embedding_max_length: int = 8192
    embedding_batch_size: int = 16
    reranker_max_length: int = 1024
    reranker_batch_size: int = 16

    # Request guardrails
    max_inputs_per_request: int = 256
    max_documents_per_rerank: int = 128
    max_chars_per_input: int = 32_000

    # Shared runtime token (same contract as common.security.runtime_auth.RuntimeAuthMiddleware):
    # when set, callers must send `X-AIP-Runtime-Token`; otherwise a Bearer header is required.
    runtime_token: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("AIP_EMBEDDING_RUNTIME_TOKEN", "AIP_RUNTIME_TOKEN"),
    )
    disable_auth: bool = False

    model_config = SettingsConfigDict(env_prefix="AIP_EMBEDDING_", env_file=".env", extra="ignore")


settings = EmbeddingServerSettings()
