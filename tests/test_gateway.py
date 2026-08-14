from fastapi.testclient import TestClient
from gateway.main import app

client = TestClient(app)
AUTH_HEADERS = {"Authorization": "Bearer aip_live_valid_test_key_12345"}


def test_health_check_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "100%" in data["srs_coverage"]
    assert data["control_plane"]["prometheus_metrics"] == "active (/metrics)"
    assert data["control_plane"]["admin_cidr_allowlist"] == "active"


def test_admin_list_exported_endpoints():
    response = client.get("/admin/v1/endpoints")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) >= 8


def test_admin_update_endpoint_export_status():
    response = client.put("/admin/v1/endpoints/chat_completions", json={"status": "disabled"})
    assert response.status_code == 200
    assert response.json()["endpoint"]["status"] == "disabled"


def test_admin_quota_management_api():
    # 1. Create API key with initial quota
    create_res = client.post("/admin/v1/keys", json={
        "tenant_id": "TENANT_MARKETING",
        "rpm_limit": 60,
        "tpm_limit": 100000,
        "concurrency_limit": 5
    })
    assert create_res.status_code == 200
    key_id = create_res.json()["key_id"]

    # 2. Adjust quota dynamically
    update_res = client.put(f"/admin/v1/keys/{key_id}/quota", json={
        "rpm_limit": 180,
        "tpm_limit": 300000,
        "concurrency_limit": 15
    })
    assert update_res.status_code == 200
    assert update_res.json()["updated_quota"]["rpm_limit"] == 180

    # 3. List keys
    list_res = client.get("/admin/v1/keys")
    assert list_res.status_code == 200
    assert len(list_res.json()["data"]) >= 2
