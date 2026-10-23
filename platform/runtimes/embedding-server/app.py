"""
AIP Embedding & Reranking Server.

Serves the `embed-standard` (BAAI/bge-m3) and `rerank-standard` (BAAI/bge-reranker-v2-m3)
aliases on one port so both MongoDB alias records can point at the same target_url:

    POST /v1/embeddings   OpenAI-compatible, optional BGE-M3 sparse weights
    POST /v1/rerank       Cohere/Jina/TEI-compatible cross-encoder scores in [0, 1]
    GET  /v1/models
    GET  /health, /health/live, /health/ready
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

try:
    from .config import settings
    from .engine import BgeEngine, ModelNotReadyError
    from .schemas import (
        EmbeddingItem,
        EmbeddingRequest,
        EmbeddingResponse,
        RerankRequest,
        RerankResponse,
        RerankResult,
        SparseVector,
        Usage,
    )
except ImportError:  # executed as `uvicorn app:app` from the runtime directory
    from config import settings
    from engine import BgeEngine, ModelNotReadyError
    from schemas import (
        EmbeddingItem,
        EmbeddingRequest,
        EmbeddingResponse,
        RerankRequest,
        RerankResponse,
        RerankResult,
        SparseVector,
        Usage,
    )

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("aip-embedding-server")

engine = BgeEngine(settings)

_PUBLIC_PATHS = {"/health", "/health/live", "/health/ready", "/docs", "/openapi.json"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_in_threadpool(engine.load)
    yield


app = FastAPI(
    title="AIP Embedding & Reranking Server",
    version=settings.version,
    description="BGE-M3 embeddings and BGE-Reranker-v2-m3 cross-encoder scoring",
    lifespan=lifespan,
)


@app.middleware("http")
async def runtime_auth(request: Request, call_next):
    """Same contract as common.security.runtime_auth.RuntimeAuthMiddleware."""
    if settings.disable_auth or request.url.path in _PUBLIC_PATHS:
        return await call_next(request)
    if settings.runtime_token:
        if request.headers.get("X-AIP-Runtime-Token") != settings.runtime_token:
            return JSONResponse(status_code=401, content={"detail": "Invalid runtime service token"})
    elif not request.headers.get("Authorization", "").startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "Bearer API key required"})
    return await call_next(request)


def _check_model(requested: str | None, served: list[str], kind: str) -> str:
    if not requested:
        return served[0]
    if requested not in served:
        raise HTTPException(status_code=404, detail=f"{kind} model '{requested}' is not served here; available: {served}")
    return requested


@app.post("/v1/embeddings", response_model=EmbeddingResponse)
async def create_embeddings(payload: EmbeddingRequest) -> EmbeddingResponse:
    model = _check_model(payload.model, settings.embedding_model_names, "Embedding")
    texts = [payload.input] if isinstance(payload.input, str) else list(payload.input)
    if not texts:
        raise HTTPException(status_code=422, detail="input must not be empty")
    if len(texts) > settings.max_inputs_per_request:
        raise HTTPException(status_code=413, detail=f"At most {settings.max_inputs_per_request} inputs per request")
    if any(len(t) > settings.max_chars_per_input for t in texts):
        raise HTTPException(status_code=413, detail=f"Each input must be <= {settings.max_chars_per_input} characters")

    try:
        result = await run_in_threadpool(engine.embed, texts, payload.return_sparse)
    except ModelNotReadyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    data = []
    for i, vec in enumerate(result["dense"]):
        sparse = SparseVector(**result["sparse"][i]) if result["sparse"] else None
        data.append(EmbeddingItem(index=i, embedding=vec, sparse=sparse))
    tokens = result["prompt_tokens"]
    return EmbeddingResponse(data=data, model=model, usage=Usage(prompt_tokens=tokens, total_tokens=tokens))


@app.post("/v1/rerank", response_model=RerankResponse)
async def rerank(payload: RerankRequest) -> RerankResponse:
    model = _check_model(payload.model, settings.reranker_model_names, "Reranker")
    if len(payload.documents) > settings.max_documents_per_rerank:
        raise HTTPException(status_code=413, detail=f"At most {settings.max_documents_per_rerank} documents per request")

    t0 = time.perf_counter()
    try:
        scores = await run_in_threadpool(engine.rerank, payload.query, payload.documents)
    except ModelNotReadyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    if payload.top_n:
        ranked = ranked[: payload.top_n]
    results = [
        RerankResult(
            index=i,
            relevance_score=round(scores[i], 6),
            document=payload.documents[i] if payload.return_documents else None,
        )
        for i in ranked
    ]
    return RerankResponse(results=results, model=model, latency_ms=round((time.perf_counter() - t0) * 1000, 2))


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {"id": settings.embedding_model_names[0], "object": "model", "category": "embedding",
             "physical_model": settings.embedding_model_path, "dimensions": settings.embedding_dim},
            {"id": settings.reranker_model_names[0], "object": "model", "category": "reranker",
             "physical_model": settings.reranker_model_path},
        ],
    }


@app.get("/health")
@app.get("/health/live")
async def health():
    return engine.status()


@app.get("/health/ready")
async def ready():
    status = engine.status()
    return JSONResponse(status_code=200 if engine.ready else 503, content=status)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)
