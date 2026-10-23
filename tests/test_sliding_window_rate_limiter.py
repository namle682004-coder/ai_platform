"""
Unit tests for Audit Item 8: Multi-Worker Sliding Window Rate Limiter.
Verifies:
1. Reverse proxy IP trust validation (anti-spoofing for X-Forwarded-For).
2. Sliding window limit enforcement (requests <= limit pass, limit + 1 raises HTTP 429).
3. Retry-After header and rate limit metadata headers.
4. Circuit breaker & fallback between Redis and in-memory.
"""

import asyncio
import time
import pytest
from starlette.requests import Request
from fastapi import HTTPException

from solutions.rag.interfaces.api.rate_limiter import SlidingWindowRateLimiter


def make_mock_request(
    client_host: str = "127.0.0.1",
    headers: dict = None,
    tenant_id: str = None,
) -> Request:
    raw_headers = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))

    scope = {
        "type": "http",
        "client": (client_host, 54321),
        "headers": raw_headers,
        "state": {},
    }
    if tenant_id:
        scope["state"]["tenant_id"] = tenant_id

    return Request(scope)


def test_ip_anti_spoofing_untrusted_client():
    """External/public IPs cannot spoof their identity using X-Forwarded-For."""
    limiter = SlidingWindowRateLimiter()

    # External public IP attempting to spoof as internal IP
    req = make_mock_request(
        client_host="8.8.8.8",  # Public internet IP
        headers={"X-Forwarded-For": "10.0.0.1"},
    )
    tid, client_ip = limiter._extract_rate_key(req)
    # Must use actual client_host, ignoring spoofed header
    assert client_ip == "8.8.8.8"


def test_ip_trusted_proxy_forwarding():
    """Trusted loopback or private proxy correctly passes through genuine forwarded client IP."""
    limiter = SlidingWindowRateLimiter()

    req = make_mock_request(
        client_host="127.0.0.1",
        headers={"X-Forwarded-For": "142.250.190.46, 10.0.0.1"},
    )
    tid, client_ip = limiter._extract_rate_key(req)
    assert client_ip == "142.250.190.46"


def test_sliding_window_enforcement_in_memory():
    """Verify in-memory sliding window allows up to limit and blocks on limit + 1."""
    async def _run():
        limiter = SlidingWindowRateLimiter(default_rpm=5, window_seconds=60.0)
        # Force in-memory fallback
        limiter._check_redis = lambda *args, **kwargs: asyncio.sleep(0, result=None)

        req = make_mock_request(client_host="192.168.1.50")

        # 5 requests must pass
        for _ in range(5):
            await limiter.check_rate_limit(req, rpm_limit=5)
            assert req.state.rate_limit_headers["X-RateLimit-Limit"] == "5"

        # 6th request must be rejected with 429
        with pytest.raises(HTTPException) as exc_info:
            await limiter.check_rate_limit(req, rpm_limit=5)

        assert exc_info.value.status_code == 429
        assert "Retry-After" in exc_info.value.headers
        assert exc_info.value.headers["X-RateLimit-Remaining"] == "0"

    asyncio.run(_run())


def test_sliding_window_sliding_recovery():
    """Verify that requests slide out of the window as time elapses."""
    async def _run():
        limiter = SlidingWindowRateLimiter(default_rpm=2, window_seconds=0.5)
        limiter._check_redis = lambda *args, **kwargs: asyncio.sleep(0, result=None)

        req = make_mock_request(client_host="192.168.1.60")

        # 2 requests pass
        await limiter.check_rate_limit(req, rpm_limit=2)
        await limiter.check_rate_limit(req, rpm_limit=2)

        # 3rd request blocked
        with pytest.raises(HTTPException):
            await limiter.check_rate_limit(req, rpm_limit=2)

        # Wait for window to expire
        await asyncio.sleep(0.6)

        # Should pass again
        await limiter.check_rate_limit(req, rpm_limit=2)

    asyncio.run(_run())


def test_redis_lua_sliding_window_integration():
    """Verify atomic Lua script sliding window directly on Redis instance."""
    async def _run():
        import uuid
        try:
            import redis.asyncio as aioredis
        except ImportError:
            pytest.skip("aioredis not installed")

        try:
            r = aioredis.from_url("redis://:redis_dev_secret@172.16.20.2:6380/0", socket_timeout=1.5)
            await r.ping()
        except Exception:
            pytest.skip("Remote Redis not reachable")

        from solutions.rag.interfaces.api.rate_limiter import SLIDING_WINDOW_LUA

        key = f"aip:ratelimit:test_integration:{uuid.uuid4().hex[:8]}"
        now = time.time()

        try:
            # First 3 requests with limit=3 must pass
            for _ in range(3):
                res = await r.eval(SLIDING_WINDOW_LUA, 1, key, str(now), "60", "3", str(uuid.uuid4()))
                assert res[0] == 1
                assert res[1] >= 0

            # 4th request must be rejected
            res4 = await r.eval(SLIDING_WINDOW_LUA, 1, key, str(now), "60", "3", str(uuid.uuid4()))
            assert res4[0] == 0
            assert res4[2] > 0
        finally:
            await r.delete(key)
            if hasattr(r, "aclose"):
                await r.aclose()
            else:
                await r.close()

    asyncio.run(_run())


def test_in_memory_pruning_zero_memory_leak():
    """Verify that old/inactive keys are pruned to prevent memory leak."""
    async def _run():
        limiter = SlidingWindowRateLimiter(default_rpm=10, window_seconds=60.0, cleanup_interval_seconds=1.0)
        limiter._last_cleanup = 0.0

        # Simulate old requests from 100 seconds ago
        old_time = 1000.0
        limiter._windows["tenant_a:1.2.3.4"].append(old_time)
        limiter._windows["tenant_b:5.6.7.8"].append(old_time + 10)

        # Prune at current time = 2000.0 (> cutoff of 1940.0)
        await limiter._prune_expired_in_memory_windows(2000.0)

        # Both keys must be completely evicted from the dict
        assert "tenant_a:1.2.3.4" not in limiter._windows
        assert "tenant_b:5.6.7.8" not in limiter._windows
        assert len(limiter._windows) == 0

    asyncio.run(_run())


def test_multi_worker_shared_state_simulation():
    """
    Verify that multiple workers sharing Redis state strictly enforce 1 global RPM limit.
    Simulates Worker A and Worker B (e.g. Uvicorn --workers 2) handling interleaved requests.
    """
    async def _run():
        shared_redis_zset = {}  # key -> list of (timestamp, member)

        async def mock_check_redis(self, rate_key: str, limit: int, now: float):
            # Atomic simulation of SLIDING_WINDOW_LUA
            zset = shared_redis_zset.setdefault(rate_key, [])
            cutoff = now - self.window_seconds
            # 1. ZREMRANGEBYSCORE
            shared_redis_zset[rate_key] = [item for item in zset if item[0] >= cutoff]
            zset = shared_redis_zset[rate_key]
            current_count = len(zset)
            if current_count < limit:
                zset.append((now, "member"))
                return True, limit - (current_count + 1), 0, current_count + 1
            else:
                oldest_ts = zset[0][0]
                retry_after = max(1, int(oldest_ts + self.window_seconds - now) + 1)
                return False, 0, retry_after, current_count

        # Worker A and Worker B instances
        worker_a = SlidingWindowRateLimiter(default_rpm=5, window_seconds=60.0)
        worker_b = SlidingWindowRateLimiter(default_rpm=5, window_seconds=60.0)
        worker_a._check_redis = lambda rk, lim, t: mock_check_redis(worker_a, rk, lim, t)
        worker_b._check_redis = lambda rk, lim, t: mock_check_redis(worker_b, rk, lim, t)

        req = make_mock_request(client_host="192.168.1.100", tenant_id="tenant_x")

        # Worker A handles 3 requests
        for _ in range(3):
            await worker_a.check_rate_limit(req, rpm_limit=5)

        # Worker B handles 2 requests (total 5 requests)
        for _ in range(2):
            await worker_b.check_rate_limit(req, rpm_limit=5)

        # 6th request arriving at Worker A MUST be blocked with HTTP 429
        with pytest.raises(HTTPException) as exc_info:
            await worker_a.check_rate_limit(req, rpm_limit=5)
        assert exc_info.value.status_code == 429

        # 7th request arriving at Worker B MUST also be blocked with HTTP 429
        with pytest.raises(HTTPException) as exc_info:
            await worker_b.check_rate_limit(req, rpm_limit=5)
        assert exc_info.value.status_code == 429

    asyncio.run(_run())


def test_rate_limit_header_middleware_integration():
    """Verify that RateLimitHeaderMiddleware propagates headers to HTTP responses."""
    from fastapi import FastAPI, Depends
    from fastapi.testclient import TestClient
    from solutions.rag.interfaces.api.rate_limiter import RateLimitHeaderMiddleware, RateLimitDependency

    app = FastAPI()
    app.add_middleware(RateLimitHeaderMiddleware)

    dep = RateLimitDependency(requests_per_minute=20)

    @app.get("/test-endpoint", dependencies=[Depends(dep)])
    def _test_endpoint():
        return {"status": "ok"}

    client = TestClient(app)
    response = client.get("/test-endpoint")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "X-RateLimit-Limit" in response.headers
    assert response.headers["X-RateLimit-Limit"] == "20"
    assert "X-RateLimit-Remaining" in response.headers
    assert response.headers["X-RateLimit-Remaining"] == "19"
    assert "X-RateLimit-Reset" in response.headers


