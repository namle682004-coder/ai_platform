import importlib.util
import os
import sys

from fastapi.testclient import TestClient

_server_dir = os.path.join(os.path.dirname(__file__), "..", "data-plane", "translation-server")
sys.path.insert(0, _server_dir)
_cfg_spec = importlib.util.spec_from_file_location("config", os.path.join(_server_dir, "config.py"))
_cfg_mod = importlib.util.module_from_spec(_cfg_spec)
sys.modules["config"] = _cfg_mod
_cfg_spec.loader.exec_module(_cfg_mod)

_spec = importlib.util.spec_from_file_location("trans_app_module", os.path.join(_server_dir, "app.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["trans_app_module"] = _mod
_spec.loader.exec_module(_mod)
translation_app = getattr(_mod, "translation_app", _mod.app)

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
