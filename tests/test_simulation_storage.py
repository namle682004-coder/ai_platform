"""
Unit and Integration Tests for DDD-Structured Simulation Storage Models & Repositories.
"""

from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)
AUTH_HEADERS = {"Authorization": "Bearer aip_live_valid_test_key_12345"}


def test_simulation_run_lifecycle():
    """Verify creating, listing, and retrieving sandbox simulation runs."""
    # 1. Create a simulation run
    payload = {
        "domain": "chat",
        "model_alias": "chat-general-standard",
        "input_payload": {"messages": [{"role": "user", "content": "Test prompt"}]},
        "output_payload": {"content": "Test response"},
        "status": "success",
        "latency_ms": 125.4,
        "token_usage": {"prompt_tokens": 10, "completion_tokens": 15, "total_tokens": 25},
        "tags": ["sandbox", "test"],
    }
    create_res = client.post("/v1/simulations/runs", json=payload, headers=AUTH_HEADERS)
    assert create_res.status_code == 200
    run_data = create_res.json()
    run_id = run_data["run_id"]
    assert run_data["domain"] == "chat"
    assert run_data["model_alias"] == "chat-general-standard"
    assert run_data["status"] == "success"

    # 2. Retrieve the run by ID
    get_res = client.get(f"/v1/simulations/runs/{run_id}", headers=AUTH_HEADERS)
    assert get_res.status_code == 200
    assert get_res.json()["run_id"] == run_id

    # 3. List runs
    list_res = client.get("/v1/simulations/runs?domain=chat", headers=AUTH_HEADERS)
    assert list_res.status_code == 200
    runs = list_res.json()["data"]
    assert any(r["run_id"] == run_id for r in runs)

    # 4. Delete the run
    del_res = client.delete(f"/v1/simulations/runs/{run_id}", headers=AUTH_HEADERS)
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True


def test_chat_session_and_messages_persistence():
    """Verify multi-turn conversation session and message threading."""
    # 1. Create a session
    sess_payload = {
        "title": "Customer Support Simulation",
        "model_alias": "chat-general-standard",
        "temperature": 0.5,
        "max_tokens": 512,
    }
    create_sess = client.post("/v1/simulations/chat/sessions", json=sess_payload, headers=AUTH_HEADERS)
    assert create_sess.status_code == 200
    session_id = create_sess.json()["session_id"]
    assert create_sess.json()["title"] == "Customer Support Simulation"

    # 2. Append User Message
    msg1 = {
        "role": "user",
        "content": "Hello, I have an issue with my subscription.",
        "prompt_tokens": 12,
        "latency_ms": 0.0,
    }
    res_msg1 = client.post(f"/v1/simulations/chat/sessions/{session_id}/messages", json=msg1, headers=AUTH_HEADERS)
    assert res_msg1.status_code == 200
    assert res_msg1.json()["role"] == "user"

    # 3. Append Assistant Response
    msg2 = {
        "role": "assistant",
        "content": "I would be happy to help! Could you provide your subscription ID?",
        "completion_tokens": 15,
        "latency_ms": 110.5,
    }
    res_msg2 = client.post(f"/v1/simulations/chat/sessions/{session_id}/messages", json=msg2, headers=AUTH_HEADERS)
    assert res_msg2.status_code == 200
    assert res_msg2.json()["role"] == "assistant"

    # 4. Retrieve Full Thread History
    thread_res = client.get(f"/v1/simulations/chat/sessions/{session_id}/messages", headers=AUTH_HEADERS)
    assert thread_res.status_code == 200
    messages = thread_res.json()["data"]
    assert len(messages) == 2
    assert messages[0]["content"] == msg1["content"]
    assert messages[1]["content"] == msg2["content"]

    # 5. Clean up session
    del_res = client.delete(f"/v1/simulations/chat/sessions/{session_id}", headers=AUTH_HEADERS)
    assert del_res.status_code == 200


def test_prompt_template_storage():
    """Verify creating and listing reusable prompt templates."""
    tmpl_payload = {
        "title": "Document Summary Prompt",
        "category": "summarization",
        "template_content": "Summarize the following text in 3 bullet points: {text}",
        "variables": ["text"],
        "is_public": True,
    }
    create_res = client.post("/v1/simulations/chat/templates", json=tmpl_payload, headers=AUTH_HEADERS)
    assert create_res.status_code == 200
    tmpl_id = create_res.json()["template_id"]

    list_res = client.get("/v1/simulations/chat/templates", headers=AUTH_HEADERS)
    assert list_res.status_code == 200
    templates = list_res.json()["data"]
    assert any(t["template_id"] == tmpl_id for t in templates)


def test_ocr_record_storage():
    """Verify saving and retrieving OCR extraction records."""
    ocr_payload = {
        "doc_type": "id_card",
        "image_url": "https://storage.company.com/id_cards/cccd_test_01.jpg",
        "extracted_data": {
            "id_number": "001204001234",
            "full_name": "NGUYEN VAN A",
            "dob": "01/01/1990",
            "address": "Ha Noi, Viet Nam",
        },
        "confidence_scores": {"id_number": 0.99, "full_name": 0.98},
        "is_tampered": False,
        "latency_ms": 350.2,
    }
    create_res = client.post("/v1/simulations/ocr/records", json=ocr_payload, headers=AUTH_HEADERS)
    assert create_res.status_code == 200
    record_id = create_res.json()["record_id"]
    assert create_res.json()["extracted_data"]["full_name"] == "NGUYEN VAN A"

    get_res = client.get(f"/v1/simulations/ocr/records/{record_id}", headers=AUTH_HEADERS)
    assert get_res.status_code == 200
    assert get_res.json()["record_id"] == record_id


def test_ekyc_session_storage():
    """Verify saving and listing eKYC biometric verification sessions."""
    ekyc_payload = {
        "id_card_image_url": "https://storage.company.com/ekyc/card.jpg",
        "selfie_image_url": "https://storage.company.com/ekyc/selfie.jpg",
        "facematch_score": 98.6,
        "liveness_score": 99.2,
        "is_live": True,
        "decision": "approved",
        "metadata": {"device": "iPhone 15", "location": "HN-VN"},
        "latency_ms": 420.0,
    }
    create_res = client.post("/v1/simulations/ekyc/sessions", json=ekyc_payload, headers=AUTH_HEADERS)
    assert create_res.status_code == 200
    assert create_res.json()["facematch_score"] == 98.6
    assert create_res.json()["decision"] == "approved"

    list_res = client.get("/v1/simulations/ekyc/sessions", headers=AUTH_HEADERS)
    assert list_res.status_code == 200
    assert len(list_res.json()["data"]) >= 1


def test_audio_records_storage():
    """Verify STT and TTS simulation records persistence."""
    # 1. STT record
    stt_payload = {
        "audio_url": "https://storage.company.com/audio/voice_sample.wav",
        "duration_seconds": 4.5,
        "transcription_text": "Xin chao AI Platform",
        "language_detected": "vi",
        "confidence": 0.99,
        "latency_ms": 280.0,
    }
    create_stt = client.post("/v1/simulations/audio/transcriptions", json=stt_payload, headers=AUTH_HEADERS)
    assert create_stt.status_code == 200
    assert create_stt.json()["transcription_text"] == "Xin chao AI Platform"

    # 2. TTS record
    tts_payload = {
        "input_text": "Chào mừng bạn đến với hệ thống AI",
        "voice_id": "northern-female",
        "output_audio_url": "https://storage.company.com/audio/synthesized.mp3",
        "audio_format": "mp3",
        "duration_seconds": 3.2,
        "latency_ms": 195.0,
    }
    create_tts = client.post("/v1/simulations/audio/syntheses", json=tts_payload, headers=AUTH_HEADERS)
    assert create_tts.status_code == 200
    assert create_tts.json()["output_audio_url"] == tts_payload["output_audio_url"]
