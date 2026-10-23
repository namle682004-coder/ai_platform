"""
Unified API Router for Enterprise RAG Solution.
Mounts both Chat & Sessions and Knowledge & Documents routers.
"""

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from .chat_router import router as chat_router
from .knowledge_router import router as knowledge_router

rag_api_router = APIRouter()
rag_api_router.include_router(chat_router)
rag_api_router.include_router(knowledge_router)


@rag_api_router.get("/metrics", tags=["Observability"], summary="Expose Prometheus Metrics")
def get_prometheus_metrics():
    """Scrape endpoint exposing real-time Prometheus metrics for RAG service."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


__all__ = ["rag_api_router", "chat_router", "knowledge_router"]
