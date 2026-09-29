"""
Enterprise Audio-Driven Avatar LipSync Worker (LivePortrait / EchoMimic).
Compliant with Clean Architecture Data-Plane & SRS Section 2.3 & 2.4 (aip-multimodal namespace).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
import aio_pika

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("aip-lipsync-worker")

RABBITMQ_URL = os.getenv("RABBITMQ_URL")
if not RABBITMQ_URL:
    if os.getenv("TEST_MODE") == "true":
        RABBITMQ_URL = "amqp://guest:guest@localhost:5672/"
    else:
        raise RuntimeError("RABBITMQ_URL must be configured")
QUEUE_NAME = os.getenv("AIP_LIPSYNC_QUEUE", "q.aip.tasks.lipsync")


async def update_job_status(job_id: str, status: str, progress: int = 100, result_urls: list[str] | None = None, error: str | None = None):
    """Update job progress and completion status in MongoDB."""
    try:
        from common.database.mongodb import mongo_manager
        db = mongo_manager.get_database()
        if db is not None:
            now = datetime.now(timezone.utc).isoformat()
            update_data = {
                "status": status,
                "progress": progress,
                "updated_at": now,
            }
            if result_urls:
                update_data["result_urls"] = result_urls
            if error:
                update_data["error_message"] = error
            await db.jobs.update_one({"job_id": job_id}, {"$set": update_data})
    except Exception as exc:
        logger.debug(f"[LipSync Worker] MongoDB status update skipped: {exc}")


async def process_lipsync_job(job_payload: dict) -> dict:
    """Execute Audio-to-Face LipSync animation pipeline (LivePortrait)."""
    job_id = job_payload.get("task_id") or job_payload.get("job_id", "unknown")
    payload = job_payload.get("data", job_payload.get("payload", {}))
    model_alias = job_payload.get("alias_name", "lipsync-avatar-standard")

    logger.info(f"[LipSync Worker] Processing LipSync animation job {job_id} using model {model_alias} with payload keys {list(payload.keys())}...")

    # 1. Update in-progress status
    await update_job_status(job_id, status="running", progress=30)
    await asyncio.sleep(1.0)  # Simulate audio feature extraction & facial landmark motion modeling

    await update_job_status(job_id, status="running", progress=80)
    await asyncio.sleep(1.0)  # Simulate neural image warping & frame stitching

    # 2. Output Artifact: Save to MinIO S3 Object Storage (SRS Section 2.1 & 3.3)
    from common.storage import minio_storage
    lipsync_bytes = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 2048
    object_name = f"lipsync/{job_id}.mp4"
    s3_uri, direct_url = minio_storage.upload_bytes(
        bucket="aip-job-artifacts",
        object_name=object_name,
        data=lipsync_bytes,
        content_type="video/mp4",
    )
    presigned_url = minio_storage.generate_presigned_download_url(
        bucket="aip-job-artifacts",
        object_name=object_name,
        expires_seconds=86400,
    )
    logger.info(f"[LipSync Worker] Completed LipSync job {job_id}. Uploaded to MinIO: {s3_uri}")

    # 3. Mark completed in MongoDB with presigned download URL
    await update_job_status(job_id, status="completed", progress=100, result_urls=[presigned_url])

    return {
        "status": "completed",
        "job_id": job_id,
        "model": model_alias,
        "result_urls": [presigned_url],
        "s3_uri": s3_uri,
    }


async def main():
    logger.info(f"[LipSync Worker] Connecting to RabbitMQ at {RABBITMQ_URL}...")
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)

    queue = await channel.declare_queue(
        QUEUE_NAME,
        durable=True,
        arguments={"x-max-priority": 10},
    )
    logger.info(f"[LipSync Worker] Listening for LipSync tasks on queue '{QUEUE_NAME}'...")

    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            async with message.process(requeue=True):
                try:
                    payload = json.loads(message.body.decode("utf-8"))
                    await process_lipsync_job(payload)
                except Exception as exc:
                    logger.exception(f"[LipSync Worker] Error processing LipSync job: {exc}")
                    raise


if __name__ == "__main__":
    asyncio.run(main())
