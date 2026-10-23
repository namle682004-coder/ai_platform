"""
Local RAG Adapter for Track B (End-to-End Evaluation).
Connects to live AIP Control Plane API (:8000/v1/rag/chat).
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional
import httpx

from .base import NormalizedResponse, RAGAdapter


class LocalRAGAdapter:
    """Adapter invoking the end-to-end Local RAG pipeline via REST endpoint."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: str = "aip_live_valid_test_key_12345",
        timeout: float = 120.0,
    ) -> None:
        self.base_url = (base_url or os.getenv("RAG_API_URL", "http://localhost:8010")).rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    async def answer(
        self,
        question: str,
        *,
        context: Optional[List[Dict[str, Any]]] = None,
        top_k: int = 5,
    ) -> NormalizedResponse:
        start_t = time.time()
        endpoint = f"{self.base_url}/v1/rag/chat"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "query": question,
            "top_k": top_k,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(endpoint, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        latency_ms = (time.time() - start_t) * 1000

        # Extract retrieved chunks / source documents
        source_docs = data.get("source_documents") or data.get("citations") or []
        retrieved_chunks = []
        for idx, doc in enumerate(source_docs, start=1):
            retrieved_chunks.append({
                "document_id": doc.get("doc_id") or doc.get("title", ""),
                "chunk_id": doc.get("chunk_id"),
                "title": doc.get("title"),
                "score": float(doc.get("score", 0.0)),
                "rank": idx,
                "excerpt": doc.get("excerpt") or doc.get("text"),
            })

        citations = data.get("citations") or []

        return NormalizedResponse(
            answer=data.get("answer", ""),
            retrieved_chunks=retrieved_chunks,
            citations=citations,
            latency_ms=round(latency_ms, 2),
            input_tokens=data.get("prompt_tokens"),
            output_tokens=data.get("completion_tokens"),
            intent=data.get("intent"),
            route_taken=data.get("route_taken"),
        )
