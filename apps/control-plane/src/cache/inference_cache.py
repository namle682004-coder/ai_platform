"""
Centralized Inference Cache Service compliant with SRS Section 5.1 & Section 8.1.
Provides deterministic payload hashing, domain-specific TTL policies,
graceful fail-open resilience, Cache-Control bypass, and Prometheus telemetry.
"""

import hashlib
import json
import logging
import time
from typing import Any, Optional
from starlette.requests import Request
from starlette.responses import Response

from src.db.redis import redis_service
from src.metrics import AIP_INFERENCE_CACHE_HITS_TOTAL, AIP_INFERENCE_CACHE_MISSES_TOTAL

logger = logging.getLogger("aip-inference-cache")

DEFAULT_DOMAIN_TTLS = {
    "embeddings": 604800,     # 7 days (vector embeddings are 100% deterministic)
    "moderations": 86400,     # 24 hours (content safety classifications)
    "translation": 86400,     # 24 hours
    "summarization": 86400,   # 24 hours
    "ocr": 86400,             # 24 hours (documents & IDs by file hash)
    "tts": 86400,             # 24 hours (audio synthesis by voice+text)
    "chat": 3600,             # 1 hour (deterministic prompt reasoning)
    "predictions": 86400,     # 24 hours
    "stt": 86400              # 24 hours (speech-to-text)
}


class InferenceCacheService:
    """
    Enterprise-grade Centralized Inference Cache Engine.
    Guarantees zero downtime with local fallback when Redis is degraded.
    """

    def __init__(self):
        # Fast in-memory backup cache with TTL when Redis is unreachable or for sub-millisecond lookups
        self._local_cache: dict[str, tuple[dict, float]] = {}
        self._max_local_entries = 2000

    def compute_hash(self, payload: Any) -> str:
        """
        Generate a deterministic MD5 hex hash for arbitrary payloads
        (dicts, lists, strings, numbers, binary bytes).
        """
        if isinstance(payload, bytes):
            return hashlib.md5(payload).hexdigest()
        if isinstance(payload, str):
            return hashlib.md5(payload.strip().encode("utf-8")).hexdigest()
        try:
            # Canonical JSON serialization with sorted keys
            canonical_json = json.dumps(payload, sort_keys=True, ensure_ascii=False)
            return hashlib.md5(canonical_json.encode("utf-8")).hexdigest()
        except Exception:
            return hashlib.md5(str(payload).encode("utf-8")).hexdigest()

    def make_cache_key(self, domain: str, model_or_alias: str, payload_hash: str) -> str:
        """Standardized SRS Cache Key format."""
        norm_domain = domain.strip().lower()
        norm_alias = model_or_alias.strip().lower().replace("/", "-")
        return f"aip:cache:inference:{norm_domain}:{norm_alias}:{payload_hash}"

    def should_bypass_cache(self, request: Optional[Request]) -> bool:
        """
        Respect standard RFC HTTP headers: Cache-Control: no-cache, no-store
        or Pragma: no-cache from clients.
        """
        if not request:
            return False
        cc = request.headers.get("cache-control", "").lower()
        pragma = request.headers.get("pragma", "").lower()
        return "no-cache" in cc or "no-store" in cc or "no-cache" in pragma

    async def get(
        self,
        domain: str,
        model_or_alias: str,
        payload_data: Any,
        request: Optional[Request] = None,
    ) -> tuple[Optional[dict], bool]:
        """
        Retrieve cached inference response.
        Returns:
            (cached_response_dict, is_cache_hit: bool)
        """
        # 1. Check client bypass headers
        if self.should_bypass_cache(request):
            AIP_INFERENCE_CACHE_MISSES_TOTAL.labels(domain=domain).inc()
            logger.debug(f"Cache bypassed by client header for domain={domain}")
            return None, False

        payload_hash = self.compute_hash(payload_data)
        cache_key = self.make_cache_key(domain, model_or_alias, payload_hash)

        # 2. Check Primary Redis Cache
        try:
            cached = await redis_service.get_json(cache_key)
            if cached is not None:
                AIP_INFERENCE_CACHE_HITS_TOTAL.labels(domain=domain).inc()
                logger.debug(f"Redis Cache HIT for key {cache_key}")
                return cached, True
        except Exception as exc:
            logger.warning(f"Inference cache Redis lookup error (failing open): {exc}")

        # 3. Check Local Memory Fallback Cache
        now = time.time()
        local_entry = self._local_cache.get(cache_key)
        if local_entry:
            val, expire_at = local_entry
            if expire_at > now:
                AIP_INFERENCE_CACHE_HITS_TOTAL.labels(domain=domain).inc()
                logger.debug(f"Local In-Memory Cache HIT for key {cache_key}")
                return val, True
            else:
                self._local_cache.pop(cache_key, None)

        # 4. Cache Miss
        AIP_INFERENCE_CACHE_MISSES_TOTAL.labels(domain=domain).inc()
        return None, False

    async def set(
        self,
        domain: str,
        model_or_alias: str,
        payload_data: Any,
        response_data: dict,
        ttl_seconds: Optional[int] = None,
    ) -> bool:
        """
        Store inference result into Redis with domain TTL.
        Fails open gracefully if storage fails.
        """
        payload_hash = self.compute_hash(payload_data)
        cache_key = self.make_cache_key(domain, model_or_alias, payload_hash)
        ttl = ttl_seconds if ttl_seconds is not None else DEFAULT_DOMAIN_TTLS.get(domain, 86400)

        # Store in Redis
        success = False
        try:
            success = await redis_service.set_json(cache_key, response_data, ttl_seconds=ttl)
        except Exception as exc:
            logger.warning(f"Failed to write to Redis inference cache: {exc}")

        # Maintain Local In-Memory Fallback
        if len(self._local_cache) >= self._max_local_entries:
            # Purge oldest 20% entries
            keys_to_remove = list(self._local_cache.keys())[:int(self._max_local_entries * 0.2)]
            for k in keys_to_remove:
                self._local_cache.pop(k, None)

        self._local_cache[cache_key] = (response_data, time.time() + ttl)
        return success

    def inject_headers(
        self,
        response: Response,
        is_hit: bool,
        duration_ms: Optional[float] = None,
    ) -> None:
        """Inject standardized SRS HTTP response headers."""
        response.headers["X-Cache"] = "HIT" if is_hit else "MISS"
        if is_hit:
            response.headers["X-Cache-Node"] = "redis-cache"
        if duration_ms is not None:
            response.headers["X-Execution-Time-Ms"] = f"{duration_ms:.2f}"


# Singleton instance
inference_cache = InferenceCacheService()
