from fastapi.testclient import TestClient
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "tts-adapter"))
from app import tts_app

client = TestClient(tts_app)


def test_tts_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "tts-adapter"


def test_tts_speech_generation():
    payload = {
        "model": "tts-vi-standard",
        "input": "Xin chào thế giới",
        "voice": "northern_female"
    }
    headers = {"Authorization": "Bearer aip_live_testkey123"}
    response = client.post("/v1/audio/speech", json=payload, headers=headers)
    assert response.status_code == 200
    assert "audio/mpeg" in response.headers["content-type"]
