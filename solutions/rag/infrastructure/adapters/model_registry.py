"""
Model alias -> runtime endpoint resolution for the RAG solution.

The platform keeps model routing in the MongoDB `aliases` collection (managed through the
gateway admin API). RAG adapters resolve the same aliases so that changing a target_url there
re-points embeddings, reranking and generation without a redeploy.

Resolution order per alias:
1. Explicit override passed by the caller (e.g. RAG_EMBEDDING_URL) - for local development.
2. MongoDB `aliases` record (cached for `alias_cache_ttl_seconds`).
3. `common.models.catalog.AIP_MODEL_CATALOG` - offline fallback.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from ...config import rag_settings

logger = logging.getLogger("aip-rag.adapter.model_registry")

_DISABLED_STATUSES = {"disabled", "inactive"}


@dataclass(frozen=True)
class ModelEndpoint:
    alias: str
    base_url: str
    physical_model: str
    source: str  # "override" | "mongodb" | "catalog"


class ModelEndpointNotFoundError(LookupError):
    """Raised when an alias is unknown, disabled, or has no target_url."""


class ModelEndpointResolver:
    def __init__(
        self,
        mongo_uri: Optional[str] = None,
        cache_ttl_seconds: Optional[float] = None,
    ) -> None:
        self.mongo_uri = mongo_uri if mongo_uri is not None else rag_settings.mongo_uri
        self.cache_ttl_seconds = cache_ttl_seconds if cache_ttl_seconds is not None else rag_settings.alias_cache_ttl_seconds
        self._client: Any = None
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_loaded_at: float = 0.0
        self._lock = asyncio.Lock()

    def _db(self) -> Any:
        if not self.mongo_uri:
            return None
        if self._client is None:
            from motor.motor_asyncio import AsyncIOMotorClient

            self._client = AsyncIOMotorClient(self.mongo_uri, serverSelectionTimeoutMS=3000)
        db_name = self.mongo_uri.rsplit("/", 1)[-1].split("?")[0] or "ai_platform"
        return self._client[db_name]

    async def _load_mongo_aliases(self) -> None:
        if self._cache and (time.monotonic() - self._cache_loaded_at) < self.cache_ttl_seconds:
            return
        async with self._lock:
            if self._cache and (time.monotonic() - self._cache_loaded_at) < self.cache_ttl_seconds:
                return
            db = self._db()
            if db is None:
                return
            try:
                docs = await db.aliases.find({}, {"_id": 0}).to_list(length=500)
                self._cache = {d["alias_name"]: d for d in docs if d.get("alias_name")}
                self._cache_loaded_at = time.monotonic()
            except Exception as exc:
                # Keep serving the last known registry; the catalog covers a cold start.
                logger.warning("Alias registry refresh from MongoDB failed (%s); using cached/catalog entries", exc)
                self._cache_loaded_at = time.monotonic()

    @staticmethod
    def _catalog_entry(alias: str) -> Optional[Dict[str, Any]]:
        try:
            from common.models.catalog import AIP_MODEL_CATALOG
        except ImportError:
            return None
        model = AIP_MODEL_CATALOG.get(alias)
        if model is None:
            return None
        return {
            "alias_name": model.id,
            "physical_model": model.physical_model,
            "target_url": model.target_url,
            "status": model.status,
        }

    async def resolve(self, alias: str, override_url: str = "") -> ModelEndpoint:
        if override_url:
            return ModelEndpoint(alias=alias, base_url=override_url.rstrip("/"), physical_model=alias, source="override")

        await self._load_mongo_aliases()
        record = self._cache.get(alias)
        source = "mongodb"
        if record is None:
            record = self._catalog_entry(alias)
            source = "catalog"
        if record is None:
            raise ModelEndpointNotFoundError(f"Model alias '{alias}' is not registered")
        if str(record.get("status", "")).lower() in _DISABLED_STATUSES:
            raise ModelEndpointNotFoundError(f"Model alias '{alias}' is disabled")
        target_url = (record.get("target_url") or "").rstrip("/")
        if not target_url:
            raise ModelEndpointNotFoundError(f"Model alias '{alias}' has no target_url")
        return ModelEndpoint(
            alias=alias,
            base_url=target_url,
            physical_model=record.get("physical_model") or record.get("model_name") or alias,
            source=source,
        )

    def invalidate(self) -> None:
        self._cache_loaded_at = 0.0


_RETRYABLE_STATUS = {429, 502, 503, 504}


class ModelRuntimeError(RuntimeError):
    """A model runtime call failed after retries (transport error or non-success status)."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


async def post_json_with_retry(
    client: Any,
    url: str,
    payload: Dict[str, Any],
    headers: Dict[str, str],
    timeout: float,
    max_retries: Optional[int] = None,
) -> Dict[str, Any]:
    """POST JSON with exponential backoff on transport errors, 429 and 5xx gateway errors."""
    import httpx

    retries = rag_settings.model_max_retries if max_retries is None else max_retries
    last_error: Optional[str] = None
    last_status: Optional[int] = None
    for attempt in range(retries + 1):
        try:
            res = await client.post(url, json=payload, headers=headers, timeout=timeout)
            if res.status_code == 200:
                return res.json()
            last_status = res.status_code
            last_error = f"HTTP {res.status_code}: {res.text[:300]}"
            if res.status_code not in _RETRYABLE_STATUS:
                break
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        if attempt < retries:
            await asyncio.sleep(0.2 * (2**attempt))
    raise ModelRuntimeError(f"POST {url} failed: {last_error}", status_code=last_status)


def runtime_headers(authorization: Optional[str] = None) -> Dict[str, str]:
    """Headers for calls to data-plane runtimes (same contract as the gateway)."""
    headers = {"Content-Type": "application/json"}
    if rag_settings.runtime_token:
        headers["X-AIP-Runtime-Token"] = rag_settings.runtime_token
    bearer = authorization or (f"Bearer {rag_settings.internal_api_key}" if rag_settings.internal_api_key else "Bearer aip-rag-internal")
    headers["Authorization"] = bearer
    return headers


model_endpoint_resolver = ModelEndpointResolver()
