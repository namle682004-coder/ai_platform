from fastapi.testclient import TestClient
from gateway.main import app

client = TestClient(app)


def test_prometheus_metrics_endpoint():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "aip_http_requests_total" in response.text
    assert "aip_http_inflight_requests" in response.text
