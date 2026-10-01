import pytest
from fastapi.testclient import TestClient
from src.main import app

AUTH_HEADERS = {"Authorization": "Bearer aip_live_valid_test_key_12345"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_check_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "aip-gateway"
    assert "timestamp" in data


def test_admin_list_exported_endpoints(client):
    response = client.get("/admin/v1/endpoints")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) >= 7


def test_admin_update_endpoint_export_status(client):
    response = client.put("/admin/v1/endpoints/chat_completions", json={"status": "disabled"})
    assert response.status_code == 200
    assert response.json()["endpoint"]["status"] == "disabled"
    # Teardown: re-enable chat_completions
    restore_res = client.put("/admin/v1/endpoints/chat_completions", json={"status": "enabled"})
    assert restore_res.status_code == 200


def test_admin_quota_management_api(client):
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
    listed_key = next(
        (key for key in list_res.json()["data"] if key["key_id"] == key_id),
        None,
    )
    assert listed_key is not None
    assert listed_key["rpm_limit"] == 180


def test_staff_portal_endpoints(client):
    # 1. Staff APIs Catalog HTML
    res = client.get("/staff/apis")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "APIs Catalog" in res.text

    # 2. Staff APIs JSON negotiation
    res_json = client.get("/staff/apis", headers={"accept": "application/json"})
    assert res_json.status_code == 200
    assert "application/json" in res_json.headers["content-type"]
    assert "apis" in res_json.json()

    # 3. Staff Dashboard & Other Views
    res_dash = client.get("/staff/dashboard")
    assert res_dash.status_code == 200
    assert "text/html" in res_dash.headers["content-type"]

    # 4. Static assets
    res_asset = client.get("/assets/css/admin.css")
    assert res_asset.status_code == 200
    assert "text/css" in res_asset.headers["content-type"]
