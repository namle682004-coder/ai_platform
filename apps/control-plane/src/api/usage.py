"""
Enterprise Usage & Token Metering Query API.
Compliant with Clean Architecture Control-Plane & SRS Section 7 & 8.
"""

import time
from typing import Optional
from fastapi import APIRouter, Request, Query
from common.repositories.usage_repository import usage_repository
from src.db.redis import redis_service

router = APIRouter(prefix="/v1/usage", tags=["Usage Metering & Token Consumption"])


@router.get("/summary", summary="Get Aggregated Token Usage and Cost Summary")
async def get_usage_summary(
    request: Request,
    tenant_id: Optional[str] = Query(None, description="Optional tenant filter"),
):
    """Retrieve aggregate usage statistics (requests, tokens, cost) for tenant or organization."""
    caller_tenant = getattr(request.state, "tenant_id", "TENANT_RETAIL_BANK")
    target_tenant = tenant_id or caller_tenant

    summary = await usage_repository.get_usage_summary(tenant_id=target_tenant)
    return summary


@router.get("/records", summary="List Granular Inference Usage Records")
async def list_usage_records(
    request: Request,
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID"),
    domain: Optional[str] = Query(None, description="Filter by service domain (e.g. chat, embedding)"),
    model_alias: Optional[str] = Query(None, description="Filter by model alias"),
    limit: int = Query(50, ge=1, le=500, description="Max number of records to return"),
):
    """Retrieve detailed log of recent inference token consumption records."""
    caller_tenant = getattr(request.state, "tenant_id", "TENANT_RETAIL_BANK")
    target_tenant = tenant_id or caller_tenant

    records = await usage_repository.list_usage_records(
        tenant_id=target_tenant,
        domain=domain,
        model_alias=model_alias,
        limit=limit,
    )
    return {
        "object": "list",
        "data": records,
        "count": len(records),
    }


@router.get("/tpm", summary="Get Current Realtime TPM (Tokens Per Minute) Status")
async def get_realtime_tpm(request: Request):
    """Check current minute's real-time token consumption against TPM quota limit."""
    caller_tenant = getattr(request.state, "tenant_id", "TENANT_RETAIL_BANK")
    tpm_limit = getattr(request.state, "tpm_limit", 100000)

    current_tpm = 0
    try:
        client = redis_service.get_client()
        if client:
            minute_ts = int(time.time() // 60) * 60
            tpm_key = f"aip:tpm:{caller_tenant}:{minute_ts}"
            val = await client.get(tpm_key)
            if val is not None:
                current_tpm = int(val)
    except Exception:
        pass

    return {
        "tenant_id": caller_tenant,
        "current_tpm": current_tpm,
        "tpm_limit": tpm_limit,
        "utilization_pct": round((current_tpm / tpm_limit) * 100, 2) if tpm_limit > 0 else 0.0,
        "status": "normal" if current_tpm < tpm_limit else "exceeded",
    }
