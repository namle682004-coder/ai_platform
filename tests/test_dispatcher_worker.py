"""
Unit tests for Upgraded Dispatcher Worker (DCP-style Architecture):
- TaskResolver (Domain / Alias -> gRPC Target Endpoint)
- RetryPolicy & Exponential Backoff with Jitter
"""

import sys
from pathlib import Path
import pytest

_src = str(Path(__file__).resolve().parent.parent / "apps" / "dispatcher-worker" / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from resolver.task_resolver import TaskResolver
from retry.backoff import (
    RetryPolicy,
    compute_backoff_delay,
    execute_with_retry,
)


def test_task_resolver_defaults():
    resolver = TaskResolver()

    # Translation
    trans_target = resolver.resolve("translation", "translate-vi-standard")
    assert trans_target.domain == "translation"
    assert trans_target.grpc_target == "translation-server:50053"
    assert trans_target.rpc_method == "Translate"

    # Chat / LLM
    chat_target = resolver.resolve("chat", "chat-general-standard")
    assert chat_target.domain == "chat"
    assert chat_target.grpc_target == "vllm-engine:50051"
    assert chat_target.rpc_method == "ChatCompletion"

    # OCR
    ocr_target = resolver.resolve("ocr", "idp-standard")
    assert ocr_target.domain == "ocr"
    assert ocr_target.grpc_target == "ocr-server:50054"


def test_task_resolver_custom_overrides():
    resolver = TaskResolver(endpoint_overrides={"translation": "custom-node:9999"})
    target = resolver.resolve("translation")
    assert target.grpc_target == "custom-node:9999"


def test_compute_backoff_delay_exponential():
    d1 = compute_backoff_delay(1, base_delay=1.0, jitter=False)
    d2 = compute_backoff_delay(2, base_delay=1.0, jitter=False)
    d3 = compute_backoff_delay(3, base_delay=1.0, jitter=False)

    assert d1 == 1.0
    assert d2 == 2.0
    assert d3 == 4.0


def test_compute_backoff_delay_with_jitter():
    delay = compute_backoff_delay(2, base_delay=2.0, max_delay=10.0, jitter=True)
    assert 2.0 <= delay <= 4.0


@pytest.mark.anyio
async def test_execute_with_retry_success():
    call_count = 0

    async def flaky_fn():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ConnectionError("Temporary glitch")
        return "success"

    policy = RetryPolicy(max_retries=3, base_delay=0.01)
    res = await execute_with_retry(flaky_fn, policy=policy)
    assert res == "success"
    assert call_count == 2


@pytest.mark.anyio
async def test_execute_with_retry_exhausted():
    async def always_fails():
        raise TimeoutError("Dead server")

    policy = RetryPolicy(max_retries=2, base_delay=0.01)
    with pytest.raises(TimeoutError):
        await execute_with_retry(always_fails, policy=policy)
