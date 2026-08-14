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
