from fastapi.testclient import TestClient
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "translation-server"))
from translation_app import translation_app

client = TestClient(translation_app)


def test_translation_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "translation-server"


def test_translation_prediction():
    payload = {
        "text": "Xin chào thế giới",
        "source_lang": "vie_Latn",
        "target_lang": "eng_Latn"
    }
    headers = {"Authorization": "Bearer aip_live_testkey123"}
    response = client.post("/v1/predictions", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "translated_text" in data
    assert data["source_lang"] == "vie_Latn"
