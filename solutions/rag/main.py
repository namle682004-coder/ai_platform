"""
Main Service Entrypoint for AIP RAG Solution.
Can run standalone FastAPI server or Worker consumer.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Ensure workspace root is in sys.path when executed directly as a script
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import uvicorn
from fastapi import FastAPI

from solutions.rag.interfaces.api.identity import InternalCallerMiddleware
from solutions.rag.interfaces.api.metrics_middleware import RagObservabilityMiddleware
from solutions.rag.interfaces.api.rate_limiter import RateLimitHeaderMiddleware
from solutions.rag.interfaces.api.router import rag_api_router
from solutions.rag.interfaces.worker.consumer import RagWorkerConsumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("aip-rag.main")


def create_app() -> FastAPI:
    app = FastAPI(
        title="AIP Enterprise RAG Solution API",
        version="1.0.0",
        description="Domain-Driven Design (DDD) Enterprise RAG Solution API with Hybrid Search and Session Persistence.",
    )
    app.add_middleware(RagObservabilityMiddleware)
    app.add_middleware(RateLimitHeaderMiddleware)
    # Added last so it runs first: authenticates service callers before identity is read.
    app.add_middleware(InternalCallerMiddleware)
    app.include_router(rag_api_router)

    @app.get("/health", tags=["Health"], summary="Health Check")
    @app.get("/health/live", tags=["Health"], summary="Liveness Probe")
    @app.get("/health/ready", tags=["Health"], summary="Readiness Probe")
    async def health_check():
        return {"status": "ok", "service": "aip-rag"}

    return app


app = create_app()


def run_api(host: str = "0.0.0.0", port: int = 8010) -> None:
    uvicorn.run("solutions.rag.main:app", host=host, port=port, reload=False)


async def run_worker() -> None:
    consumer = RagWorkerConsumer()
    await consumer.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AIP RAG Solution Entrypoint")
    parser.add_argument("--mode", choices=["api", "worker"], default="api", help="Execution mode")
    parser.add_argument("--host", default="0.0.0.0", help="API Host")
    parser.add_argument("--port", type=int, default=8010, help="API Port")
    args = parser.parse_args()

    if args.mode == "worker":
        asyncio.run(run_worker())
    else:
        run_api(host=args.host, port=args.port)
