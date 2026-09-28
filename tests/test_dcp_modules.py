from fastapi.testclient import TestClient
from src.main import app
from src.quota.enforcer import QuotaEnforcer

client = TestClient(app)
VALID_AUTH = {"Authorization": "Bearer aip_live_valid_test_key_12345"}


def test_quota_enforcer_bucket_and_concurrency():
    enforcer = QuotaEnforcer(salt="test-salt")
    b1 = enforcer.resolve_bucket("aip_live_key1", "1.2.3.4")
    b2 = enforcer.resolve_bucket("aip_live_key1", "5.6.7.8")
    assert b1 == b2
    assert b1.startswith("key:")

    # Concurrency checks
    assert enforcer.acquire_concurrency(b1, limit=2) is True
    assert enforcer.acquire_concurrency(b1, limit=2) is True
    assert enforcer.acquire_concurrency(b1, limit=2) is False
    enforcer.release_concurrency(b1)
    assert enforcer.acquire_concurrency(b1, limit=2) is True


def test_schemas_registry_list_and_get():
    # 1. List all schemas
    response = client.get("/v1/schemas", headers=VALID_AUTH)
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert "chat-general-standard" in data["schemas"]
    assert "translate-vi-standard" in data["schemas"]

    # 2. Get specific schema
    response_chat = client.get("/v1/schemas/chat-general-standard", headers=VALID_AUTH)
    assert response_chat.status_code == 200
    chat_schema = response_chat.json()
    assert chat_schema["model_id"] == "chat-general-standard"
    assert "messages" in chat_schema["properties"]

    # 3. Get 404 for unknown schema
    response_404 = client.get("/v1/schemas/unknown-model-xyz", headers=VALID_AUTH)
    assert response_404.status_code == 404


def test_resources_gpu_and_capacity_routes():
    # 1. GPU Telemetry route
    response_gpu = client.get("/admin/v1/resources/gpu")
    assert response_gpu.status_code == 200
    gpu_data = response_gpu.json()
    assert "vram_total_mb" in gpu_data
    assert "temperature_celsius" in gpu_data

    # 2. Cluster Capacity route
    response_cap = client.get("/admin/v1/resources/capacity")
    assert response_cap.status_code == 200
    cap_data = response_cap.json()
    assert "active_nodes" in cap_data
    assert cap_data["total_nodes"] >= 1
