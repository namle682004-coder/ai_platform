"""
Automated tests for Heavy Workload Auto-Offloading to RabbitMQ.
"""

from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)
VALID_AUTH = {"Authorization": "Bearer aip_live_valid_test_key_12345"}


def test_translation_short_stays_sync():
    """Short text <= 500 chars should be translated synchronously (HTTP 200)."""
    short_text = "Xin chào, đây là một câu ngắn để kiểm tra dịch tức thì."
    res = client.post(
        "/v1/nlp/translation",
        json={"text": short_text, "source_lang": "vi", "target_lang": "en"},
        headers=VALID_AUTH,
    )
    assert res.status_code == 200
    data = res.json()
    assert data.get("status") == "success"
    assert "translated_text" in data
    assert data.get("mode") != "async_job"


def test_translation_heavy_auto_offloads_to_rabbitmq():
    """Text > 500 chars should automatically offload to RabbitMQ with HTTP 202."""
    long_text = (
        "Trí tuệ nhân tạo (AI) đang định hình lại toàn bộ nền kinh tế số toàn cầu, "
        "từ tự động hóa quy trình nghiệp vụ, tối ưu hóa chuỗi cung ứng cho đến phân tích dữ liệu quy mô lớn. "
        "Việc tự xây dựng và vận hành nền tảng AI nội bộ (Self-hosted AI Platform) giúp các doanh nghiệp bảo vệ "
        "toàn vẹn chủ quyền dữ liệu, giảm thiểu rủi ro rò rỉ bí mật kinh doanh và tối ưu hóa chi phí vận hành hạ tầng. "
        "Với sự phát triển vượt bậc của các mô hình mã nguồn mở thế hệ mới, doanh nghiệp có thể triển khai hệ thống dịch thuật."
    )
    assert len(long_text) > 500

    res = client.post(
        "/v1/nlp/translation",
        json={"text": long_text, "source_lang": "vi", "target_lang": "en"},
        headers={**VALID_AUTH, "X-Priority": "high"},
    )
    assert res.status_code == 202
    data = res.json()
    assert data["status"] == "queued"
    assert data["mode"] == "async_job"
    assert data["job_type"] == "tasks.translation"
    assert data["alias_name"] == "translate-vi-standard"
    assert data["priority"] == "high"
    assert data["priority_level"] == 9
    assert "job_id" in data
    assert "check_status_url" in data
    assert "Văn bản dài" in data["reason"]


def test_chat_heavy_context_auto_offloads_to_rabbitmq():
    """Chat with context > 3000 chars should automatically offload to RabbitMQ with HTTP 202."""
    massive_context = "Đây là một tài liệu pháp lý cực kỳ chi tiết cần AI tóm tắt và phân tích chuyên sâu. " * 50
    assert len(massive_context) > 3000

    res = client.post(
        "/v1/chat/completions",
        json={
            "model": "chat-general-standard",
            "messages": [
                {"role": "system", "content": "You are a legal assistant."},
                {"role": "user", "content": massive_context},
            ],
            "stream": False,
        },
        headers={**VALID_AUTH, "X-Priority": "high"},
    )
    assert res.status_code == 202
    data = res.json()
    assert data["status"] == "queued"
    assert data["mode"] == "async_job"
    assert data["job_type"] == "tasks.chat"
    assert data["alias_name"] == "chat-general-standard"
    assert data["priority"] == "high"
    assert "job_id" in data


def test_tts_heavy_auto_offloads_to_rabbitmq():
    """TTS with input text > 300 chars should automatically offload with HTTP 202."""
    long_speech = (
        "Chào mừng quý khách đến với dịch vụ tổng đài tự động thông minh của hệ thống AIP Platform doanh nghiệp. "
        "Để gặp nhân viên tư vấn về các giải pháp trí tuệ nhân tạo và chuyển đổi số, vui lòng nhấn phím một. "
        "Để tra cứu thông tin hóa đơn điện tử và các giao dịch gần đây, vui lòng nhấn phím hai hoặc giữ máy để được trợ giúp."
    )
    assert len(long_speech) > 300

    res = client.post(
        "/v1/audio/speech",
        json={
            "model": "tts-vi-standard",
            "input": long_speech,
            "voice": "northern_female",
        },
        headers=VALID_AUTH,
    )
    assert res.status_code == 202
    data = res.json()
    assert data["status"] == "queued"
    assert data["mode"] == "async_job"
    assert data["job_type"] == "tasks.tts"
    assert "job_id" in data


def test_image_heavy_batch_auto_offloads_to_rabbitmq():
    """Image generation with n > 1 should automatically offload with HTTP 202."""
    res = client.post(
        "/v1/images/generations",
        json={
            "model": "image-gen-standard",
            "prompt": "a futuristic cyber city at sunset",
            "n": 4,
        },
        headers={**VALID_AUTH, "X-Priority": "batch"},
    )
    assert res.status_code == 202
    data = res.json()
    assert data["status"] == "queued"
    assert data["mode"] == "async_job"
    assert data["job_type"] == "tasks.image"
    assert data["priority"] == "batch"
    assert "job_id" in data


def test_explicit_async_header_offload():
    """Any request with header "Prefer: respond-async" should offload even if short."""
    short_text = "Câu ngắn."
    res = client.post(
        "/v1/nlp/translation",
        json={"text": short_text, "source_lang": "vi", "target_lang": "en"},
        headers={**VALID_AUTH, "Prefer": "respond-async"},
    )
    assert res.status_code == 202
    data = res.json()
    assert data["status"] == "queued"
    assert data["mode"] == "async_job"
