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
    """Service to record and look up idempotent request results in Redis."""

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

        return None

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
        try:
            success = await redis_service.set_json(
                redis_key,
                response_data,
                ttl_seconds=ttl_seconds,
            )
            return success
        except Exception as exc:
            logger.warning("Failed to save idempotency response in Redis: %s", exc)
            return False

    async def claim(self, tenant_id: str, idempotency_key: Optional[str]) -> Optional[bool]:
        """Atomically reserve a key; None means Redis was unavailable."""
        if not idempotency_key or not idempotency_key.strip():
            return False
        try:
            return await redis_service.set_json(
                _make_redis_key(tenant_id, idempotency_key),
                {"status": "in_progress"},
                ttl_seconds=IDEMPOTENCY_TTL_SECONDS,
                nx=True,
            )
        except Exception as exc:
            logger.warning("Failed to claim idempotency key: %s", exc)
            return None


idempotency_service = IdempotencyService()
