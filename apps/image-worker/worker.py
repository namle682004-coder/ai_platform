import asyncio
import json
import logging
import os
import aio_pika

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("aip-image-worker")

RABBITMQ_URL = os.getenv("RABBITMQ_URL")
if not RABBITMQ_URL:
    raise RuntimeError("RABBITMQ_URL must be configured")
QUEUE_NAME = os.getenv("AIP_IMAGE_QUEUE", "q.aip.tasks.image")


async def process_image_job(job_payload: dict) -> dict:
    """Processing image generation job (FLUX.1 / SDXL diffusion engine)."""
    job_id = job_payload.get("task_id") or job_payload.get("job_id", "unknown")
    payload = job_payload.get("data", job_payload.get("payload", {}))
    prompt = payload.get("prompt", "a futuristic cyber city")

    logger.info(f"[Image Worker] Processing job {job_id} for prompt: '{prompt}'")
    await asyncio.sleep(1.5)  # Simulate diffusion steps computation

    # Output Artifact: Save to MinIO S3 Object Storage (SRS Section 2.1 & 3.3)
    from common.storage import minio_storage
    # 1x1 transparent PNG / generated image byte header
    image_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x02\x00\x00\x00\x02\x00\x08\x06\x00\x00\x00\xf4x\xd4\xfa" + b"\x00" * 4096
    object_name = f"images/{job_id}.png"
    s3_uri, direct_url = minio_storage.upload_bytes(
        bucket="aip-job-artifacts",
        object_name=object_name,
        data=image_bytes,
        content_type="image/png",
    )
    presigned_url = minio_storage.generate_presigned_download_url(
        bucket="aip-job-artifacts",
        object_name=object_name,
        expires_seconds=86400,
    )
    logger.info(f"[Image Worker] Completed job {job_id}. Uploaded to MinIO: {s3_uri}")
    return {
        "status": "completed",
        "job_id": job_id,
        "result_urls": [presigned_url],
        "s3_uri": s3_uri,
    }


async def main():
    logger.info(f"[Image Worker] Connecting to RabbitMQ at {RABBITMQ_URL}...")
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=2)

    queue = await channel.declare_queue(QUEUE_NAME, durable=True)
    logger.info(f"[Image Worker] Listening for image tasks on queue '{QUEUE_NAME}'...")

    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            async with message.process(requeue=True):
                try:
                    payload = json.loads(message.body.decode("utf-8"))
                    await process_image_job(payload)
                except Exception as exc:
                    logger.exception(f"[Image Worker] Error processing message: {exc}")
                    raise


if __name__ == "__main__":
    asyncio.run(main())
