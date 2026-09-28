"""
Redis-Backed Idempotency Service for AIP Platform.
Inspired by DCP Idempotency Engine.

Ensures that duplicate requests carrying an Idempotency-Key header within
a 24-hour window return the cached initial response rather than re-executing
expensive GPU workloads or creating duplicate task dispatches.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from src.db.redis import redis_service

logger = logging.getLogger("aip-gateway.idempotency")

IDEMPOTENCY_TTL_SECONDS: int = 86400  # 24 hours


def _make_redis_key(tenant_id: str, idempotency_key: str) -> str:
    clean_tenant = tenant_id.strip() or "global"
    clean_key = idempotency_key.strip()
    return f"aip:idempotency:{clean_tenant}:{clean_key}"


class IdempotencyService:
    """Service to record and look up idempotent request results in Redis with in-memory fallback."""

    def __init__(self):
        self._mem_store: dict[str, dict[str, Any]] = {}

    async def get_cached_response(
        self,
        tenant_id: str,
        idempotency_key: Optional[str],
    ) -> Optional[dict[str, Any]]:
        """
        Check if an idempotency key already exists.
        Returns cached response dict if found, None otherwise.
        """
        if not idempotency_key or not idempotency_key.strip():
            return None

        redis_key = _make_redis_key(tenant_id, idempotency_key)
        try:
            cached = await redis_service.get_json(redis_key)
            if cached:
                logger.info(
                    "Idempotency cache hit for key '%s' (tenant='%s')",
                    idempotency_key,
                    tenant_id,
                )
                return cached
        except Exception as exc:
            logger.warning("Failed to query idempotency key in Redis: %s", exc)

        return self._mem_store.get(redis_key)

    async def save_response(
        self,
        tenant_id: str,
        idempotency_key: Optional[str],
        response_data: dict[str, Any],
        ttl_seconds: int = IDEMPOTENCY_TTL_SECONDS,
    ) -> bool:
        """
        Cache response for an idempotency key.
        """
        if not idempotency_key or not idempotency_key.strip():
            return False

        redis_key = _make_redis_key(tenant_id, idempotency_key)
        self._mem_store[redis_key] = response_data
        try:
            success = await redis_service.set_json(
                redis_key,
                response_data,
                ttl_seconds=ttl_seconds,
            )
            return success
        except Exception as exc:
            logger.warning("Failed to save idempotency response in Redis: %s", exc)
            return True

    async def claim(self, tenant_id: str, idempotency_key: Optional[str]) -> Optional[bool]:
        """Atomically reserve a key; falls back to local memory store if Redis is unavailable."""
        if not idempotency_key or not idempotency_key.strip():
            return False
        redis_key = _make_redis_key(tenant_id, idempotency_key)

        try:
            client = redis_service.get_client()
            import json
            serialized = json.dumps({"status": "in_progress"}, ensure_ascii=False)
            res = await client.set(redis_key, serialized, ex=IDEMPOTENCY_TTL_SECONDS, nx=True)
            if res is not None:
                self._mem_store[redis_key] = {"status": "in_progress"}
                return True
            else:
                return False
        except Exception as exc:
            logger.warning("Redis unavailable for idempotency claim, using memory fallback: %s", exc)
            if redis_key in self._mem_store:
                return False
            self._mem_store[redis_key] = {"status": "in_progress"}
            return True


idempotency_service = IdempotencyService()
