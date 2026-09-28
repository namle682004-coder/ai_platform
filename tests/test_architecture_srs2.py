"""
Automated Architecture Verification Test Suite for SRS Section 2 (System Architecture).
Compliant with Clean Architecture DDD & SRS Section 2.1, 2.2, 2.3, 2.4.
"""

import os
import yaml
import pytest
from unittest.mock import AsyncMock, patch

from src.quota.enforcer import quota_enforcer


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_srs_2_4_all_six_kubernetes_namespaces_exist():
    """Verify all 6 official namespaces defined in SRS Section 2.4 exist in namespaces.yaml."""
    manifest_path = os.path.join(BASE_DIR, "deploy/k8s/namespaces/namespaces.yaml")
    assert os.path.exists(manifest_path), f"{manifest_path} must exist"

    with open(manifest_path, "r", encoding="utf-8") as f:
        docs = list(yaml.safe_load_all(f))

    ns_names = [d["metadata"]["name"] for d in docs if d and d.get("kind") == "Namespace"]
    
    expected_namespaces = [
        "aip-control",
        "aip-text",
        "aip-multimodal",
        "aip-video",
        "aip-infra",
        "aip-observability",
    ]

    for expected_ns in expected_namespaces:
        assert expected_ns in ns_names, f"Namespace '{expected_ns}' missing from {manifest_path}"


def test_srs_2_3_helm_runtime_groups_and_namespaces_mapping():
    """Verify Helm values and deployments configure all runtime groups and map to proper namespaces."""
    values_path = os.path.join(BASE_DIR, "deploy/helm/aip-runtimes/values.yaml")
    assert os.path.exists(values_path)

    with open(values_path, "r", encoding="utf-8") as f:
        values = yaml.safe_load(f)

    # Runtime groups from SRS Section 2.3
    assert "vllm" in values
    assert "translation" in values
    assert "stt" in values
    assert "tts" in values
    assert "ocr" in values
    assert "image" in values
    assert "video" in values
    assert "lipsync" in values

    # Namespace verification
    assert values["vllm"]["namespace"] == "aip-text"
    assert values["video"]["namespace"] == "aip-video"
    assert values["image"]["namespace"] == "aip-multimodal"
    assert values["lipsync"]["namespace"] == "aip-multimodal"


def test_srs_2_2_media_quota_enforcement():
    """Verify Quota Service enforces binary upload limits (audio, image, video)."""
    # Audio standard limit is 10MB
    allowed, _ = quota_enforcer.check_media_quota(5 * 1024 * 1024, media_type="audio", is_vip=False)
    assert allowed is True

    # 15MB audio exceeds standard 10MB limit
    denied, reason = quota_enforcer.check_media_quota(15 * 1024 * 1024, media_type="audio", is_vip=False)
    assert denied is False
    assert "vượt quá hạn mức Media Quota" in reason

    # 15MB audio is permitted for VIP (limit 50MB)
    vip_allowed, _ = quota_enforcer.check_media_quota(15 * 1024 * 1024, media_type="audio", is_vip=True)
    assert vip_allowed is True


@pytest.mark.anyio
async def test_srs_2_2_job_concurrency_quota_enforcement():
    """Verify Quota Service controls simultaneous active background jobs per tenant."""
    test_tenant = "TENANT_QUOTA_TEST"

    # Reset any existing counter
    with patch("src.db.redis.redis_service.get_client") as mock_redis_client:
        mock_client = AsyncMock()
        mock_redis_client.return_value = mock_client

        # Mock current count = 5 (limit is 5)
        mock_client.get.return_value = "5"
        allowed, count = await quota_enforcer.acquire_job_concurrency(test_tenant, limit=5)
        assert allowed is False
        assert count == 5

        # Mock current count = 2 (under limit)
        mock_client.get.return_value = "2"
        mock_client.incr.return_value = 3
        allowed, count = await quota_enforcer.acquire_job_concurrency(test_tenant, limit=5)
        assert allowed is True
        assert count == 3


@pytest.mark.anyio
async def test_srs_2_3_video_worker_execution():
    """Verify Video Worker pipeline execution and artifact generation."""
    import importlib
    video_mod = importlib.import_module("workers.gpu-workloads.video-worker.worker")
    process_video_job = video_mod.process_video_job

    with patch.object(video_mod, "update_job_status", new_callable=AsyncMock) as mock_update:
        payload = {
            "task_id": "job_vid_unit_test",
            "alias_name": "video-wan2-standard",
            "data": {
                "prompt": "Cinematic drone view of high-tech metropolis at twilight",
            },
        }
        res = await process_video_job(payload)
        assert res["status"] == "completed"
        assert res["job_id"] == "job_vid_unit_test"
        assert "aip-job-artifacts/videos/job_vid_unit_test.mp4" in res["result_urls"][0]
        assert mock_update.call_count >= 2


@pytest.mark.anyio
async def test_srs_2_3_lipsync_worker_execution():
    """Verify LipSync Worker pipeline execution and artifact generation."""
    import importlib
    lipsync_mod = importlib.import_module("workers.gpu-workloads.lipsync-worker.worker")
    process_lipsync_job = lipsync_mod.process_lipsync_job

    with patch.object(lipsync_mod, "update_job_status", new_callable=AsyncMock) as mock_update:
        payload = {
            "task_id": "job_lip_unit_test",
            "alias_name": "lipsync-avatar-standard",
            "data": {
                "face_image": "avatar.png",
                "audio": "speech.mp3",
            },
        }
        res = await process_lipsync_job(payload)
        assert res["status"] == "completed"
        assert res["job_id"] == "job_lip_unit_test"
        assert "aip-job-artifacts/lipsync/job_lip_unit_test.mp4" in res["result_urls"][0]
        assert mock_update.call_count >= 2
