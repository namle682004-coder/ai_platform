import os
import time
import math
import hmac
import hashlib
import logging
from typing import Tuple, Dict, Optional
from src.db.redis import redis_service

logger = logging.getLogger("aip-quota.enforcer")

_WINDOW_SECONDS = 60
_DEFAULT_RPM = 60
_DEFAULT_CONCURRENCY = 5

# Redis Atomic Lua Script for Sliding Window Rate Limit & Concurrency
# Executes in a single round-trip with zero race conditions
LUA_RATE_LIMIT_AND_CONCURRENCY = """
local cur_key = KEYS[1]
local prev_key = KEYS[2]
local conc_key = KEYS[3]

local window_ttl = tonumber(ARGV[1])
local prev_weight = tonumber(ARGV[2])
local rpm_limit = tonumber(ARGV[3])
local conc_limit = tonumber(ARGV[4])

-- 1. Check & Enforce In-Flight Concurrency
local current_conc = redis.call('GET', conc_key)
current_conc = current_conc and tonumber(current_conc) or 0
if conc_limit > 0 and current_conc >= conc_limit then
    return {0, "concurrency_exceeded", current_conc, 0, 0}
end

-- 2. Check Sliding Window Rate Limit
local prev_count = redis.call('GET', prev_key)
prev_count = prev_count and tonumber(prev_count) or 0
local cur_count = redis.call('GET', cur_key)
cur_count = cur_count and tonumber(cur_count) or 0
local weighted = (prev_count * prev_weight) + cur_count + 1

if rpm_limit > 0 and weighted > rpm_limit then
    return {0, "rate_limit_exceeded", current_conc, math.ceil(weighted), 0}
end

-- 3. Atomic increment on both counters
redis.call('INCR', cur_key)
redis.call('EXPIRE', cur_key, window_ttl)
redis.call('INCR', conc_key)
redis.call('EXPIRE', conc_key, 300)

local remaining = math.max(0, rpm_limit - math.ceil(weighted))
return {1, "ok", current_conc + 1, math.ceil(weighted), remaining}
"""

LUA_RELEASE_CONCURRENCY = """
local conc_key = KEYS[1]
local current_conc = redis.call('GET', conc_key)
if current_conc and tonumber(current_conc) > 0 then
    return redis.call('DECR', conc_key)
else
    return 0
end
"""


class QuotaEnforcer:
    """
    Enterprise Quota & Rate Limit Enforcer.
    - Redis Sliding-Window weighted algorithm.
    - Redis Atomic Lua script for concurrency and rate limit evaluation.
    - HMAC-SHA256 salted bucket token isolation.
    - In-flight concurrency protection.
    - Graceful fail-open on cache degradation.
    """

    def __init__(self, salt: Optional[str] = None):
        self._salt = (salt or os.getenv("RATE_LIMIT_BUCKET_SALT", "aip-rate-limit-salt")).encode("utf-8")
        self._concurrency_counter: Dict[str, int] = {}

    def resolve_bucket(self, api_key: Optional[str], client_ip: str = "unknown") -> str:
        if api_key:
            digest = hmac.new(self._salt, api_key.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
            return f"key:{digest}"
        return f"ip:{client_ip}"

    def acquire_concurrency(self, bucket: str, limit: int = _DEFAULT_CONCURRENCY) -> bool:
        """Synchronous in-memory check (retained for backward compatibility and unit tests)."""
        current = self._concurrency_counter.get(bucket, 0)
        if current >= limit:
            return False
        self._concurrency_counter[bucket] = current + 1
        return True

    def release_concurrency(self, bucket: str):
        """Release concurrency slot in both local memory and Redis."""
        if bucket in self._concurrency_counter and self._concurrency_counter[bucket] > 0:
            self._concurrency_counter[bucket] -= 1

        try:
            client = redis_service.get_client()
            if client:
                conc_key = f"aip:concurrency:{bucket}"
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(client.eval(LUA_RELEASE_CONCURRENCY, 1, conc_key))
        except Exception:
            pass

    async def check_atomic_quota(
        self,
        bucket: str,
        rpm_limit: int = _DEFAULT_RPM,
        concurrency_limit: int = _DEFAULT_CONCURRENCY,
    ) -> Tuple[bool, str, Dict[str, str], int]:
        """
        SRS Section 3.1: Check rate limit, quota, and concurrency in a single Redis atomic Lua script.
        Returns: (allowed, error_code, rate_headers, current_concurrency)
        """
        now = time.time()
        window = _WINDOW_SECONDS
        current_window_start = int(now // window) * window
        previous_window_start = current_window_start - window
        elapsed = now - current_window_start
        previous_weight = max(0.0, 1.0 - (elapsed / window))

        cur_key = f"aip:ratelimit:{bucket}:{current_window_start}"
        prev_key = f"aip:ratelimit:{bucket}:{previous_window_start}"
        conc_key = f"aip:concurrency:{bucket}"

        reset_seconds = max(1, int(math.ceil(window - elapsed)))
        remaining = rpm_limit

        try:
            client = redis_service.get_client()
            if client:
                res = await client.eval(
                    LUA_RATE_LIMIT_AND_CONCURRENCY,
                    3,
                    cur_key,
                    prev_key,
                    conc_key,
                    window * 2,
                    round(previous_weight, 4),
                    rpm_limit,
                    concurrency_limit,
                )
                # res format: {allowed (0/1), status_str, current_conc, weighted_count, remaining}
                is_allowed = bool(res[0] == 1)
                status_reason = str(res[1])
                curr_conc = int(res[2])
                remaining = int(res[4])

                headers = {
                    "X-RateLimit-Limit": str(rpm_limit),
                    "X-RateLimit-Remaining": str(remaining),
                    "X-RateLimit-Reset": str(reset_seconds),
                }
                return is_allowed, status_reason, headers, curr_conc
        except Exception as exc:
            logger.error(f"Redis atomic Lua rate-limit unavailable: {exc}")
            return False, "rate_limit_store_unavailable", {"X-RateLimit-Reset": "5"}, 0

    async def check_and_increment(
        self,
        bucket: str,
        limit: int = _DEFAULT_RPM,
    ) -> Tuple[bool, float, Dict[str, str]]:
        """Classic sliding window increment (retained for backward compatibility)."""
        now = time.time()
        window = _WINDOW_SECONDS
        current_window_start = int(now // window) * window
        previous_window_start = current_window_start - window
        elapsed = now - current_window_start
        previous_weight = max(0.0, 1.0 - (elapsed / window))

        cur_key = f"aip:ratelimit:{bucket}:{current_window_start}"
        prev_key = f"aip:ratelimit:{bucket}:{previous_window_start}"

        try:
            client = redis_service.get_client()
            pipe = client.pipeline()
            pipe.incr(cur_key)
            pipe.expire(cur_key, window * 2)
            pipe.get(prev_key)
            results = await pipe.execute()
            current_count = int(results[0])
            prev_raw = results[2]
            previous_count = int(prev_raw) if prev_raw is not None else 0
            weighted = (previous_count * previous_weight) + current_count
        except Exception as exc:
            logger.warning(f"Redis pipeline failed during rate-limit check; failing open: {exc}")
            weighted = 1.0

        remaining = max(0, int(limit - math.ceil(weighted)))
        reset_seconds = max(1, int(math.ceil(window - elapsed)))

        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_seconds),
        }

        allowed = weighted <= limit
        return allowed, weighted, headers

    def check_media_quota(
        self,
        file_size_bytes: int,
        media_type: str = "audio",
        is_vip: bool = False,
    ) -> Tuple[bool, str]:
        limits_standard = {
            "audio": 10 * 1024 * 1024,
            "image": 5 * 1024 * 1024,
            "video": 25 * 1024 * 1024,
            "document": 15 * 1024 * 1024,
        }
        multiplier = 5 if is_vip else 1
        max_bytes = limits_standard.get(media_type, 10 * 1024 * 1024) * multiplier

        if file_size_bytes > max_bytes:
            max_mb = max_bytes / (1024 * 1024)
            actual_mb = file_size_bytes / (1024 * 1024)
            return False, f"Tệp tải lên {actual_mb:.2f} MB vượt quá hạn mức Media Quota cho phép ({max_mb:.0f} MB)."
        return True, ""

    async def acquire_job_concurrency(self, tenant_id: str, limit: int = 5) -> Tuple[bool, int]:
        try:
            client = redis_service.get_client()
            if client:
                key = f"aip:jobs:active:{tenant_id}"
                current = await client.get(key)
                count = int(current) if current is not None else 0
                if count >= limit:
                    return False, count
                new_count = await client.incr(key)
                await client.expire(key, 86400)
                return True, new_count
        except Exception as exc:
            logger.warning(f"Failed to check job concurrency in Redis: {exc}")
        return True, 1

    async def release_job_concurrency(self, tenant_id: str):
        try:
            client = redis_service.get_client()
            if client:
                key = f"aip:jobs:active:{tenant_id}"
                current = await client.get(key)
                if current and int(current) > 0:
                    await client.decr(key)
        except Exception as exc:
            logger.warning(f"Failed to release job concurrency: {exc}")


quota_enforcer = QuotaEnforcer()
