"""
Production Sliding-Window Rate Limiter for AIP Enterprise RAG API (NFR-6.2).
Enforces 120 requests/minute per tenant and IP with sliding window accuracy,
returning HTTP 429 Too Many Requests and standard Retry-After headers.

Production-grade implementation:
- Atomic Redis ZSET sliding-window via Lua script supporting multi-worker (Uvicorn --workers N).
- Zero state loss across server restarts and automatic key TTL (zero memory leaks).
- Reverse proxy IP validation to prevent X-Forwarded-For spoofing.
- Graceful in-memory fallback if Redis is unreachable.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
import ipaddress
import logging
import math
import time
from typing import Any, Deque, Dict, Optional, Tuple
import uuid

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from ...config import rag_settings
from ...domain.entities import normalize_tenant_id
from ...infrastructure.adapters.redis_cache_adapter import get_redis_cache

logger = logging.getLogger("aip-rag.api.rate_limiter")

# Atomic Sliding-Window Lua Script for Redis
# Returns: [allowed (1/0), remaining, retry_after, current_count]
SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
local clear_before = now - window

-- 1. Remove expired requests outside the sliding window
redis.call('ZREMRANGEBYSCORE', key, '-inf', clear_before)

-- 2. Count requests currently in sliding window
local current_count = redis.call('ZCARD', key)

if current_count < limit then
    -- 3. Add current request timestamp and refresh TTL
    redis.call('ZADD', key, now, member)
    redis.call('EXPIRE', key, math.ceil(window) + 15)
    local remaining = limit - (current_count + 1)
    return {1, remaining, 0, current_count + 1}
else
    -- 4. Over limit: calculate exact Retry-After from oldest entry in current window
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = 1
    if oldest and #oldest >= 2 then
        local oldest_ts = tonumber(oldest[2])
        retry_after = math.ceil(oldest_ts + window - now)
        if retry_after < 1 then retry_after = 1 end
    end
    return {0, 0, retry_after, current_count}
end
"""


class SlidingWindowRateLimiter:
    """
    Multi-worker atomic Redis sliding-window rate limiter with in-memory fallback.
    Maintains timestamp logs per rate key and enforces limits within a moving 60-second window.
    """

    def __init__(
        self,
        default_rpm: int = 120,
        window_seconds: float = 60.0,
        cleanup_interval_seconds: float = 300.0,
    ) -> None:
        self.default_rpm = default_rpm
        self.window_seconds = window_seconds
        self.cleanup_interval_seconds = cleanup_interval_seconds
        # In-memory fallback structures
        self._windows: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()
        self._last_cleanup = time.time()

    @staticmethod
    def _is_private_or_loopback(ip_str: str) -> bool:
        """Check if an IP address belongs to loopback or private subnets."""
        try:
            ip = ipaddress.ip_address(ip_str)
            return ip.is_loopback or ip.is_private
        except ValueError:
            return False

    def _extract_rate_key(self, request: Request, tenant_id: Optional[str] = None) -> Tuple[str, str]:
        """
        Extract compound (tenant_id, client_ip) key for rate limiting.
        Prevents X-Forwarded-For header spoofing by validating proxy trust.
        """
        # 1. Tenant ID from request state, explicit param, or headers
        tid = tenant_id
        if not tid:
            tid = getattr(request.state, "tenant_id", None)
        if not tid:
            tid = request.headers.get("X-Tenant-ID") or request.headers.get("X-Tenant-Id")
        tid = normalize_tenant_id(tid)

        # 2. Client IP respecting reverse proxy headers only from trusted network origins
        direct_ip = request.client.host if request.client else "127.0.0.1"
        if self._is_private_or_loopback(direct_ip):
            forwarded = request.headers.get("X-Forwarded-For")
            real_ip = request.headers.get("X-Real-IP")
            if forwarded:
                client_ip = forwarded.split(",")[0].strip()
            elif real_ip:
                client_ip = real_ip.strip()
            else:
                client_ip = direct_ip
        else:
            # Untrusted direct connection: strictly use direct peer IP to block header spoofing
            client_ip = direct_ip

        return tid, client_ip

    async def _prune_expired_in_memory_windows(self, now: float) -> None:
        """Periodic cleanup to avoid memory leak for inactive tenants/IPs in in-memory fallback mode."""
        if now - self._last_cleanup < self.cleanup_interval_seconds:
            return
        self._last_cleanup = now
        cutoff = now - self.window_seconds
        keys_to_remove = []
        for key, timestamps in self._windows.items():
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()
            if not timestamps:
                keys_to_remove.append(key)
        for key in keys_to_remove:
            self._windows.pop(key, None)

    async def _check_redis(
        self,
        rate_key: str,
        limit: int,
        now: float,
    ) -> Optional[Tuple[bool, int, int, int]]:
        """
        Evaluate sliding window via Redis Lua script.
        Returns (allowed, remaining, retry_after, current_count) or None if Redis unavailable.
        """
        try:
            cache = get_redis_cache()
            client = await cache._get_client()
            if client is None:
                return None

            redis_key = f"aip:ratelimit:{rate_key}"
            member_id = f"{now}:{uuid.uuid4().hex[:8]}"

            # Execute atomic sliding window script
            res = await client.eval(
                SLIDING_WINDOW_LUA,
                1,
                redis_key,
                str(now),
                str(self.window_seconds),
                str(limit),
                member_id,
            )
            if res and isinstance(res, (list, tuple)) and len(res) >= 4:
                allowed = bool(res[0])
                remaining = int(res[1])
                retry_after = int(res[2])
                current_count = int(res[3])
                return allowed, remaining, retry_after, current_count
        except Exception as exc:
            logger.debug("Redis rate limit evaluation failed, falling back to memory: %s", exc)

        return None

    async def _check_in_memory(
        self,
        rate_key: str,
        limit: int,
        now: float,
    ) -> Tuple[bool, int, int, int]:
        """Fallback evaluation using in-memory deques when Redis is offline."""
        cutoff = now - self.window_seconds
        async with self._lock:
            await self._prune_expired_in_memory_windows(now)
            timestamps = self._windows[rate_key]

            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()

            current_count = len(timestamps)
            if current_count >= limit:
                oldest_in_window = timestamps[0]
                retry_after = max(1, int(oldest_in_window + self.window_seconds - now) + 1)
                return False, 0, retry_after, current_count

            timestamps.append(now)
            remaining = max(0, limit - (current_count + 1))
            return True, remaining, 0, current_count + 1

    async def check_rate_limit(
        self,
        request: Request,
        rpm_limit: Optional[int] = None,
        tenant_id: Optional[str] = None,
    ) -> None:
        """
        Evaluate sliding window rate limit for the incoming request.
        Raises HTTP 429 if request exceeds rate limit.
        """
        limit = rpm_limit or self.default_rpm
        tid, client_ip = self._extract_rate_key(request, tenant_id=tenant_id)
        rate_key = f"{tid}:{client_ip}"
        now = time.time()

        # 1. Primary: Evaluate in distributed Redis (atomic across all Uvicorn workers)
        redis_result = await self._check_redis(rate_key, limit, now)

        # 2. Fallback: If Redis is offline, evaluate in thread-safe memory deque
        if redis_result is not None:
            allowed, remaining, retry_after, current_count = redis_result
        else:
            allowed, remaining, retry_after, current_count = await self._check_in_memory(rate_key, limit, now)

        if not allowed:
            logger.warning(
                "Rate limit exceeded for key '%s' (%d/%d rpm). Retry-After: %ds",
                rate_key,
                current_count,
                limit,
                retry_after,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Maximum {limit} requests per minute allowed.",
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(now + retry_after)),
                },
            )

        # Set rate limit headers on response via request.state
        request.state.rate_limit_headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(int(now + self.window_seconds)),
        }


# Singleton limiter instance
rate_limiter = SlidingWindowRateLimiter(default_rpm=120, window_seconds=60.0)


class RateLimitDependency:
    """FastAPI Depends helper for configurable per-endpoint rate limits."""

    def __init__(self, requests_per_minute: int = 120) -> None:
        self.rpm = requests_per_minute

    async def __call__(self, request: Request) -> None:
        await rate_limiter.check_rate_limit(request, rpm_limit=self.rpm)


class RateLimitHeaderMiddleware(BaseHTTPMiddleware):
    """
    Middleware that propagates rate limit headers (X-RateLimit-Limit,
    X-RateLimit-Remaining, X-RateLimit-Reset) from request.state to HTTP responses.
    Ensures RFC-compliant headers are returned on all endpoints.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        rl_headers = getattr(request.state, "rate_limit_headers", None)
        if rl_headers and isinstance(rl_headers, dict):
            for k, v in rl_headers.items():
                response.headers[k] = str(v)
        return response
