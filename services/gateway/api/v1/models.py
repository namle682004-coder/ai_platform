from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/v1", tags=["Models & Aliases"])

_MODELS_CATALOG = [
    {
        "id": "chat-general-standard",
        "object": "model",
        "created": 1770970000,
        "owned_by": "aip-platform",
        "runtime": "vLLM (Qwen3-8B)",
        "min_vram_gb": 24,
        "status": "active",
        "version": "v1.0"
    },
    {
        "id": "chat-general-high-quality",
        "object": "model",
        "created": 1770970000,
        "owned_by": "aip-platform",
        "runtime": "vLLM (Qwen3-14B)",
        "min_vram_gb": 32,
        "status": "active",
        "version": "v1.0"
    },
    {
        "id": "embed-standard",
        "object": "model",
        "created": 1770970000,
        "owned_by": "aip-platform",
        "runtime": "TEI (bge-m3)",
        "min_vram_gb": 8,
        "status": "active",
        "version": "v1.0"
    },
    {
        "id": "translate-vi-standard",
        "object": "model",
        "created": 1770970000,
        "owned_by": "aip-platform",
        "runtime": "CTranslate2 (NLLB-200)",
        "min_vram_gb": 16,
        "status": "active",
        "version": "v1.0"
    },
    {
        "id": "stt-vn-standard",
        "object": "model",
        "created": 1770970000,
        "owned_by": "aip-platform",
        "runtime": "Faster-Whisper (PhoWhisper)",
        "min_vram_gb": 16,
        "status": "active",
        "version": "v1.0"
    },
]


@router.get("/models")
async def list_models():
    return {
        "object": "list",
        "data": _MODELS_CATALOG
    }


@router.get("/models/{alias}")
async def get_model_alias(alias: str):
    for m in _MODELS_CATALOG:
        if m["id"] == alias:
            return m
    raise HTTPException(status_code=404, detail=f"Model alias '{alias}' not found.")
