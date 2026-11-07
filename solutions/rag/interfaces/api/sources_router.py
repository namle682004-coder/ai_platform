"""
Data sources read by connectors (/v1/knowledge/sources). Administrators of a tenant only.

Configurations are validated here (allowed hosts cover every URL, secrets referenced by environment variable
name with the required prefix); a sync requested through the API runs in the ingestion worker.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator

from ...config import rag_settings
from ...infrastructure.connectors import SOURCE_TYPES
from ...infrastructure.connectors.http import host_of
from ...infrastructure.repositories.mongo_document_repo import MongoDocumentRepositoryAdapter
from ...infrastructure.repositories.mongo_source_repo import MongoSourceRepository
from .identity import extract_tenant, is_admin

logger = logging.getLogger("aip-rag.api.sources")
router = APIRouter(prefix="/v1/knowledge/sources", tags=["Knowledge sources"])

_sources = MongoSourceRepository(rag_settings.mongo_uri)
_docs = MongoDocumentRepositoryAdapter(mongo_uri=rag_settings.mongo_uri)
AUTH_TYPES = ("none", "bearer", "header", "basic", "cookie")


class SourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: str
    config: Dict[str, Any]
    auth: Dict[str, Any] = Field(default_factory=lambda: {"type": "none"})
    schedule_minutes: int = Field(default=60, ge=0, le=7 * 24 * 60, description="0 = manual syncs only")
    enabled: bool = True
    allowed_roles: List[str] = Field(default_factory=lambda: ["*"])
    department: Optional[str] = None

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        if v not in SOURCE_TYPES:
            raise ValueError(f"type must be one of {SOURCE_TYPES}")
        return v


class SourcePatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    config: Optional[Dict[str, Any]] = None
    auth: Optional[Dict[str, Any]] = None
    schedule_minutes: Optional[int] = Field(default=None, ge=0, le=7 * 24 * 60)
    enabled: Optional[bool] = None
    allowed_roles: Optional[List[str]] = None
    department: Optional[str] = None


def _validate(source_type: str, config: Dict[str, Any], auth: Dict[str, Any], preview: bool = False) -> List[str]:
    """
    Problems that make the configuration unusable (422). A trial read (preview) does not need the record id yet:
    it is how the administrator finds which field holds it.
    """
    problems: List[str] = []
    hosts = {h.lower() for h in config.get("allowed_hosts") or []}
    if not hosts:
        problems.append("config.allowed_hosts is required")
    urls = [config.get("url")] if source_type == "json_api" else list(config.get("start_urls") or [])
    if source_type == "json_api" and not config.get("id_field") and not preview:
        problems.append("config.id_field is required")
    if not any(urls):
        problems.append("config.url is required" if source_type == "json_api" else "config.start_urls is required")
    for u in urls:
        if u and (not str(u).startswith(("http://", "https://")) or host_of(str(u)) not in hosts):
            problems.append(f"{u}: must be http(s) on one of config.allowed_hosts")
    kind = (auth.get("type") or "none").lower()
    if kind not in AUTH_TYPES:
        problems.append(f"auth.type must be one of {AUTH_TYPES}")
    for k in ("token_env", "password_env"):
        name = auth.get(k)
        if name and not str(name).startswith(rag_settings.connector_secret_env_prefix):
            problems.append(f"auth.{k} must start with {rag_settings.connector_secret_env_prefix}")
    for k in auth or {}:
        if k not in ("type", "token_env", "password_env", "header", "username"):
            problems.append(f"auth.{k} is not accepted: store secrets in environment variables, not in the source")
    return problems


def _missing_secrets(auth: Dict[str, Any]) -> List[str]:
    return [str(auth[k]) for k in ("token_env", "password_env") if auth.get(k) and not os.getenv(str(auth[k]))]


def _require_admin(request: Request) -> str:
    if not is_admin(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Managing data sources requires an admin role")
    return extract_tenant(request)


async def _owned(source_id: str, tenant_id: str) -> Dict[str, Any]:
    source = await _sources.get(source_id, tenant_id)
    if not source:
        raise HTTPException(status_code=404, detail=f"Source '{source_id}' not found")
    return source


def _public(source: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in source.items() if k not in ("lease_owner", "lease_until")}
    out["missing_secrets"] = _missing_secrets(source.get("auth") or {})
    return out


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_source(body: SourceIn, request: Request) -> Dict[str, Any]:
    tenant_id = _require_admin(request)
    problems = _validate(body.type, body.config, body.auth)
    if problems:
        raise HTTPException(status_code=422, detail=problems)
    now = time.time()
    source = {
        "source_id": f"srcdef_{uuid.uuid4().hex[:12]}", "tenant_id": tenant_id, **body.model_dump(),
        "created_at": now, "updated_at": now, "next_sync_at": now if body.schedule_minutes else None,
        "cursor": {}, "consecutive_failures": 0,
    }
    await _sources.create(source)
    logger.info("Source %s (%s) created for tenant %s", source["source_id"], body.type, tenant_id)
    return _public(source)


class SourcePreviewIn(BaseModel):
    name: str = Field(default="Xem trước", max_length=200)
    type: str
    config: Dict[str, Any]
    auth: Dict[str, Any] = Field(default_factory=lambda: {"type": "none"})


PREVIEW_TIMEOUT_SECONDS = 60.0


@router.post("/preview")
async def preview_source(body: SourcePreviewIn, request: Request) -> Dict[str, Any]:
    """Reads the source once with this configuration and reports what it holds; nothing is stored."""
    tenant_id = _require_admin(request)
    if body.type not in SOURCE_TYPES:
        raise HTTPException(status_code=422, detail=[f"type must be one of {SOURCE_TYPES}"])
    problems = _validate(body.type, body.config, body.auth, preview=True)
    if problems:
        raise HTTPException(status_code=422, detail=problems)
    from ...infrastructure.connectors.preview import preview_source as run_preview

    source = {"source_id": "preview", "tenant_id": tenant_id, **body.model_dump()}
    try:
        return await asyncio.wait_for(run_preview(source), timeout=PREVIEW_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        return {"ok": False, "type": body.type, "error": f"the source did not answer within {PREVIEW_TIMEOUT_SECONDS:.0f}s"}


@router.get("")
async def list_sources(request: Request) -> Dict[str, Any]:
    tenant_id = _require_admin(request)
    counts = await _docs.count_by_source(tenant_id)
    items = [{**_public(s), "documents": counts.get(s["source_id"], 0)} for s in await _sources.list(tenant_id)]
    return {"items": items, "total": len(items)}


@router.get("/{source_id}")
async def get_source(source_id: str, request: Request) -> Dict[str, Any]:
    tenant_id = _require_admin(request)
    source = _public(await _owned(source_id, tenant_id))
    source["documents"] = len(await _docs.find_by_source(tenant_id, source_id))
    return source


@router.patch("/{source_id}")
async def update_source(source_id: str, body: SourcePatch, request: Request) -> Dict[str, Any]:
    tenant_id = _require_admin(request)
    current = await _owned(source_id, tenant_id)
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    merged = {**current, **fields}
    problems = _validate(merged["type"], merged["config"], merged.get("auth") or {})
    if problems:
        raise HTTPException(status_code=422, detail=problems)
    fields["updated_at"] = time.time()
    if "schedule_minutes" in fields or "enabled" in fields:
        fields["next_sync_at"] = time.time() if merged.get("schedule_minutes") else None
    return _public(await _sources.update(source_id, tenant_id, fields) or merged)


@router.delete("/{source_id}")
async def delete_source(source_id: str, request: Request, purge: bool = Query(False)) -> Dict[str, Any]:
    tenant_id = _require_admin(request)
    await _owned(source_id, tenant_id)
    removed = 0
    if purge:
        from .knowledge_router import knowledge_use_case

        for doc in await _docs.find_by_source(tenant_id, source_id):
            removed += bool(await knowledge_use_case.delete_document(doc["doc_id"], tenant_id))
    await _sources.delete(source_id, tenant_id)
    return {"deleted": True, "documents_deleted": removed}


@router.post("/{source_id}/sync", status_code=status.HTTP_202_ACCEPTED)
async def sync_source(source_id: str, request: Request) -> Dict[str, Any]:
    tenant_id = _require_admin(request)
    await _owned(source_id, tenant_id)
    from ...infrastructure.adapters.rabbitmq_adapter import rabbitmq_broker

    ok = await rabbitmq_broker.publish(queue_name=rag_settings.rag_queue,
                                       payload={"payload": {"type": "source_sync", "source_id": source_id}})
    if not ok:
        raise HTTPException(status_code=503, detail="Ingestion queue unavailable; retry later")
    return {"queued": True, "source_id": source_id}


@router.get("/{source_id}/runs")
async def source_runs(source_id: str, request: Request, limit: int = Query(20, ge=1, le=50)) -> Dict[str, Any]:
    tenant_id = _require_admin(request)
    await _owned(source_id, tenant_id)
    return {"items": await _sources.runs(source_id, limit)}
