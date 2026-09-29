"""
Test SRS Compliance Upgrades:
- Section 6.2: Deprecated Aliases return header 'X-AIP-Alias-Deprecated: true'
- Section 7.4: RabbitMQ Topology defines aip.jobs, aip.jobs.retry, aip.jobs.dlx & canonical queues
"""

from fastapi.testclient import TestClient
from src.main import app
from src.items.alias_router import alias_router
from src.publisher.topology import (
    EXCHANGE_JOBS,
    EXCHANGE_JOBS_RETRY,
    EXCHANGE_JOBS_DLX,
    SRS_JOB_TYPES,
)

client = TestClient(app)
VALID_AUTH = {"Authorization": "Bearer aip_live_valid_test_key_12345"}


def test_srs_6_2_deprecated_alias_header():
    """Verify that calling an alias marked as deprecated injects X-AIP-Alias-Deprecated: true."""
    # Temporarily mark 'translate-vi-standard' as deprecated
    original_status = alias_router._registry["translate-vi-standard"]["status"]
    try:
        alias_router._registry["translate-vi-standard"]["status"] = "deprecated"
        
        # Test GET /v1/models/translate-vi-standard
        response = client.get("/v1/models/translate-vi-standard", headers=VALID_AUTH)
        assert response.status_code == 200
        assert response.headers.get("X-AIP-Alias-Deprecated") == "true"
        
        # Test Chat with a deprecated model (e.g. chat-general-standard)
        orig_chat_status = alias_router._registry["chat-general-standard"]["status"]
        alias_router._registry["chat-general-standard"]["status"] = "deprecated"
        try:
            res_chat = client.post(
                "/v1/chat/completions",
                json={
                    "model": "chat-general-standard",
                    "messages": [{"role": "user", "content": "hello"}]
                },
                headers=VALID_AUTH
            )
            # Even if backend mock/runtime fails or returns, header X-AIP-Alias-Deprecated is present
            assert res_chat.headers.get("X-AIP-Alias-Deprecated") == "true"
        finally:
            alias_router._registry["chat-general-standard"]["status"] = orig_chat_status

    finally:
        alias_router._registry["translate-vi-standard"]["status"] = original_status


def test_srs_7_4_rabbitmq_topology_constants():
    """Verify RabbitMQ exchange and job queue topology conforms to SRS Section 7.4."""
    assert EXCHANGE_JOBS == "aip.jobs"
    assert EXCHANGE_JOBS_RETRY == "aip.jobs.retry"
    assert EXCHANGE_JOBS_DLX == "aip.jobs.dlx"
    
    expected_jobs = {
        "video_generation",
        "lip_sync",
        "image_generation",
        "audio_transcription",
        "tts_synthesis",
        "idp_batch",
        "embedding_batch",
        "translation_batch",
    }
    assert expected_jobs.issubset(set(SRS_JOB_TYPES))
