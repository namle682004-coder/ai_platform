import os
from unittest.mock import patch

def test_image_worker_process_job():
    os.environ["RABBITMQ_URL"] = "amqp://test:test@localhost:5672/"
    with patch("common.storage.minio_storage.upload_bytes", return_value=("s3://aip-job-artifacts/images/test_1.png", "http://minio/test_1.png")), \
         patch("common.storage.minio_storage.generate_presigned_download_url", return_value="http://minio/presigned_test.png"):
        import sys
        import asyncio
        sys.path.insert(0, "apps/image-worker")
        import worker
        
        result = asyncio.run(worker.process_image_job({
            "job_id": "test_job_image_001",
            "payload": {"prompt": "A modern AI platform architecture diagram"}
        }))
        assert result["status"] == "completed"
        assert result["job_id"] == "test_job_image_001"
        assert "s3_uri" in result
        assert len(result["result_urls"]) == 1
