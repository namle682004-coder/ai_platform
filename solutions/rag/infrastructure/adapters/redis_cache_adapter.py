"""
Multi-Tier Redis Caching Adapter for AIP Enterprise RAG Solution (FR-EXEC-05 / EXEC-RAG-06).
Provides high-concurrency response caching (1,000 CCU support) with exact query hash caching,
sub-millisecond lookups, graceful degradation, and automatic cache invalidation.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any, Dict, Optional, Tuple

try:
    import redis.asyncio as aioredis
except ImportError:
    try:
        import aioredis  # type: ignore
    except ImportError:
        aioredis = None

from ...config import rag_settings
from ...application.dtos import RagChatResponseDTO
from ...domain.entities import DEFAULT_TENANT_ID, normalize_tenant_id
from ...domain.ports import CachePort

logger = logging.getLogger("aip-rag.adapter.redis_cache")


class RedisCacheAdapter(CachePort):
    """
    Production Redis Cache Adapter with Circuit-Breaker and In-Memory Fallback.
    Complies with FR-EXEC-05 & EXEC-RAG-06.
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        default_ttl: Optional[int] = None,
        connection_timeout: float = 1.0,
    ) -> None:
        self.redis_url = redis_url or rag_settings.redis_url
        self.default_ttl = default_ttl or rag_settings.cache_ttl_seconds
        self.connection_timeout = connection_timeout
        self._client: Optional[Any] = None
        self._is_available: bool = True
        self._last_failure_time: float = 0.0
        self._backoff_cooldown: float = 60.0  # seconds before retry after connection failure
        self._in_memory_lru: Dict[str, Tuple[float, str]] = {}  # key -> (expires_at, json_payload)
        self._max_in_memory_entries: int = 500

    async def _get_client(self) -> Optional[Any]:
        if aioredis is None:
            return None

        # Check circuit-breaker cooldown
        now = time.time()
        if not self._is_available and (now - self._last_failure_time) < self._backoff_cooldown:
            return None

        if self._client is None:
            try:
                self._client = aioredis.from_url(
                    self.redis_url,
                    socket_connect_timeout=self.connection_timeout,
                    socket_timeout=self.connection_timeout,
                    encoding="utf-8",
                    decode_responses=True,
                )
                # Quick ping to verify connectivity
                await asyncio.wait_for(self._client.ping(), timeout=self.connection_timeout)
                self._is_available = True
                logger.info("Connected to Redis cache at %s", self.redis_url)
            except Exception as exc:
                self._is_available = False
                self._last_failure_time = now
                logger.warning("Redis cache unavailable (%s). Falling back to in-memory cache.", exc)
                self._client = None
                return None

        return self._client

    @staticmethod
    def compute_cache_key(
        query: str,
        tenant_id: str = DEFAULT_TENANT_ID,
        combine_strategy: str = "single_pass_reordered",
        as_of_date: Optional[str] = None,
        user_role: str = "user",
        department: Optional[str] = None,
        similarity_threshold: Optional[float] = None,
    ) -> str:
        """
        Computes deterministic SHA-256 cache key across normalized query, tenancy, and ACL parameters.
        Prevents role-escalation and cross-role ACL leakage in multi-tenant RAG.
        """
        norm_tenant = normalize_tenant_id(tenant_id)
        normalized_q = query.strip().lower()
        thresh_str = f"{round(similarity_threshold, 2)}" if similarity_threshold else "0.0"
        key_raw = f"{norm_tenant}:{user_role}:{department or '*'}:{normalized_q}:{combine_strategy}:{as_of_date or 'CURRENT'}:{thresh_str}"
        hash_digest = hashlib.sha256(key_raw.encode("utf-8")).hexdigest()
        return f"aip:rag:cache:{norm_tenant}:{hash_digest}"

    async def get(
        self,
        query: str,
        tenant_id: str = DEFAULT_TENANT_ID,
        combine_strategy: str = "single_pass_reordered",
        as_of_date: Optional[str] = None,
        user_role: str = "user",
        department: Optional[str] = None,
        similarity_threshold: Optional[float] = None,
    ) -> Optional[RagChatResponseDTO]:
        """
        Retrieves cached response in < 15ms.
        Returns None if cache miss or Redis failure.
        """
        cache_key = self.compute_cache_key(
            query=query,
            tenant_id=tenant_id,
            combine_strategy=combine_strategy,
            as_of_date=as_of_date,
            user_role=user_role,
            department=department,
            similarity_threshold=similarity_threshold,
        )
        now = time.time()

        # 1. Try Redis first
        client = await self._get_client()
        if client:
            try:
                cached_json = await asyncio.wait_for(client.get(cache_key), timeout=0.1)
                if cached_json:
                    data = json.loads(cached_json)
                    response_dto = RagChatResponseDTO(**data)
                    response_dto.cache_hit = True
                    logger.debug("Redis cache HIT for key: %s", cache_key)
                    return response_dto
            except Exception as exc:
                logger.debug("Redis get error for key %s: %s", cache_key, exc)

        # 2. In-Memory LRU fallback
        if cache_key in self._in_memory_lru:
            expires_at, raw_json = self._in_memory_lru[cache_key]
            if now < expires_at:
                try:
                    data = json.loads(raw_json)
                    response_dto = RagChatResponseDTO(**data)
                    response_dto.cache_hit = True
                    logger.debug("In-memory cache HIT for key: %s", cache_key)
                    return response_dto
                except Exception:
                    del self._in_memory_lru[cache_key]
            else:
                del self._in_memory_lru[cache_key]

        return None

    async def set(
        self,
        query: str,
        response: RagChatResponseDTO,
        tenant_id: str = DEFAULT_TENANT_ID,
        combine_strategy: str = "single_pass_reordered",
        as_of_date: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
        user_role: str = "user",
        department: Optional[str] = None,
        similarity_threshold: Optional[float] = None,
    ) -> bool:
        """
        Stores response in cache with TTL.
        """
        # Do not cache circuit-breaker refusals or temporary errors
        if response.status == "escalation_required" or response.circuit_breaker_triggered:
            return False

        cache_key = self.compute_cache_key(
            query=query,
            tenant_id=tenant_id,
            combine_strategy=combine_strategy,
            as_of_date=as_of_date,
            user_role=user_role,
            department=department,
            similarity_threshold=similarity_threshold,
        )
        ttl = ttl_seconds or self.default_ttl
        now = time.time()

        try:
            # Prepare payload
            payload_dict = response.model_dump()
            payload_dict["cache_hit"] = True
            raw_json = json.dumps(payload_dict)

            # 1. Store in Redis
            client = await self._get_client()
            if client:
                try:
                    await asyncio.wait_for(client.set(cache_key, raw_json, ex=ttl), timeout=0.2)
                    logger.debug("Cached response in Redis for key: %s (TTL=%ds)", cache_key, ttl)
                except Exception as exc:
                    logger.debug("Redis set error for key %s: %s", cache_key, exc)

            # 2. Store in In-Memory LRU fallback
            if len(self._in_memory_lru) >= self._max_in_memory_entries:
                # Evict oldest entry
                oldest_key = next(iter(self._in_memory_lru))
                del self._in_memory_lru[oldest_key]
            self._in_memory_lru[cache_key] = (now + ttl, raw_json)
            return True
        except Exception as exc:
            logger.warning("Failed to cache response: %s", exc)
            return False

    async def get_flight_lock(self, cache_key: str) -> asyncio.Lock:
        """Single-Flight lock to prevent Cache Stampede (Dogpiling) on concurrent identical queries."""
        if not hasattr(self, "_inflight_locks"):
            self._inflight_locks = {}
            self._inflight_guard = asyncio.Lock()
        async with self._inflight_guard:
            if cache_key not in self._inflight_locks:
                self._inflight_locks[cache_key] = asyncio.Lock()
            return self._inflight_locks[cache_key]

    async def release_flight_lock(self, cache_key: str) -> None:
        """Release and cleanup in-flight lock after cache population."""
        if hasattr(self, "_inflight_guard"):
            async with self._inflight_guard:
                self._inflight_locks.pop(cache_key, None)

    async def invalidate_tenant(self, tenant_id: str) -> int:
        """
        Invalidates all cached queries for a given tenant using non-blocking SCAN.
        Never uses blocking KEYS in production (FR-EXEC-05 / EXEC-RAG-06).
        """
        norm_tenant = normalize_tenant_id(tenant_id)
        pattern = f"aip:rag:cache:{norm_tenant}:*"
        count = 0

        # Invalidate in-memory
        keys_to_del = [k for k in self._in_memory_lru if k.startswith(f"aip:rag:cache:{norm_tenant}:")]
        for k in keys_to_del:
            del self._in_memory_lru[k]
        count += len(keys_to_del)

        # Invalidate Redis using non-blocking scan_iter cursor
        client = await self._get_client()
        if client:
            try:
                batch = []
                async for key in client.scan_iter(match=pattern, count=250):
                    batch.append(key)
                    if len(batch) >= 250:
                        await client.delete(*batch)
                        count += len(batch)
                        batch = []
                if batch:
                    await client.delete(*batch)
                    count += len(batch)
                logger.info("Non-blocking invalidated %d cache keys for tenant '%s'", count, norm_tenant)
            except Exception as exc:
                logger.warning("Failed to invalidate Redis cache keys for tenant '%s': %s", norm_tenant, exc)

        return count

    async def invalidate_all(self) -> int:
        """
        Invalidates all RAG cache entries across all tenants using non-blocking SCAN.
        """
        count = len(self._in_memory_lru)
        self._in_memory_lru.clear()

        client = await self._get_client()
        if client:
            try:
                batch = []
                async for key in client.scan_iter(match="aip:rag:cache:*", count=250):
                    batch.append(key)
                    if len(batch) >= 250:
                        await client.delete(*batch)
                        count += len(batch)
                        batch = []
                if batch:
                    await client.delete(*batch)
                    count += len(batch)
                logger.info("Non-blocking invalidated %d total RAG cache keys", count)
            except Exception as exc:
                logger.warning("Failed to invalidate all Redis cache keys: %s", exc)

        return count

    async def is_healthy(self) -> bool:
        """Check cache liveness and connection health."""
        if not self._is_available:
            return False
        client = await self._get_client()
        if client:
            try:
                pong = await client.ping()
                return bool(pong)
            except Exception:
                return False
        return True


# Singleton instance
redis_cache = RedisCacheAdapter()


def get_redis_cache() -> RedisCacheAdapter:
    """Return the global Redis cache adapter singleton."""
    return redis_cache

