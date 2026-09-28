import importlib.util
import os
import sys

from fastapi.testclient import TestClient

_server_dir = os.path.join(os.path.dirname(__file__), "..", "data-plane", "tts-adapter")
sys.path.insert(0, _server_dir)
_cfg_spec = importlib.util.spec_from_file_location("config", os.path.join(_server_dir, "config.py"))
_cfg_mod = importlib.util.module_from_spec(_cfg_spec)
sys.modules["config"] = _cfg_mod
_cfg_spec.loader.exec_module(_cfg_mod)

# Load app.py as unique module name to avoid collision
_spec = importlib.util.spec_from_file_location("tts_app_module", os.path.join(_server_dir, "app.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["tts_app_module"] = _mod
_spec.loader.exec_module(_mod)
tts_app = _mod.tts_app

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


def test_tts_voices_list():
    headers = {"Authorization": "Bearer aip_live_testkey123"}
    response = client.get("/v1/audio/voices", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "voices" in data
    assert len(data["voices"]) >= 3
