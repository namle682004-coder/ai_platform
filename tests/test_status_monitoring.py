from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)


def test_platform_status_public_endpoint():
    """Verify /status is publicly accessible and conforms to platform monitoring schema."""
    response = client.get("/status")
    assert response.status_code == 200
    data = response.json()

    assert "platform_status" in data
    assert data["platform_status"] in ("healthy", "degraded", "unhealthy")
    assert isinstance(data["active_runs"], int)
    assert isinstance(data["queued_tasks"], int)

    # Infrastructure checks
    assert "infrastructure" in data
    infra = data["infrastructure"]
    assert "mongodb" in infra
    assert "redis" in infra
    assert "rabbitmq" in infra
    assert "minio" in infra
    assert "status" in infra["mongodb"]

    # Services / workers checks
    assert "services" in data
    services = data["services"]
    assert "control_plane" in services
    assert "vllm_engine" in services
    assert "dispatcher_worker" in services
    assert "callback_worker" in services
    assert "translation" in services
    assert "stt" in services
    assert "ocr" in services
    assert "moderation" in services
    assert "tts" in services

    # Verify collector/service sub-dict structure matches user schema
    assert "status" in services["vllm_engine"]
    assert "active_runs" in services["vllm_engine"]

    # Models summary
    assert "models_summary" in data
    assert "total_hosted_models" in data["models_summary"]
    assert "checked_at" in data


def test_platform_status_v1_endpoint():
    """Verify /v1/status returns the same monitoring structure."""
    response = client.get("/v1/status")
    assert response.status_code == 200
    data = response.json()
    assert data["platform_status"] in ("healthy", "degraded", "unhealthy")
    assert "services" in data
    assert "infrastructure" in data


def test_models_status_endpoints():
    """Verify /status/models and /v1/status/models provide deep-dive vLLM telemetry."""
    for path in ["/status/models", "/v1/status/models", "/v1/models/status"]:
        response = client.get(path)
        assert response.status_code == 200
        data = response.json()

        assert "engine_status" in data
        assert data["engine_status"] in ("healthy", "offline")
        assert "runtime" in data
        assert "device" in data
        assert "models" in data
        assert isinstance(data["models"], dict)

        # Check hosted models
        assert "chat-general-standard" in data["models"]
        standard_chat = data["models"]["chat-general-standard"]
        assert "status" in standard_chat
        assert "physical_model" in standard_chat
        assert "runtime" in standard_chat
        assert standard_chat["stream_capable"] is True
        assert "active_runs" in standard_chat
        assert "checked_at" in data
