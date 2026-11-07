"""
Overload protection of the RAG service (model host incident 2026-11-05): runtime bulkhead and circuit
breaker, no retry of read timeouts, chat admission, chat rate limits and the busy reply.
"""

import asyncio

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from solutions.rag.application.use_cases.chat_use_case import (
    BUSY_MESSAGE,
    OUTAGE_MESSAGE,
    ChatAdmission,
    unavailable_reply,
)
from solutions.rag.config import rag_settings
from solutions.rag.domain.exceptions import LLMGenerationError, ServiceOverloadedError
from solutions.rag.infrastructure.adapters import runtime_guard as rg
from solutions.rag.infrastructure.adapters.model_registry import ModelRuntimeError, post_json_with_retry
from solutions.rag.interfaces.api.rate_limiter import ChatRateLimitDependency, SlidingWindowRateLimiter


@pytest.fixture(autouse=True)
def _fresh_guards(monkeypatch):
    monkeypatch.setattr(rag_settings, "llm_max_concurrent", 1)
    monkeypatch.setattr(rag_settings, "runtime_queue_timeout_seconds", 0.05)
    monkeypatch.setattr(rag_settings, "runtime_breaker_failures", 2)
    monkeypatch.setattr(rag_settings, "runtime_breaker_cooldown_seconds", 0.2)
    rg.reset_guards()
    yield
    rg.reset_guards()


def test_bulkhead_refuses_calls_beyond_capacity():
    guard = rg.runtime_guard("llm")

    async def scenario():
        release = asyncio.Event()

        async def holder():
            async with guard.slot():
                await release.wait()
                guard.record_success()

        task = asyncio.create_task(holder())
        await asyncio.sleep(0.01)
        with pytest.raises(rg.RuntimeOverloadedError) as err:
            async with guard.slot():
                pass
        release.set()
        await task
        return err.value

    err = asyncio.run(scenario())
    assert isinstance(err, ServiceOverloadedError) and err.retry_after >= 1
    assert guard.rejected == 1 and guard.in_flight == 0


def test_breaker_opens_after_failures_fails_fast_then_recovers():
    guard = rg.runtime_guard("llm")

    async def fail():
        async with guard.slot():
            guard.record_failure()

    async def scenario():
        await fail()
        await fail()
        assert guard.state == rg.OPEN
        with pytest.raises(rg.RuntimeOverloadedError, match="circuit open"):
            async with guard.slot():
                pass
        await asyncio.sleep(0.25)  # cooldown over: one trial call is let through
        assert guard.state == rg.HALF_OPEN
        async with guard.slot():
            guard.record_success()
        assert guard.state == rg.CLOSED

    asyncio.run(scenario())


def test_calls_cancelled_by_their_caller_do_not_open_the_breaker():
    """A burst: callers give up on a busy but healthy runtime (their own deadline). Not runtime failures."""
    guard = rg.runtime_guard("llm")

    async def slow_call():
        async with guard.slot():
            await asyncio.sleep(1)  # the runtime is working; the caller's deadline is shorter
            guard.record_success()

    async def scenario():
        for _ in range(3):
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(slow_call(), timeout=0.02)
        return guard.state, guard.snapshot()["consecutive_failures"], guard.in_flight

    assert asyncio.run(scenario()) == (rg.CLOSED, 0, 0)


def test_failed_trial_reopens_and_unreported_exception_counts_as_failure():
    guard = rg.runtime_guard("llm")

    async def scenario():
        for _ in range(2):
            with pytest.raises(ValueError):
                async with guard.slot():
                    raise ValueError("boom")  # not reported by the caller: still a failure
        assert guard.state == rg.OPEN
        await asyncio.sleep(0.25)
        with pytest.raises(ValueError):
            async with guard.slot():
                raise ValueError("still down")
        assert guard.state == rg.OPEN  # the trial failed: open again for a full cooldown

    asyncio.run(scenario())


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_read_timeout_is_not_retried_and_opens_the_breaker():
    calls = []

    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout("slow", request=request)

    async def scenario():
        async with _client(handler) as client:
            for _ in range(2):
                with pytest.raises(ModelRuntimeError):
                    await post_json_with_retry(client, "http://m/v1/chat/completions", {}, {}, 1.0,
                                               max_retries=2, kind="llm")
            with pytest.raises(rg.RuntimeOverloadedError):
                await post_json_with_retry(client, "http://m/v1/chat/completions", {}, {}, 1.0,
                                           max_retries=2, kind="llm")

    asyncio.run(scenario())
    assert len(calls) == 2  # one attempt per call, and none once the breaker is open


def test_connection_errors_and_gateway_errors_are_retried_and_success_closes():
    replies = iter([httpx.ConnectError("refused"), 503, 200])

    def handler(request):
        r = next(replies)
        if isinstance(r, Exception):
            raise r
        return httpx.Response(r, json={"ok": True}, headers={"Retry-After": "0"})

    async def scenario():
        async with _client(handler) as client:
            return await post_json_with_retry(client, "http://m/v1/x", {}, {}, 1.0, max_retries=2, kind="llm")

    assert asyncio.run(scenario()) == {"ok": True}
    assert rg.runtime_guard("llm").state == rg.CLOSED


def test_chat_admission_refuses_turns_beyond_the_limit():
    admission = ChatAdmission(limit=1)

    async def scenario():
        async with admission.turn():
            with pytest.raises(ServiceOverloadedError):
                async with admission.turn():
                    pass
        async with admission.turn():  # released: admitted again
            pass

    asyncio.run(scenario())
    assert admission.rejected == 1 and admission.in_flight == 0


def test_busy_and_outage_replies():
    overload = rg.RuntimeOverloadedError("llm", "full", 12)
    wrapped = LLMGenerationError("generation failed")
    wrapped.__cause__ = overload
    assert unavailable_reply(overload) == (BUSY_MESSAGE, 12, True)
    assert unavailable_reply(wrapped) == (BUSY_MESSAGE, 12, True)
    assert unavailable_reply(LLMGenerationError("down")) == (OUTAGE_MESSAGE, 5, False)


def _request(tenant="t1", ip="10.0.0.1"):
    scope = {"type": "http", "method": "POST", "path": "/v1/rag/chat", "headers": [(b"x-tenant-id", tenant.encode())],
             "client": (ip, 1234)}
    return Request(scope)


def test_chat_rate_limits_per_client_and_service_wide(monkeypatch):
    import importlib

    rl = importlib.import_module("solutions.rag.interfaces.api.rate_limiter")
    limiter = SlidingWindowRateLimiter(default_rpm=120)

    async def no_redis(*_a, **_k):
        return None

    monkeypatch.setattr(limiter, "_check_redis", no_redis)
    monkeypatch.setattr(rl, "rate_limiter", limiter)
    monkeypatch.setattr(rag_settings, "chat_rate_limit_per_minute", 2)
    monkeypatch.setattr(rag_settings, "chat_global_rate_limit_per_minute", 3)
    dep = ChatRateLimitDependency()

    async def scenario():
        await dep(_request("t1"))
        await dep(_request("t1"))
        with pytest.raises(HTTPException) as per_client:
            await dep(_request("t1"))
        await dep(_request("t2", "10.0.0.2"))  # another client: its own budget ...
        with pytest.raises(HTTPException) as global_limit:
            await dep(_request("t3", "10.0.0.3"))  # ... but the service-wide budget (3) is used up
        return per_client.value, global_limit.value

    per_client, global_limit = asyncio.run(scenario())
    assert per_client.status_code == 429 and global_limit.status_code == 429
    assert "Retry-After" in global_limit.headers


def test_evaluation_client_waits_when_busy_and_suite_stops_on_a_failing_service(tmp_path, monkeypatch):
    from benchmarks.rag.src.rag_benchmark.adapters import rag_api
    from benchmarks.rag.src.rag_benchmark.runner.suite import SuiteOptions, run_suite
    from benchmarks.rag.src.rag_benchmark.schemas.dataset import GoldenCase

    monkeypatch.setattr(rag_api, "BUSY_MIN_WAIT_S", 0.0)
    replies = iter([503, 200])

    def busy_then_ok(request):
        if request.url.path == "/v1/rag/chat":
            code = next(replies)
            if code == 503:
                return httpx.Response(503, headers={"Retry-After": "0"}, json={"detail": "busy"})
            return httpx.Response(200, json={"answer": "12 ngày", "status": "success"})
        return httpx.Response(404)

    async def one_turn():
        client = rag_api.RagApiClient("http://rag", transport=httpx.MockTransport(busy_then_ok))
        try:
            return await client.chat("Ngày phép?", "s1")
        finally:
            await client.aclose()

    turn = asyncio.run(one_turn())
    assert turn.answer == "12 ngày" and turn.error is None  # waited, asked again, answered

    calls = []

    def down(request):
        if request.url.path == "/v1/rag/chat":
            calls.append(1)
            return httpx.Response(500, json={"detail": "down"})
        return httpx.Response(404)

    cases = [GoldenCase(case_id=f"C{i}", question="q", expected_answer="a") for i in range(8)]

    async def run():
        client = rag_api.RagApiClient("http://rag", transport=httpx.MockTransport(down))
        try:
            return await run_suite(cases, client, None, str(tmp_path), run_id="r",
                                   opts=SuiteOptions(max_consecutive_errors=3))
        finally:
            await client.aclose()

    results = asyncio.run(run())
    assert len(calls) == 3  # stopped after three failing cases: no more load on a failing service
    assert all("run stopped to protect it" in " ".join(r.reasons) for r in results[3:])
