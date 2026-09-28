import importlib.util
import io
import os
import sys

from fastapi.testclient import TestClient

_server_dir = os.path.join(os.path.dirname(__file__), "..", "data-plane", "ocr-server")
sys.path.insert(0, _server_dir)
_cfg_spec = importlib.util.spec_from_file_location("config", os.path.join(_server_dir, "config.py"))
_cfg_mod = importlib.util.module_from_spec(_cfg_spec)
sys.modules["config"] = _cfg_mod
_cfg_spec.loader.exec_module(_cfg_mod)

# Load app.py as unique module name to avoid collision
_spec = importlib.util.spec_from_file_location("ocr_app_module", os.path.join(_server_dir, "app.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["ocr_app_module"] = _mod
_spec.loader.exec_module(_mod)
ocr_app = _mod.ocr_app

client = TestClient(ocr_app)


def test_ocr_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "ocr-server"


def test_ocr_process():
    fake_png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
        b"\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    files = {"file": ("id_card.png", io.BytesIO(fake_png_bytes), "image/png")}
    headers = {"Authorization": "Bearer aip_live_testkey123"}

    response = client.post("/v1/ocr/process", files=files, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "detected_text" in data
    assert len(data["boxes"]) >= 1
    assert data["boxes"][0]["confidence"] > 0.8
