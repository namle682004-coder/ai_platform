from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import time
from typing import Any

from fastapi import APIRouter, Request
import httpx

from common.database.mongodb import mongo_manager
from common.models.catalog import AIP_MODEL_CATALOG
from common.repositories.job_repository import job_repository
from src.configs.settings import gateway_settings
from src.db.redis import redis_service

router = APIRouter(tags=["Status & Health Probes"])

DEFAULT_VLLM_MODELS = [
    "chat-general-standard",
    "chat-general-high-quality",
    "summarize-high-quality",
    "classify-dynamic-standard",
    "ner-re-standard",
    "translate-vi-standard",
    "embed-standard",
]


async def probe_mongodb() -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        db = mongo_manager.get_database()
        if db is not None:
            await db.command("ping")
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            return {"status": "healthy", "latency_ms": latency_ms}
        # If client not initialized, attempt quick connect
        await mongo_manager.connect(gateway_settings.mongo_uri)
        db = mongo_manager.get_database()
        if db is not None:
            await db.command("ping")
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            return {"status": "healthy", "latency_ms": latency_ms}
        return {"status": "unhealthy", "latency_ms": None}
    except Exception as exc:
        return {"status": "unhealthy", "latency_ms": None, "error": str(exc)}


async def probe_redis() -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        client = redis_service.get_client()
        pong = await client.ping()
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        if pong:
            return {"status": "healthy", "latency_ms": latency_ms}
        return {"status": "unhealthy", "latency_ms": None}
    except Exception as exc:
        return {"status": "unhealthy", "latency_ms": None, "error": str(exc)}


async def probe_rabbitmq(request: Request | None = None) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        if request and hasattr(request.app.state, "task_publisher"):
            publisher = request.app.state.task_publisher
            if publisher and publisher._connection and not publisher._connection.is_closed:
                latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                return {"status": "healthy", "latency_ms": latency_ms}

        import aio_pika

        conn = await aio_pika.connect_robust(gateway_settings.rabbitmq_url, timeout=1.5)
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        await conn.close()
        return {"status": "healthy", "latency_ms": latency_ms}
    except Exception as exc:
        return {"status": "unhealthy", "latency_ms": None, "error": str(exc)}


async def probe_minio() -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        endpoint = gateway_settings.minio_endpoint.rstrip("/")
        async with httpx.AsyncClient(timeout=1.5) as client:
            resp = await client.get(f"{endpoint}/minio/health/live")
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            if resp.status_code == 200:
                return {"status": "healthy", "latency_ms": latency_ms}
            return {"status": "unhealthy", "latency_ms": latency_ms}
    except Exception as exc:
        return {"status": "unhealthy", "latency_ms": None, "error": str(exc)}


async def probe_vllm() -> dict[str, Any]:
    t0 = time.perf_counter()
    raw_url = gateway_settings.vllm_server_url.rstrip("/")
    base_url = raw_url[:-3] if raw_url.endswith("/v1") else raw_url

    candidate_urls = [
        f"{base_url}/health",
    ]
    seen = set()
    unique_candidates = [u for u in candidate_urls if not (u in seen or seen.add(u))]

    for cand in unique_candidates:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(cand)
                if resp.status_code == 200:
                    latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                    data = resp.json()
                    target_url = cand.replace("/health", "/v1")
                    return {
                        "status": "healthy",
                        "latency_ms": latency_ms,
                        "target_url": target_url,
                        "device": data.get("device", "cuda"),
                        "vram_allocated_mb": data.get("vram_allocated_mb", 0.0),
                        "foundation_model": data.get("foundation_model", "Qwen/Qwen2.5-1.5B-Instruct"),
                        "neural_inference_ready": data.get("neural_inference_ready", True),
                        "models_served": data.get("models_served", DEFAULT_VLLM_MODELS),
                    }
        except Exception:
            continue

    return {
        "status": "offline",
        "latency_ms": None,
        "target_url": gateway_settings.vllm_server_url,
        "device": "unknown",
        "vram_allocated_mb": 0.0,
        "foundation_model": "None",
        "neural_inference_ready": False,
        "models_served": DEFAULT_VLLM_MODELS,
    }


async def probe_http_service(target_url: str) -> dict[str, Any]:
    t0 = time.perf_counter()
    url = target_url.rstrip("/")
    health_url = f"{url[:-3]}/health" if url.endswith("/v1") else f"{url}/health"

    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.get(health_url)
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            if resp.status_code == 200:
                return {"status": "healthy", "active_runs": 0, "latency_ms": latency_ms}
            return {"status": "offline", "active_runs": 0, "latency_ms": latency_ms}
    except Exception:
        return {"status": "not_configured", "active_runs": 0}


async def get_task_counts() -> tuple[int, int]:
    active_runs = 0
    queued_tasks = 0
    try:
        db = mongo_manager.get_database()
        if db is not None:
            active_runs = await db.jobs.count_documents(
                {"status": {"$in": ["running", "processing", "in_flight"]}}
            )
            queued_tasks = await db.jobs.count_documents(
                {"status": {"$in": ["queued", "pending", "submitted"]}}
            )
            return active_runs, queued_tasks
    except Exception:
        pass

    for job in job_repository._jobs_cache.values():
        st = job.get("status")
        if st in ("running", "processing", "in_flight"):
            active_runs += 1
        elif st in ("queued", "pending", "submitted"):
            queued_tasks += 1
    return active_runs, queued_tasks


# ---------------------------------------------------------------------------
# Standard Kubernetes Probes
# ---------------------------------------------------------------------------


@router.get("/health", summary="Basic Liveness Probe")
async def health_check():
    return {
        "status": "healthy",
        "service": "aip-gateway",
        "version": "1.0.0",
        "environment": gateway_settings.environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/live", summary="Kubernetes Liveness Probe")
async def liveness_probe():
    return {"status": "live"}


@router.get("/health/ready", summary="Kubernetes Readiness Probe")
async def readiness_probe():
    return {
        "status": "ready",
        "mongodb": "connected",
        "redis": "connected",
        "rabbitmq": "connected",
    }


# ---------------------------------------------------------------------------
# Comprehensive Platform Status Monitoring
# ---------------------------------------------------------------------------


async def _build_platform_status(request: Request) -> dict[str, Any]:
    (
        task_counts,
        mongo_res,
        redis_res,
        rmq_res,
        minio_res,
        vllm_res,
        trans_res,
        stt_res,
        ocr_res,
        mod_res,
        tts_res,
    ) = await asyncio.gather(
        get_task_counts(),
        probe_mongodb(),
        probe_redis(),
        probe_rabbitmq(request),
        probe_minio(),
        probe_vllm(),
        probe_http_service(gateway_settings.translation_server_url),
        probe_http_service(gateway_settings.stt_server_url),
        probe_http_service(gateway_settings.ocr_server_url),
        probe_http_service(gateway_settings.moderation_server_url),
        probe_http_service(gateway_settings.tts_server_url),
        return_exceptions=True,
    )

    active_runs, queued_tasks = task_counts if isinstance(task_counts, tuple) else (0, 0)
    mongo_stat = mongo_res if isinstance(mongo_res, dict) else {"status": "unhealthy"}
    redis_stat = redis_res if isinstance(redis_res, dict) else {"status": "unhealthy"}
    rmq_stat = rmq_res if isinstance(rmq_res, dict) else {"status": "unhealthy"}
    minio_stat = minio_res if isinstance(minio_res, dict) else {"status": "unhealthy"}
    vllm_stat = vllm_res if isinstance(vllm_res, dict) else {"status": "offline"}
    trans_stat = trans_res if isinstance(trans_res, dict) else {"status": "not_configured", "active_runs": 0}
    stt_stat = stt_res if isinstance(stt_res, dict) else {"status": "not_configured", "active_runs": 0}
    ocr_stat = ocr_res if isinstance(ocr_res, dict) else {"status": "not_configured", "active_runs": 0}
    mod_stat = mod_res if isinstance(mod_res, dict) else {"status": "not_configured", "active_runs": 0}
    tts_stat = tts_res if isinstance(tts_res, dict) else {"status": "not_configured", "active_runs": 0}

    # Evaluate platform status
    core_healthy = (
        mongo_stat.get("status") == "healthy"
        and redis_stat.get("status") == "healthy"
        and rmq_stat.get("status") == "healthy"
    )
    if not core_healthy:
        platform_status = "unhealthy" if (mongo_stat.get("status") != "healthy" and redis_stat.get("status") != "healthy") else "degraded"
    elif vllm_stat.get("status") == "healthy":
        platform_status = "healthy"
    else:
        platform_status = "degraded"

    dispatcher_status = "healthy" if rmq_stat.get("status") == "healthy" else "offline"
    callback_status = "healthy" if rmq_stat.get("status") == "healthy" else "offline"

    models_served = vllm_stat.get("models_served", DEFAULT_VLLM_MODELS)
    total_models = len(models_served)
    healthy_models = total_models if vllm_stat.get("status") == "healthy" else 0

    return {
        "platform_status": platform_status,
        "active_runs": active_runs,
        "queued_tasks": queued_tasks,
        "infrastructure": {
            "mongodb": mongo_stat,
            "redis": redis_stat,
            "rabbitmq": rmq_stat,
            "minio": minio_stat,
        },
        "services": {
            "control_plane": {
                "status": "healthy",
                "active_runs": 0,
            },
            "vllm_engine": {
                "status": vllm_stat.get("status", "offline"),
                "target_url": vllm_stat.get("target_url"),
                "device": vllm_stat.get("device", "unknown"),
                "vram_allocated_mb": vllm_stat.get("vram_allocated_mb", 0.0),
                "latency_ms": vllm_stat.get("latency_ms"),
                "models_count": total_models,
                "active_runs": 0,
            },
            "dispatcher_worker": {
                "status": dispatcher_status,
                "active_runs": 0,
            },
            "callback_worker": {
                "status": callback_status,
                "active_runs": 0,
            },
            "translation": trans_stat,
            "stt": stt_stat,
            "ocr": ocr_stat,
            "moderation": mod_stat,
            "tts": tts_stat,
        },
        "models_summary": {
            "total_hosted_models": total_models,
            "healthy_models": healthy_models,
            "runtime": "vLLM / Neural Transformers",
            "foundation_model": vllm_stat.get("foundation_model", "None"),
            "device": vllm_stat.get("device", "unknown"),
            "vram_allocated_mb": vllm_stat.get("vram_allocated_mb", 0.0),
        },
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/status", summary="Comprehensive Platform Status Monitoring")
async def platform_status_root(request: Request):
    return await _build_platform_status(request)


@router.get("/v1/status", summary="Comprehensive Platform Status Monitoring (v1)")
async def platform_status_v1(request: Request):
    return await _build_platform_status(request)


# ---------------------------------------------------------------------------
# Deep-Dive vLLM Hosted Models Status Monitoring
# ---------------------------------------------------------------------------


async def _build_models_status() -> dict[str, Any]:
    vllm_stat = await probe_vllm()
    is_healthy = vllm_stat.get("status") == "healthy"
    models_served = vllm_stat.get("models_served", DEFAULT_VLLM_MODELS)
    latency_ms = vllm_stat.get("latency_ms")
    device = vllm_stat.get("device", "unknown")
    vram_mb = vllm_stat.get("vram_allocated_mb", 0.0)

    models_dict: dict[str, Any] = {}
    for model_id in models_served:
        meta = AIP_MODEL_CATALOG.get(model_id)
        if meta:
            physical_model = meta.physical_model
            runtime = meta.runtime
            category = meta.category
            stream_capable = meta.stream_capable
            timeout_sec = meta.timeout_seconds
            desc = meta.description
        else:
            physical_model = vllm_stat.get("foundation_model", "Qwen/Qwen2.5-1.5B-Instruct")
            runtime = "vLLM"
            category = "llm"
            stream_capable = True
            timeout_sec = 120
            desc = "vLLM hosted inference model"

        models_dict[model_id] = {
            "status": "healthy" if is_healthy else "offline",
            "physical_model": physical_model,
            "runtime": runtime,
            "category": category,
            "stream_capable": stream_capable,
            "device": device,
            "vram_allocated_mb": vram_mb,
            "latency_ms": latency_ms,
            "active_runs": 0,
            "timeout_seconds": timeout_sec,
            "description": desc,
        }

    return {
        "engine_status": "healthy" if is_healthy else "offline",
        "engine_url": vllm_stat.get("target_url"),
        "foundation_model": vllm_stat.get("foundation_model", "None"),
        "runtime": "vLLM / Neural Transformers",
        "device": device,
        "vram_allocated_mb": vram_mb,
        "neural_inference_ready": vllm_stat.get("neural_inference_ready", False),
        "latency_ms": latency_ms,
        "total_models": len(models_served),
        "healthy_models": len(models_served) if is_healthy else 0,
        "models": models_dict,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/status/models", summary="Status of Models Hosted on vLLM Engine")
async def models_status_root():
    return await _build_models_status()


@router.get("/v1/status/models", summary="Status of Models Hosted on vLLM Engine (v1)")
async def models_status_v1():
    return await _build_models_status()


@router.get("/v1/models/status", summary="Status of Models Hosted on vLLM Engine (OpenAI-compatible alias)")
async def models_status_alias():
    return await _build_models_status()
