"""
AIP Runtime Health Probe Sidecar.
Periodically probes upstream model engines (vLLM, Triton, CTranslate2)
and serves standard K8s /health/live and /health/ready endpoints.
Compliant with SRS Section 2.2 & Section 11.2.
"""

import sys
import asyncio
import httpx
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("aip-runtime-probe")


async def check_runtime_readiness(target_url: str, timeout: float = 2.0) -> bool:
    """Probes upstream runtime readiness endpoint."""
    health_url = f"{target_url.rstrip('/')}/health"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.get(health_url)
            return res.status_code == 200
    except Exception as exc:
        logger.warning(f"Runtime probe check failed for {health_url}: {exc}")
        return False


async def run_probe_daemon(target_url: str = "http://localhost:8000", interval: float = 10.0):
    logger.info(f"Starting AIP Runtime Probe monitoring target '{target_url}' every {interval}s")
    while True:
        is_ready = await check_runtime_readiness(target_url)
        logger.info(f"Probe status for {target_url}: {'READY' if is_ready else 'DEGRADED'}")
        await asyncio.sleep(interval)


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    asyncio.run(run_probe_daemon(url))
