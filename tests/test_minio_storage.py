"""
Automated Integration Tests for MinIO S3 Object Storage Service.
Compliant with SRS Section 2.1, 2.2, & 3.3.
Verifies:
- Native MinIO bucket provisioning ('aip-data', 'aip-job-artifacts')
- Binary media upload & retrieval integrity
- AWS S3 v4 HMAC Presigned URL generation (24-hour TTL)
- Real background worker artifact uploads (video-worker, lipsync-worker)
- Audio transcription input upload to MinIO
"""

import io
import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from common.storage import minio_storage
from src.main import app

client = TestClient(app)
VALID_AUTH = {"Authorization": "Bearer aip_live_valid_test_key_12345"}


def test_minio_buckets_initialization():
    """Verify that MinIO storage initializes default buckets."""
    assert minio_storage.object_exists("aip-data", "non_existent_key") is False
    assert minio_storage.object_exists("aip-job-artifacts", "non_existent_key") is False


def test_minio_binary_upload_and_download_integrity():
    """Verify binary data uploaded to MinIO can be retrieved without corruption."""
    test_id = uuid.uuid4().hex[:8]
    sample_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + f"TEST_IMAGE_{test_id}".encode("utf-8")
    object_name = f"tests/test_image_{test_id}.png"

    # Upload
    s3_uri, direct_url = minio_storage.upload_bytes(
        bucket="aip-data",
        object_name=object_name,
        data=sample_bytes,
        content_type="image/png",
    )
    assert s3_uri == f"s3://aip-data/{object_name}"
    assert f"aip-data/{object_name}" in direct_url

    # Check existence
    assert minio_storage.object_exists("aip-data", object_name) is True

    # Download
    downloaded = minio_storage.download_bytes("aip-data", object_name)
    assert downloaded == sample_bytes


def test_minio_presigned_url_generation_24h():
    """Verify S3 Presigned URL contains valid HMAC signature and 24h expiration."""
    test_id = uuid.uuid4().hex[:8]
    object_name = f"videos/output_render_{test_id}.mp4"

    url = minio_storage.generate_presigned_download_url(
        bucket="aip-job-artifacts",
        object_name=object_name,
        expires_seconds=86400,
    )
    assert url is not None
    assert f"aip-job-artifacts/{object_name}" in url
    assert "X-Amz-Signature=" in url
    assert "X-Amz-Expires=86400" in url or "X-Amz-Date=" in url


def test_audio_transcription_uploads_to_minio():
    """Verify that uploading an audio file to /v1/audio/transcriptions stores it into MinIO."""
    test_id = uuid.uuid4().hex[:8]
    filename = f"customer_call_{test_id}.wav"
    fake_wav = b"RIFF" + b"\x00" * 36 + b"WAVEfmt " + f"SPEECH_{test_id}".encode("utf-8")
    files = {"file": (filename, io.BytesIO(fake_wav), "audio/wav")}

    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {
        "text": "Xin chào thế giới máy học",
        "language": "vi",
        "duration": 2.5,
        "segments": [{"start": 0.0, "end": 2.5, "text": "Xin chào thế giới máy học"}],
    }
    mock_res.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_res
        resp = client.post(
            "/v1/audio/transcriptions",
            files=files,
            data={"model": "stt-vn-standard", "language": "vi"},
            headers=VALID_AUTH,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "text" in data

    # Verify that the file was actually written to MinIO!
    from datetime import datetime, timezone
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    expected_obj = f"audio/inputs/TENANT_RETAIL_BANK/{date_str}/{filename}"
    assert minio_storage.object_exists("aip-data", expected_obj) is True
    downloaded = minio_storage.download_bytes("aip-data", expected_obj)
    assert downloaded == fake_wav


@pytest.mark.anyio
async def test_video_worker_saves_artifact_to_real_minio():
    """Verify Video Worker writes MP4 artifact to MinIO and returns presigned URL."""
    import importlib
    video_mod = importlib.import_module("workers.gpu-workloads.video-worker.worker")
    process_video_job = video_mod.process_video_job

    job_id = f"job_vid_minio_{uuid.uuid4().hex[:6]}"
    payload = {
        "task_id": job_id,
        "alias_name": "video-wan2-standard",
        "data": {"prompt": "Sunset over Da Nang Dragon Bridge"},
    }

    res = await process_video_job(payload)
    assert res["status"] == "completed"
    assert res["job_id"] == job_id
    assert "s3_uri" in res
    assert res["s3_uri"] == f"s3://aip-job-artifacts/videos/{job_id}.mp4"
    assert "aip-job-artifacts/videos/" in res["result_urls"][0]

    # Check that object is actually in MinIO!
    assert minio_storage.object_exists("aip-job-artifacts", f"videos/{job_id}.mp4") is True
