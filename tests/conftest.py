import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Enforce isolated local test defaults unless explicitly running in live integration mode
if os.environ.get("AIP_LIVE_TEST") != "1":
    os.environ["TEST_MODE"] = "true"
    os.environ["VLLM_TEST_MODE"] = "true"
    os.environ["MASTER_PEPPER"] = "test-master-pepper-for-testing-purposes-min-32-chars"
    os.environ["JWT_SECRET"] = "test-jwt-secret-for-testing-purposes-min-32-chars"
    os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017/test_ai_platform")
    os.environ.setdefault("MINIO_ROOT_PASSWORD", "minioadmin123")
    os.environ.setdefault("RABBITMQ_URL", "amqp://aip:lenam682004@localhost:5672/")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("QDRANT_URL", "http://127.0.0.1:6333")


import pytest


@pytest.fixture
def requires_embedding_runtime():
    """
    Skip tests that exercise the real retrieval stack when the `embed-standard` runtime
    (platform/runtimes/embedding-server, BAAI/bge-m3) is not reachable. The RAG adapter no
    longer fabricates vectors, so these tests can only pass against a live runtime.
    """
    import asyncio

    import httpx

    from solutions.rag.config import rag_settings
    from solutions.rag.infrastructure.adapters.model_registry import ModelEndpointResolver

    async def _probe() -> str:
        endpoint = await ModelEndpointResolver().resolve(
            rag_settings.embedding_model_alias, override_url=rag_settings.embedding_base_url
        )
        health_url = endpoint.base_url.rsplit("/v1", 1)[0] + "/health/ready"
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get(health_url)
        if res.status_code != 200:
            raise RuntimeError(f"{health_url} -> HTTP {res.status_code}")
        return health_url

    try:
        asyncio.run(_probe())
    except Exception as exc:
        pytest.skip(f"embed-standard runtime unavailable ({exc}); start platform/runtimes/embedding-server")
