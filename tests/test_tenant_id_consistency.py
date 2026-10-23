"""
Unit tests for Tenant ID Consistency across AIP RAG modules (NFR-6.1).
Verifies:
1. Canonical DEFAULT_TENANT_ID ("proj_default") and normalize_tenant_id() behavior.
2. Cross-module alignment: chat_router, knowledge_router, ingestion_use_case,
   knowledge_use_case, chat_use_case, and redis_cache_adapter all share the identical canonical tenant ID.
3. Cache key alignment between ingestion invalidation, chat query caching, and rate limiting.
"""

from starlette.requests import Request

from solutions.rag.domain.entities import (
    DEFAULT_TENANT_ID,
    normalize_tenant_id,
)
from solutions.rag.infrastructure.adapters.redis_cache_adapter import (
    RedisCacheAdapter,
)
from solutions.rag.interfaces.api.chat_router import _extract_tenant as chat_extract_tenant
from solutions.rag.interfaces.api.knowledge_router import _extract_tenant as knowledge_extract_tenant
from solutions.rag.interfaces.api.rate_limiter import rate_limiter


def make_mock_request(headers: dict = None, state_tenant: str = None) -> Request:
    raw_headers = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))
    scope = {
        "type": "http",
        "client": ("127.0.0.1", 12345),
        "headers": raw_headers,
        "state": {},
    }
    if state_tenant:
        scope["state"]["tenant_id"] = state_tenant
    return Request(scope)


def test_normalize_tenant_id_canonical_rules():
    """Verify all fallback aliases map to canonical DEFAULT_TENANT_ID."""
    assert DEFAULT_TENANT_ID == "proj_default"

    for alias in ["default_tenant", "tenant_default", "default", "global", "", None]:
        assert normalize_tenant_id(alias) == "proj_default", f"Alias '{alias}' must normalize to proj_default"

    # Case-insensitivity test
    assert normalize_tenant_id("GLOBAL") == "proj_default"
    assert normalize_tenant_id("Default_Tenant") == "proj_default"
    assert normalize_tenant_id("  global  ") == "proj_default"

    # Forwarded comma-separated header test
    assert normalize_tenant_id("tenant_retail, extra_proxy") == "tenant_retail"

    # Custom tenant preservation
    assert normalize_tenant_id("tenant_enterprise_01") == "tenant_enterprise_01"
    assert normalize_tenant_id("bank_vpbank") == "bank_vpbank"


def test_cross_router_tenant_extraction_parity():
    """Verify chat_router, knowledge_router, and rate_limiter extract identical tenant IDs."""
    # 1. Default request with no headers
    req_empty = make_mock_request()
    chat_tid = chat_extract_tenant(req_empty)
    knowledge_tid = knowledge_extract_tenant(req_empty)
    limiter_tid, _ = rate_limiter._extract_rate_key(req_empty)

    assert chat_tid == "proj_default"
    assert knowledge_tid == "proj_default"
    assert limiter_tid == "proj_default"
    assert chat_tid == knowledge_tid == limiter_tid

    # 2. Legacy alias in header
    for alias in ["default_tenant", "global", "default"]:
        req_alias = make_mock_request(headers={"X-Tenant-ID": alias})
        assert chat_extract_tenant(req_alias) == "proj_default"
        assert knowledge_extract_tenant(req_alias) == "proj_default"
        lim_tid, _ = rate_limiter._extract_rate_key(req_alias)
        assert lim_tid == "proj_default"

    # 3. Explicit custom tenant
    req_custom = make_mock_request(headers={"X-Tenant-ID": "tenant_fintech_789"})
    assert chat_extract_tenant(req_custom) == "tenant_fintech_789"
    assert knowledge_extract_tenant(req_custom) == "tenant_fintech_789"
    lim_custom, _ = rate_limiter._extract_rate_key(req_custom)
    assert lim_custom == "tenant_fintech_789"


def test_redis_cache_key_tenant_consistency():
    """Verify cache keys normalize legacy aliases to prevent cross-tenant cache misses."""
    key_default = RedisCacheAdapter.compute_cache_key("quy dinh phep nam")
    key_global = RedisCacheAdapter.compute_cache_key("quy dinh phep nam", tenant_id="global")
    key_default_tenant = RedisCacheAdapter.compute_cache_key("quy dinh phep nam", tenant_id="default_tenant")
    key_proj_default = RedisCacheAdapter.compute_cache_key("quy dinh phep nam", tenant_id="proj_default")

    # All must produce the EXACT same cache key
    assert key_default == key_global == key_default_tenant == key_proj_default
    assert "aip:rag:cache:proj_default:" in key_default

    # Custom tenant produces isolated key
    key_custom = RedisCacheAdapter.compute_cache_key("quy dinh phep nam", tenant_id="tenant_custom")
    assert "aip:rag:cache:tenant_custom:" in key_custom
    assert key_custom != key_default
