"""
Embedding Service Adapter for AIP Enterprise RAG Solution.

Calls the OpenAI-compatible `/v1/embeddings` endpoint of the runtime registered under the
`embed-standard` alias (BAAI/bge-m3 on platform/runtimes/embedding-server).

Failures raise EmbeddingError. There is deliberately no synthetic fallback vector: a fake
vector indexed during ingestion, or used at query time, silently corrupts retrieval.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

import httpx

from ...config import rag_settings
from ...domain.exceptions import EmbeddingError
from ...domain.ports import EmbeddingPort
from .model_registry import (
    ModelEndpointNotFoundError,
    ModelEndpointResolver,
    ModelRuntimeError,
    model_endpoint_resolver,
    post_json_with_retry,
    runtime_headers,
)

logger = logging.getLogger("aip-rag.adapter.embedding")


class HttpEmbeddingAdapter(EmbeddingPort):
    """Embedding adapter resolving the runtime endpoint from the model alias registry."""

    def __init__(
        self,
        dim: Optional[int] = None,
        base_url: Optional[str] = None,
        model_alias: Optional[str] = None,
        resolver: Optional[ModelEndpointResolver] = None,
        batch_size: Optional[int] = None,
        timeout: Optional[float] = None,
        **_legacy_kwargs: Any,  # accepts the removed gRPC `target=` / `http_url=` arguments
    ) -> None:
        self.dim = dim or rag_settings.embedding_dim
        self.override_url = base_url if base_url is not None else rag_settings.embedding_base_url
        self.model_alias = model_alias or rag_settings.embedding_model_alias
        self.resolver = resolver or model_endpoint_resolver
        self.batch_size = batch_size or rag_settings.embedding_batch_size
        self.timeout = timeout or rag_settings.embedding_timeout_seconds
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(limits=httpx.Limits(max_keepalive_connections=20, max_connections=50))
        return self._client

    async def _embed_batch(self, texts: List[str], alias: str) -> List[List[float]]:
        try:
            endpoint = await self.resolver.resolve(alias, override_url=self.override_url)
        except ModelEndpointNotFoundError as exc:
            raise EmbeddingError(str(exc)) from exc

        try:
            data = await post_json_with_retry(
                self._get_client(),
                f"{endpoint.base_url}/embeddings",
                {"model": alias, "input": texts},
                headers=runtime_headers(),
                timeout=self.timeout,
            )
        except ModelRuntimeError as exc:
            raise EmbeddingError(f"Embedding runtime '{alias}' at {endpoint.base_url} unavailable: {exc}") from exc

        items = sorted(data.get("data", []), key=lambda item: item.get("index", 0))
        vectors = [item.get("embedding") or [] for item in items]
        if len(vectors) != len(texts):
            raise EmbeddingError(f"Embedding runtime returned {len(vectors)} vectors for {len(texts)} inputs")
        bad = next((len(v) for v in vectors if len(v) != self.dim), None)
        if bad is not None:
            raise EmbeddingError(
                f"Embedding dimension mismatch: alias '{alias}' returned {bad}-dim vectors, "
                f"collection expects {self.dim} (check that the alias points at BAAI/bge-m3)"
            )
        return vectors

    async def get_embedding(self, text: str, model_alias: Optional[str] = None) -> List[float]:
        return (await self._embed_batch([text], model_alias or self.model_alias))[0]

    async def batch_get_embeddings(
        self,
        texts: List[str],
        model_alias: Optional[str] = None,
    ) -> List[List[float]]:
        if not texts:
            return []
        alias = model_alias or self.model_alias
        vectors: List[List[float]] = []
        for i in range(0, len(texts), self.batch_size):
            vectors.extend(await self._embed_batch(texts[i : i + self.batch_size], alias))
        return vectors

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None


# Backwards-compatible name: the gRPC fast lane was removed because no EmbeddingService gRPC
# server exists in the platform (and the batch call used a non-existent proto message).
GrpcEmbeddingAdapter = HttpEmbeddingAdapter
