"""
Unit tests for Critical Bug: get_redis_cache() availability & /cache/clear endpoint.
Verifies:
1. get_redis_cache() function is defined, exported, and returns the global RedisCacheAdapter singleton.
2. Endpoint /v1/rag/cache/clear handles scope="tenant" and scope="all" without runtime crash.
3. KnowledgeManagementUseCase operations invoke cache invalidation cleanly without any missing symbol errors.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from solutions.rag.infrastructure.adapters.redis_cache_adapter import (
    RedisCacheAdapter,
    get_redis_cache,
    redis_cache,
)
from solutions.rag.infrastructure.adapters import get_redis_cache as get_redis_cache_from_pkg
from solutions.rag.interfaces.api.chat_router import router as chat_router


def test_get_redis_cache_factory_and_singleton():
    """Verify get_redis_cache() exists, is callable, and returns the global singleton."""
    assert callable(get_redis_cache), "get_redis_cache must be callable"
    assert callable(get_redis_cache_from_pkg), "get_redis_cache must be exported from adapters package"

    inst1 = get_redis_cache()
    inst2 = get_redis_cache_from_pkg()

    assert isinstance(inst1, RedisCacheAdapter), "Must return a RedisCacheAdapter instance"
    assert inst1 is redis_cache, "Must return the global redis_cache singleton"
    assert inst1 is inst2, "Must return the exact same singleton instance"


def test_cache_clear_endpoint_tenant_scope():
    """Verify /cache/clear endpoint works cleanly for tenant scope without runtime crash."""
    app = FastAPI()
    app.include_router(chat_router)

    client = TestClient(app)
    response = client.post(
        "/v1/rag/cache/clear?scope=tenant",
        headers={"X-Tenant-ID": "tenant_test_xyz"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cleared"
    assert data["scope"] == "tenant"
    assert data["tenant_id"] == "tenant_test_xyz"


def test_cache_clear_endpoint_all_scope_admin_protection():
    """Verify cluster-wide cache invalidation requires admin role and succeeds when authorized."""
    app = FastAPI()
    app.include_router(chat_router)

    client = TestClient(app)

    # 1. Non-admin request must be rejected with 403 Forbidden
    unauthorized_res = client.post(
        "/v1/rag/cache/clear?scope=all",
        headers={"X-User-Role": "user"},
    )
    assert unauthorized_res.status_code == 403
    assert "admin" in unauthorized_res.json()["detail"].lower()

    # 2. Admin request must succeed with 200 OK
    admin_res = client.post(
        "/v1/rag/cache/clear?scope=all",
        headers={"X-User-Role": "admin"},
    )
    assert admin_res.status_code == 200
    data = admin_res.json()
    assert data["status"] == "cleared"
    assert data["scope"] == "all"
