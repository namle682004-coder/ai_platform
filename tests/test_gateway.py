from fastapi.testclient import TestClient
from gateway.main import app

client = TestClient(app)
AUTH_HEADERS = {"Authorization": "Bearer aip_live_valid_test_key_12345"}


def test_health_check_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["srs_coverage"] == "100%"
    assert data["control_plane"]["realtime_metrics"] == "active"


def test_admin_realtime_active_calls_metrics():
    response = client.get("/admin/v1/metrics/active-calls")
    assert response.status_code == 200
    data = response.json()
    assert "total_active_inflight" in data
    assert len(data["data"]) >= 3
