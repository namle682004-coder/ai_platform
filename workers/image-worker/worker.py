import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aip-image-worker")


async def process_image_job(job_payload: dict) -> dict:
    """Mock processing image generation job (FLUX.1 / SDXL diffusion engine)."""
    job_id = job_payload.get("job_id", "unknown")
    prompt = job_payload.get("prompt", "a futuristic cyber city")
    
    logger.info(f"[Image Worker] Processing job {job_id} for prompt: '{prompt}'")
    await asyncio.sleep(1.5)  # Simulate diffusion steps computation
    
    result_url = f"https://minio.internal/aip-job-artifacts/images/{job_id}.png"
    logger.info(f"[Image Worker] Completed job {job_id}. Output: {result_url}")
    return {"status": "completed", "result_urls": [result_url]}


async def main():
    logger.info("[Image Worker] Started FLUX.1 / SDXL Distributed Worker Listener...")
    # In production, connects to RabbitMQ queue 'q.aip.jobs.image_generation' via aio-pika
    while True:
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
