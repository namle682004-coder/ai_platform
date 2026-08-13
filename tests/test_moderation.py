from fastapi.testclient import TestClient
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "moderation-server"))
from moderation_app import moderation_app

client = TestClient(moderation_app)


def test_moderation_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "moderation-server"


def test_moderation_check():
    payload = {
        "input": "Noi dung kiem tra an toan",
        "model": "moderation-multimodal"
    }
    headers = {"Authorization": "Bearer aip_live_testkey123"}
    response = client.post("/v1/moderations", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 1
    assert data["results"][0]["flagged"] is False
