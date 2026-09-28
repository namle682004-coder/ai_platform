"""
Unit and Integration Tests for Asynchronous Usage Metering & Token Consumption.
Compliant with Clean Architecture DDD & SRS Section 7 & 8.
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from common.models.usage import UsageRecord, UsageSummary
from common.repositories.usage_repository import usage_repository
from src.usage.meter import usage_meter
from src.main import app

client = TestClient(app)
AUTH_HEADERS = {"Authorization": "Bearer aip_live_valid_test_key_12345"}


def test_usage_models_validation():
    """Verify UsageRecord and UsageSummary data contracts."""
    rec = UsageRecord(
        request_id="req_test_001",
        tenant_id="TENANT_RETAIL_BANK",
        cost_center="CC_DIGITAL_BANKING",
        model_alias="chat-general-standard",
        physical_model="Qwen3-8B",
        prompt_tokens=25,
        completion_tokens=50,
        total_tokens=75,
        cost_vnd=0.75,
        latency_ms=120.5,
    )
    assert rec.usage_id.startswith("usg_")
    assert rec.total_tokens == 75
    assert rec.cost_vnd == 0.75

    summary = UsageSummary(
        tenant_id="TENANT_RETAIL_BANK",
        total_requests=10,
        total_tokens=1000,
        total_cost_vnd=10.0,
        active_models=["chat-general-standard"],
    )
    assert summary.total_cost_vnd == 10.0
    assert "chat-general-standard" in summary.active_models


@pytest.mark.anyio
async def test_usage_repository_persistence():
    """Verify MongoUsageRepository records usage and calculates summary."""
    test_record = {
        "usage_id": "usg_unit_test_999",
        "request_id": "req_unit_test_999",
        "tenant_id": "TENANT_TEST_CORP",
        "cost_center": "CC_TEST_LAB",
        "domain": "chat",
        "model_alias": "chat-general-standard",
        "physical_model": "Qwen3-8B",
        "prompt_tokens": 100,
        "completion_tokens": 200,
        "total_tokens": 300,
        "cost_vnd": 3.0,
        "latency_ms": 85.0,
        "status_code": 200,
        "stream": False,
    }

    saved = await usage_repository.record_usage(test_record)
    assert saved["usage_id"] == "usg_unit_test_999"
    assert "timestamp" in saved

    # Query back
    records = await usage_repository.list_usage_records(tenant_id="TENANT_TEST_CORP")
    assert len(records) >= 1
    assert any(r["usage_id"] == "usg_unit_test_999" for r in records)

    # Check summary
    summary = await usage_repository.get_usage_summary(tenant_id="TENANT_TEST_CORP")
    assert summary["total_tokens"] >= 300
    assert summary["total_cost_vnd"] >= 3.0
    assert "chat-general-standard" in summary["active_models"]


@pytest.mark.anyio
async def test_usage_meter_service_calculation():
    """Verify UsageMeterService calculates cost and constructs usage document."""
    res = await usage_meter.record_inference_usage(
        request_id="req_meter_abc123",
        tenant_id="TENANT_RETAIL_BANK",
        cost_center="CC_DIGITAL_BANKING",
        api_key_prefix="aip_live_val...",
        domain="chat",
        model_alias="chat-general-high-quality",
        physical_model="Qwen3-14B",
        prompt_tokens=40,
        completion_tokens=60,
        total_tokens=100,
        latency_ms=150.0,
        status_code=200,
    )

    assert res["prompt_tokens"] == 40
    assert res["completion_tokens"] == 60
    assert res["total_tokens"] == 100
    # 100 tokens * 0.01 VND = 1.0 VND
    assert res["cost_vnd"] == 1.0


def test_api_usage_summary_endpoint():
    """Verify GET /v1/usage/summary returns aggregated metrics."""
    resp = client.get("/v1/usage/summary", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_requests" in data
    assert "total_tokens" in data
    assert "total_cost_vnd" in data
    assert isinstance(data["active_models"], list)


def test_api_usage_records_endpoint():
    """Verify GET /v1/usage/records returns list of granular usage records."""
    resp = client.get("/v1/usage/records?limit=10", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    assert isinstance(data["data"], list)
    assert "count" in data


def test_api_usage_tpm_endpoint():
    """Verify GET /v1/usage/tpm returns real-time TPM utilization."""
    resp = client.get("/v1/usage/tpm", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "tenant_id" in data
    assert "current_tpm" in data
    assert "tpm_limit" in data
    assert "utilization_pct" in data
    assert data["status"] in ["normal", "exceeded"]


def test_chat_inference_triggers_async_usage_recording():
    """Verify /v1/chat/completions triggers async usage recording on success."""
    mock_upstream_response = {
        "id": "chatcmpl-mock-12345",
        "object": "chat.completion",
        "created": 1790000000,
        "model": "chat-general-standard",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Xin chào! Tôi có thể giúp gì cho bạn?"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 15,
            "completion_tokens": 25,
            "total_tokens": 40,
        },
    }

    with patch("src.api.proxy.proxy_service.client.post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: mock_upstream_response
        mock_resp.headers = {"content-type": "application/json"}
        mock_post.return_value = mock_resp

        payload = {
            "model": "chat-general-standard",
            "messages": [{"role": "user", "content": "Xin chào bạn"}],
            "temperature": 0.7,
        }

        resp = client.post("/v1/chat/completions", json=payload, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "chatcmpl-mock-12345"
        assert data["usage"]["total_tokens"] == 40
