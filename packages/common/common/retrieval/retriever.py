"""
Enterprise Hybrid Document Retriever for Multi-Tenant Qdrant Search.
Combines Dense Vector Similarity + Full-Text Keyword Match using Reciprocal Rank Fusion (RRF).
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("aip-common.retriever")


@dataclass
class RetrievedChunk:
    doc_id: str
    chunk_index: int
    title: str
    page_number: int
    score: float
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    dense_rank: Optional[int] = None
    sparse_rank: Optional[int] = None
    rrf_score: float = 0.0


class DocumentRetriever:
    """Production-grade Hybrid Retriever (Dense Vector + Full-Text Keyword with RRF)."""

    def __init__(
        self,
        qdrant_url: Optional[str] = None,
        collection_name: str = "aip_knowledge_base",
    ) -> None:
        if not qdrant_url:
            default_host = "http://qdrant:6333" if os.path.exists("/.dockerenv") else "http://127.0.0.1:6333"
            qdrant_url = os.getenv("QDRANT_URL", default_host)
        self.qdrant_url = qdrant_url.rstrip("/")
        self.collection_name = collection_name
        self._index_ensured = False

    async def ensure_text_index(self) -> None:
        """Ensure full-text inverted index exists on payload text field."""
        if self._index_ensured:
            return
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.put(
                    f"{self.qdrant_url}/collections/{self.collection_name}/index",
                    json={"field_name": "text", "field_schema": "text"},
                )
            self._index_ensured = True
        except Exception as exc:
            logger.debug("Could not verify Qdrant full-text index: %s", exc)

    def _build_filter_conditions(
        self,
        tenant_id: str,
        user_role: str = "user",
        department: Optional[str] = None,
        doc_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        must: List[Dict[str, Any]] = [
            {"key": "tenant_id", "match": {"value": tenant_id}}
        ]
        if department and department not in ("ALL", "*"):
            must.append({
                "should": [
                    {"key": "department", "match": {"value": department}},
                    {"key": "department", "match": {"value": "GENERAL"}},
                    {"key": "department", "match": {"value": ""}},
                    {"key": "department", "match": {"value": "string"}},
                ]
            })
        if doc_ids:
            must.append({"key": "doc_id", "match": {"any": doc_ids}})

        must.append({
            "should": [
                {"key": "allowed_roles", "match": {"value": "*"}},
                {"key": "allowed_roles", "match": {"value": user_role}},
            ]
        })
        return must

    async def search_dense(
        self,
        query_vector: List[float],
        tenant_id: str,
        user_role: str = "user",
        department: Optional[str] = None,
        doc_ids: Optional[List[str]] = None,
        top_k: int = 10,
    ) -> List[RetrievedChunk]:
        """Perform dense vector similarity search."""
        must = self._build_filter_conditions(tenant_id, user_role, department, doc_ids)
        payload = {
            "vector": query_vector,
            "limit": top_k,
            "with_payload": True,
            "filter": {"must": must},
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(
                    f"{self.qdrant_url}/collections/{self.collection_name}/points/search",
                    json=payload,
                )
                if res.status_code == 200:
                    hits = res.json().get("result", [])
                    results = []
                    for rank, h in enumerate(hits, start=1):
                        p = h.get("payload", {})
                        chunk = RetrievedChunk(
                            doc_id=p.get("doc_id", "unknown"),
                            chunk_index=p.get("chunk_index", 0),
                            title=p.get("title", "Tài liệu nội bộ"),
                            page_number=p.get("page_number", 1),
                            score=float(h.get("score", 0.0)),
                            text=p.get("text", ""),
                            metadata=p,
                            dense_rank=rank,
                        )
                        results.append(chunk)
                    return results
        except Exception as exc:
            logger.warning("Qdrant dense search failed: %s", exc)
        return []

    @staticmethod
    def _extract_salient_keywords(query: str) -> List[str]:
        vi_stopwords = {
            "và", "của", "cho", "ở", "tại", "trong", "là", "với", "được", "này", "đó",
            "theo", "về", "bởi", "do", "từ", "đến", "khi", "nào", "gì", "ai", "sao",
            "thế", "hãy", "thì", "mà", "cũng", "đang", "sẽ", "đã", "có", "không",
            "những", "các", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín", "mười",
            "lại", "làm", "như", "ra", "vào", "lên", "xuống", "rồi", "rất", "đâu", "bao",
            "nhiêu", "việc", "biết", "nên", "cần", "phải", "bị"
        }
        # 1. Structural identifiers and codes (e.g. 145/QĐ-UBND, NV-2024, A1)
        special_codes = re.findall(
            r"\b[A-Za-zĐđ0-9_\-]+/[A-Za-zĐđ0-9_\-\./]+\b|"
            r"\b[A-Za-zĐđ0-9]{1,8}[-_][A-Za-zĐđ0-9]{1,8}\b|"
            r"\b[A-Za-zĐđ]+\d+[A-Za-zĐđ0-9]*\b|"
            r"\b\d+[A-Za-zĐđ]+[A-Za-zĐđ0-9]*\b",
            query,
        )
        dates = re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", query)
        quoted = re.findall(r'["\'](.*?)["\']', query)

        words = [w.lower() for w in re.findall(r"[\w]+", query) if len(w) >= 2]
        filtered = [w for w in words if w not in vi_stopwords and not w.isdigit()]

        bigrams = []
        tokens = [w.lower() for w in re.findall(r"[\w]+", query)]
        for i in range(len(tokens) - 1):
            w1, w2 = tokens[i], tokens[i + 1]
            if w1.isalpha() and w2.isalpha() and w1 not in vi_stopwords and w2 not in vi_stopwords:
                bigrams.append(f"{w1} {w2}")

        combined = list(dict.fromkeys(special_codes + dates + quoted + bigrams + filtered))
        return combined[:15]

    async def search_sparse_keywords(
        self,
        query_text: str,
        tenant_id: str,
        user_role: str = "user",
        department: Optional[str] = None,
        doc_ids: Optional[List[str]] = None,
        top_k: int = 10,
    ) -> List[RetrievedChunk]:
        """Perform sparse full-text keyword search via Qdrant payload text match."""
        await self.ensure_text_index()

        keywords = self._extract_salient_keywords(query_text)
        if not keywords:
            return []

        must = self._build_filter_conditions(tenant_id, user_role, department, doc_ids)
        should_clauses = [{"key": "text", "match": {"text": kw}} for kw in keywords]

        payload = {
            "filter": {
                "must": must,
                "should": should_clauses,
            },
            "limit": max(top_k * 3, 20),
            "with_payload": True,
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(
                    f"{self.qdrant_url}/collections/{self.collection_name}/points/scroll",
                    json=payload,
                )
                if res.status_code == 200:
                    points = res.json().get("result", {}).get("points", [])
                    scored_candidates = []
                    for p_obj in points:
                        p = p_obj.get("payload", {})
                        chunk_text = p.get("text", "")
                        matched_count = sum(1 for kw in keywords if kw.lower() in chunk_text.lower())
                        coverage = matched_count / len(keywords) if keywords else 0.0
                        
                        chunk = RetrievedChunk(
                            doc_id=p.get("doc_id", "unknown"),
                            chunk_index=p.get("chunk_index", 0),
                            title=p.get("title", "Tài liệu nội bộ"),
                            page_number=p.get("page_number", 1),
                            score=min(1.0, 0.4 + (coverage * 0.6)),
                            text=chunk_text,
                            metadata=p,
                        )
                        scored_candidates.append((coverage, chunk))

                    # Sort by keyword match coverage descending
                    scored_candidates.sort(key=lambda x: x[0], reverse=True)
                    results = []
                    for rank, (_, ch) in enumerate(scored_candidates[:top_k], start=1):
                        ch.sparse_rank = rank
                        results.append(ch)
                    return results
        except Exception as exc:
            logger.warning("Qdrant keyword scroll failed: %s", exc)
        return []

    async def search(
        self,
        query_vector: List[float],
        tenant_id: str,
        query_text: Optional[str] = None,
        user_role: str = "user",
        department: Optional[str] = None,
        doc_ids: Optional[List[str]] = None,
        top_k: int = 5,
        hybrid: bool = True,
    ) -> List[RetrievedChunk]:
        """
        Enterprise Hybrid Search:
        Executes Dense Vector Search + Sparse Keyword Search in parallel,
        then merges and balances ranks using Reciprocal Rank Fusion (RRF).
        """
        fetch_k = max(top_k * 3, 10)

        # 1. Dense search
        dense_results = await self.search_dense(
            query_vector=query_vector,
            tenant_id=tenant_id,
            user_role=user_role,
            department=department,
            doc_ids=doc_ids,
            top_k=fetch_k,
        )

        if not hybrid or not query_text:
            return dense_results[:fetch_k]

        # 2. Sparse keyword search
        sparse_results = await self.search_sparse_keywords(
            query_text=query_text,
            tenant_id=tenant_id,
            user_role=user_role,
            department=department,
            doc_ids=doc_ids,
            top_k=fetch_k,
        )

        # 3. Reciprocal Rank Fusion (RRF with k=60)
        rrf_k = 60.0
        chunks_map: Dict[str, RetrievedChunk] = {}

        for rank, c in enumerate(dense_results, start=1):
            key = f"{c.doc_id}_{c.chunk_index}"
            c.dense_rank = rank
            c.rrf_score = 1.0 / (rrf_k + rank)
            chunks_map[key] = c

        for rank, c in enumerate(sparse_results, start=1):
            key = f"{c.doc_id}_{c.chunk_index}"
            c.sparse_rank = rank
            sparse_rrf = 1.0 / (rrf_k + rank)
            if key in chunks_map:
                existing = chunks_map[key]
                existing.sparse_rank = rank
                existing.rrf_score += sparse_rrf
                existing.score = min(1.0, existing.score * 1.05)
            else:
                c.rrf_score = sparse_rrf
                chunks_map[key] = c

        combined = list(chunks_map.values())
        combined.sort(key=lambda x: (x.rrf_score, x.score), reverse=True)
        return combined[:fetch_k]
