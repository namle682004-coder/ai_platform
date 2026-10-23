"""
Configuration settings for AIP Enterprise RAG Solution.
"""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=False)


class RagSolutionSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else ".env",
        extra="ignore",
        populate_by_name=True,
    )

    environment: str = Field(
        default="development",
        validation_alias=AliasChoices("ENVIRONMENT", "environment"),
    )
    rabbitmq_url: str = Field(
        default=os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/aip" if os.path.exists("/.dockerenv") else "amqp://guest:guest@localhost:5672/"),
        validation_alias=AliasChoices("RABBITMQ_URL", "rabbitmq_url"),
    )
    rag_queue: str = Field(
        default="q.aip.tasks.rag.normal",
        validation_alias=AliasChoices("AIP_RAG_QUEUE", "rag_queue"),
    )
    mongo_uri: str = Field(
        default=os.getenv(
            "MONGO_URI",
            os.getenv("MONGODB_URI", "")
        ),
        validation_alias=AliasChoices("MONGO_URI", "MONGODB_URI", "mongo_uri"),
    )
    qdrant_url: str = Field(
        default="http://qdrant:6333" if os.path.exists("/.dockerenv") else "http://localhost:6333",
        validation_alias=AliasChoices("QDRANT_URL", "qdrant_url"),
    )
    qdrant_grpc_port: int = Field(
        default=6334,
        validation_alias=AliasChoices("QDRANT_GRPC_PORT", "qdrant_grpc_port"),
    )
    collection_name: str = Field(
        default="aip_knowledge_base",
        validation_alias=AliasChoices("QDRANT_COLLECTION_NAME", "collection_name"),
    )
    embedding_dim: int = Field(
        default=1024,
        validation_alias=AliasChoices("EMBEDDING_DIM", "embedding_dim"),
    )  # bge-m3 standard
    embedding_grpc_target: str = Field(
        default="platform-gateway:50058" if os.path.exists("/.dockerenv") else "localhost:50058",
        validation_alias=AliasChoices("EMBEDDING_GRPC_TARGET", "embedding_grpc_target"),
    )
    vllm_server_url: str = Field(
        default="http://vllm-engine:8000/v1" if os.path.exists("/.dockerenv") else "http://localhost:8001/v1",
        validation_alias=AliasChoices("VLLM_SERVER_URL", "vllm_server_url"),
    )
    # Model serving resolution: explicit URL override -> MongoDB `aliases` -> common catalog.
    embedding_model_alias: str = Field(
        default="embed-standard",
        validation_alias=AliasChoices("RAG_EMBEDDING_ALIAS", "embedding_model_alias"),
    )
    reranker_model_alias: str = Field(
        default="rerank-standard",
        validation_alias=AliasChoices("RAG_RERANKER_ALIAS", "reranker_model_alias"),
    )
    embedding_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("RAG_EMBEDDING_URL", "embedding_base_url"),
        description="Explicit OpenAI-compatible embeddings base URL (…/v1); empty = resolve from alias registry",
    )
    reranker_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("RAG_RERANKER_URL", "reranker_base_url"),
        description="Explicit rerank base URL (…/v1); empty = resolve from alias registry",
    )
    llm_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("RAG_LLM_URL", "llm_base_url"),
        description="Explicit chat completions base URL (…/v1); empty = resolve from alias registry",
    )
    alias_cache_ttl_seconds: float = Field(
        default=60.0,
        validation_alias=AliasChoices("RAG_ALIAS_CACHE_TTL_SECONDS", "alias_cache_ttl_seconds"),
    )
    runtime_token: str = Field(
        default="",
        validation_alias=AliasChoices("AIP_RUNTIME_TOKEN", "runtime_token"),
        description="Shared token sent as X-AIP-Runtime-Token to data-plane runtimes and required from internal callers",
    )
    embedding_timeout_seconds: float = Field(
        default=30.0,
        validation_alias=AliasChoices("RAG_EMBEDDING_TIMEOUT_SECONDS", "embedding_timeout_seconds"),
    )
    embedding_batch_size: int = Field(
        default=32,
        validation_alias=AliasChoices("RAG_EMBEDDING_BATCH_SIZE", "embedding_batch_size"),
    )
    reranker_timeout_seconds: float = Field(
        default=15.0,
        validation_alias=AliasChoices("RAG_RERANKER_TIMEOUT_SECONDS", "reranker_timeout_seconds"),
    )
    llm_timeout_seconds: float = Field(
        default=60.0,
        validation_alias=AliasChoices("RAG_LLM_TIMEOUT_SECONDS", "llm_timeout_seconds"),
    )
    model_max_retries: int = Field(
        default=2,
        validation_alias=AliasChoices("RAG_MODEL_MAX_RETRIES", "model_max_retries"),
        description="Retries (with exponential backoff) on transport errors / 5xx from model runtimes",
    )
    reranker_backend: str = Field(
        default="remote",
        validation_alias=AliasChoices("RAG_RERANKER_BACKEND", "reranker_backend"),
        description="'remote' = bge-reranker via rerank-standard alias; 'local' = in-process FlashRank (dev only)",
    )
    trust_identity_headers: bool = Field(
        default=False,
        validation_alias=AliasChoices("RAG_TRUST_IDENTITY_HEADERS", "trust_identity_headers"),
        description="Accept X-Tenant-ID / X-User-Role without a runtime token (local development only)",
    )
    enforce_shared_kb_write_acl: bool = Field(
        default=True,
        validation_alias=AliasChoices("RAG_ENFORCE_SHARED_KB_WRITE_ACL", "enforce_shared_kb_write_acl"),
        description="Only admin roles may write to the shared (default) tenant, which every tenant can read",
    )
    minio_endpoint: str = Field(
        default="http://minio:9000" if os.path.exists("/.dockerenv") else "http://localhost:9000",
        validation_alias=AliasChoices("MINIO_ENDPOINT", "minio_endpoint"),
    )
    # Object storage credentials (must be populated via environment variables in production)
    minio_root_user: str = Field(
        default=os.getenv("AIP_MINIO_USER", os.getenv("MINIO_ROOT_USER", "")),
        validation_alias=AliasChoices("AIP_MINIO_USER", "MINIO_ROOT_USER", "minio_root_user"),
        description="MinIO root username/access key",
    )
    minio_root_password: str = Field(
        default=os.getenv("AIP_MINIO_PASSWORD", os.getenv("MINIO_ROOT_PASSWORD", "")),
        validation_alias=AliasChoices("AIP_MINIO_PASSWORD", "MINIO_ROOT_PASSWORD", "minio_root_password"),
        description="MinIO root password/secret key",
    )
    minio_bucket: str = Field(
        default="aip-data",
        validation_alias=AliasChoices("MINIO_BUCKET", "minio_bucket"),
    )
    chunk_size_chars: int = Field(
        default=900,
        validation_alias=AliasChoices("RAG_CHUNK_SIZE", "chunk_size_chars"),
    )
    chunk_overlap_chars: int = Field(
        default=150,
        validation_alias=AliasChoices("RAG_CHUNK_OVERLAP", "chunk_overlap_chars"),
    )
    child_chunk_size_chars: int = Field(
        default=900,
        validation_alias=AliasChoices("RAG_CHILD_CHUNK_SIZE", "child_chunk_size_chars"),
    )
    child_overlap_chars: int = Field(
        default=150,
        validation_alias=AliasChoices("RAG_CHILD_OVERLAP", "child_overlap_chars"),
    )
    parent_chunk_size_chars: int = Field(
        default=3600,
        validation_alias=AliasChoices("RAG_PARENT_CHUNK_SIZE", "parent_chunk_size_chars"),
    )
    mask_pii: bool = Field(
        default=True,
        validation_alias=AliasChoices("RAG_MASK_PII", "mask_pii"),
    )
    prefetch_count: int = Field(
        default=4,
        validation_alias=AliasChoices("WORKER_PREFETCH_COUNT", "prefetch_count"),
    )
    internal_api_key: str = Field(
        default=os.getenv("AIP_INTERNAL_API_KEY", ""),
        validation_alias=AliasChoices("AIP_INTERNAL_API_KEY", "internal_api_key"),
    )
    escalation_hotline: str = Field(
        default="1900-xxxx (Nhánh 2)",
        validation_alias=AliasChoices("RAG_ESCALATION_HOTLINE", "escalation_hotline"),
    )
    escalation_support_method: str = Field(
        default="UltraViewer",
        validation_alias=AliasChoices("RAG_ESCALATION_SUPPORT_METHOD", "escalation_support_method"),
    )
    escalation_instructions: str = Field(
        default="Vui lòng cung cấp ID và Mật khẩu UltraViewer để kỹ thuật viên kết nối hỗ trợ trực tiếp.",
        validation_alias=AliasChoices("RAG_ESCALATION_INSTRUCTIONS", "escalation_instructions"),
    )
    redis_url: str = Field(
        default="redis://localhost:6380/0" if not os.path.exists("/.dockerenv") else "redis://redis:6379/0",
        validation_alias=AliasChoices("REDIS_URL", "redis_url"),
    )
    cache_ttl_seconds: int = Field(
        default=3600,
        validation_alias=AliasChoices("RAG_CACHE_TTL_SECONDS", "cache_ttl_seconds"),
    )
    # Enterprise Algorithm & Hyperparameter Controls
    rrf_k: int = Field(
        default=60,
        validation_alias=AliasChoices("RAG_RRF_K", "rrf_k"),
        description="Reciprocal Rank Fusion smoothing constant",
    )
    bm25_k1: float = Field(
        default=1.5,
        validation_alias=AliasChoices("RAG_BM25_K1", "bm25_k1"),
        description="BM25 term frequency saturation parameter",
    )
    bm25_b: float = Field(
        default=0.75,
        validation_alias=AliasChoices("RAG_BM25_B", "bm25_b"),
        description="BM25 document length normalization parameter",
    )
    max_query_length: int = Field(
        default=4000,
        validation_alias=AliasChoices("RAG_MAX_QUERY_LENGTH", "max_query_length"),
        description="Maximum input query length in characters before truncation",
    )
    speculative_rewrite_timeout: float = Field(
        default=0.8,
        validation_alias=AliasChoices("RAG_SPECULATIVE_REWRITE_TIMEOUT", "speculative_rewrite_timeout"),
        description="Timeout in seconds for speculative query reformulation",
    )
    reranker_model: str = Field(
        default="ms-marco-MiniLM-L-12-v2",
        validation_alias=AliasChoices("RAG_RERANKER_MODEL", "reranker_model"),
        description="FlashRank model for reranker_backend='local' only (English; not calibrated for Vietnamese)",
    )
    sparse_avg_doc_len: float = Field(
        default=180.0,
        validation_alias=AliasChoices("RAG_SPARSE_AVG_DOC_LEN", "sparse_avg_doc_len"),
        description="Average chunk length in tokens for BM25 length normalisation (900-char chunks ~ 180 syllables)",
    )
    hybrid_fetch_multiplier: int = Field(
        default=8,
        validation_alias=AliasChoices("RAG_HYBRID_FETCH_MULTIPLIER", "hybrid_fetch_multiplier"),
    )
    hybrid_fetch_ceiling: int = Field(
        default=64,
        validation_alias=AliasChoices("RAG_HYBRID_FETCH_CEILING", "hybrid_fetch_ceiling"),
    )
    confidence_gate_threshold: float = Field(
        default=0.75,
        validation_alias=AliasChoices("RAG_CONFIDENCE_GATE_THRESHOLD", "confidence_gate_threshold"),
        description="Anti-Hallucination Gatekeeper cutoff (BRD-RAG-03: must be >= 0.75)",
    )
    hyde_max_tokens: int = Field(
        default=128,
        validation_alias=AliasChoices("RAG_HYDE_MAX_TOKENS", "hyde_max_tokens"),
    )
    # PDF Parser Security & Recursion Controls (Anti-Zip-Bomb & Nesting Guards)
    pdf_max_depth: int = Field(
        default=3,
        validation_alias=AliasChoices("RAG_PDF_MAX_DEPTH", "pdf_max_recursion_depth", "pdf_max_depth"),
        description="Maximum recursion depth for parsing embedded PDF files",
    )
    max_embedded_file_size_bytes: int = Field(
        default=20 * 1024 * 1024,  # 20MB
        validation_alias=AliasChoices("RAG_MAX_EMBEDDED_FILE_SIZE_BYTES", "max_embedded_file_size_bytes"),
        description="Maximum byte size for individual embedded file attachments",
    )
    max_embedded_files_count: int = Field(
        default=10,
        validation_alias=AliasChoices("RAG_MAX_EMBEDDED_FILES_COUNT", "max_embedded_files_count"),
        description="Maximum count of embedded file attachments extracted per PDF",
    )


rag_settings = RagSolutionSettings()
