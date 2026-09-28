import importlib.util
import io
import os
import sys

from fastapi.testclient import TestClient

_server_dir = os.path.join(os.path.dirname(__file__), "..", "data-plane", "stt-server")
sys.path.insert(0, _server_dir)
_cfg_spec = importlib.util.spec_from_file_location("config", os.path.join(_server_dir, "config.py"))
_cfg_mod = importlib.util.module_from_spec(_cfg_spec)
sys.modules["config"] = _cfg_mod
_cfg_spec.loader.exec_module(_cfg_mod)

# Load app.py as unique module name to avoid collision
_spec = importlib.util.spec_from_file_location("stt_app_module", os.path.join(_server_dir, "app.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["stt_app_module"] = _mod
_spec.loader.exec_module(_mod)
stt_app = _mod.stt_app

client = TestClient(stt_app)


def test_stt_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "stt-server"


def test_stt_transcription():
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000)
    fake_wav_bytes = buf.getvalue()
    files = {"file": ("test_speech.wav", io.BytesIO(fake_wav_bytes), "audio/wav")}
    data = {"model": "stt-vn-standard", "language": "vi"}
    headers = {"Authorization": "Bearer aip_live_testkey123"}

    response = client.post("/v1/audio/transcriptions", files=files, data=data, headers=headers)
    assert response.status_code == 200
    res_data = response.json()
    assert "text" in res_data
    assert res_data["language"] == "vi"
    assert "segments" in res_data
    assert len(res_data["segments"]) > 0
