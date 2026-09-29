import importlib.util
import os
import sys

from fastapi.testclient import TestClient

_server_dir = os.path.join(os.path.dirname(__file__), "..", "apps", "data-plane", "moderation-server")
sys.path.insert(0, _server_dir)
_cfg_spec = importlib.util.spec_from_file_location("config", os.path.join(_server_dir, "config.py"))
_cfg_mod = importlib.util.module_from_spec(_cfg_spec)
sys.modules["config"] = _cfg_mod
_cfg_spec.loader.exec_module(_cfg_mod)

_spec = importlib.util.spec_from_file_location("mod_app_module", os.path.join(_server_dir, "app.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["mod_app_module"] = _mod
_spec.loader.exec_module(_mod)
moderation_app = getattr(_mod, "moderation_app", _mod.app)

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


def test_moderation_pii_detection():
    payload = {
        "input": "So dien thoai cua toi la 0901234567 va email test@example.com",
        "model": "moderation-multimodal"
    }
    headers = {"Authorization": "Bearer aip_live_testkey123"}
    response = client.post("/v1/moderations", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["results"][0]["flagged"] is True
    assert data["results"][0]["categories"]["pii_leakage"] is True
