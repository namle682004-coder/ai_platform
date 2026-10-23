"""
Qdrant Vector Store Adapter for AIP Enterprise RAG Solution.
Implements domain VectorStorePort with multi-tenant payload schemas and ACL filtering.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import logging
import math
import re
import time
import uuid
from collections import Counter
from typing import Any, Dict, List, Optional

import httpx
from ...config import rag_settings
from ...domain.entities import DocumentChunk, normalize_iso_date
from ...domain.exceptions import VectorStoreError
from ...domain.ports import VectorStorePort

logger = logging.getLogger("aip-rag.adapter.qdrant")

# Common 1-letter Vietnamese words that form meaningful compound phrases (e.g. "y tế", "ý kiến")
SINGLE_LETTER_VI_WORDS = {"y", "ở", "ý", "ổ", "ả", "ạ", "e"}

_KEYWORD_INDEX_FIELDS = (
    "tenant_id",
    "doc_id",
    "parent_id",
    "department",
    "content_type",
    "heading_path",
    "file_type",
    "strategy",
    "allowed_roles",
    "effective_status",
)
_DATETIME_INDEX_FIELDS = ("effective_from", "effective_to", "effective_date", "expiry_date")

_TOKEN_RE = re.compile(r"\b\w+\b")
_DECIMAL_RE = re.compile(r"\b\d+(?:\.\d+)+\b")


def _sparse_terms(text: str) -> List[str]:
    """
    Sparse vocabulary for Vietnamese: syllables plus adjacent-syllable bigrams.

    Vietnamese words are mostly 2-syllable compounds ("bảo hiểm", "hóa đơn"); indexing the
    bigram as its own term lets exact phrases outrank documents that merely contain both
    syllables apart. Decimal section numbers ("2.1.3") are kept whole.
    """
    lowered = text.lower()
    tokens = [w for w in _TOKEN_RE.findall(lowered) if len(w) >= 2 or w in SINGLE_LETTER_VI_WORDS]
    # Single-letter words ("y" in "y tế") only carry meaning inside a compound.
    unigrams = [w for w in tokens if len(w) >= 2]
    bigrams = [
        f"{a} {b}" for a, b in zip(tokens, tokens[1:]) if a != b and not (a.isdigit() and b.isdigit())
    ]
    return _DECIMAL_RE.findall(lowered) + unigrams + bigrams


def _term_index(term: str) -> int:
    return int(hashlib.md5(term.encode("utf-8")).hexdigest()[:7], 16)



class QdrantVectorStoreAdapter(VectorStorePort):
    """Production Qdrant adapter with connection pooling and schema management."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        collection_name: Optional[str] = None,
        dim: Optional[int] = None,
    ) -> None:
        self.base_url = (base_url or rag_settings.qdrant_url).rstrip("/")
        self.collection_name = collection_name or rag_settings.collection_name
        self.dim = dim or rag_settings.embedding_dim
        self._initialized = False
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Reuse persistent connection pool across requests to avoid socket exhaustion."""
        if self._http_client is None or self._http_client.is_closed:
            limits = httpx.Limits(max_keepalive_connections=50, max_connections=100)
            self._http_client = httpx.AsyncClient(limits=limits, timeout=15.0)
        return self._http_client

    async def ensure_collection(self) -> None:
        if self._initialized:
            return

        try:
            client = await self._get_client()
            coll_url = f"{self.base_url}/collections/{self.collection_name}"
            res = await client.get(coll_url)
            payload_schema: Dict[str, Any] = {}
            if res.status_code == 404:
                logger.info("Initializing collection '%s' in Qdrant...", self.collection_name)
                create_res = await client.put(
                    coll_url,
                    json={
                        "vectors": {"": {"size": self.dim, "distance": "Cosine"}},
                        # IDF is applied by Qdrant at query time, so stored values only carry BM25 TF saturation.
                        "sparse_vectors": {"text-sparse": {"modifier": "idf"}},
                    },
                )
                create_res.raise_for_status()
            else:
                res.raise_for_status()
                info = res.json().get("result", {})
                payload_schema = info.get("payload_schema", {}) or {}
                sparse_cfg = (info.get("config", {}).get("params", {}).get("sparse_vectors") or {}).get("text-sparse")
                if sparse_cfg is not None and sparse_cfg.get("modifier") != "idf":
                    # Collections created before the IDF fix: enable it in place (no re-index needed).
                    patch = await client.patch(coll_url, json={"sparse_vectors": {"text-sparse": {"modifier": "idf"}}})
                    patch.raise_for_status()
                    logger.info("Enabled IDF modifier on sparse vector 'text-sparse' of '%s'", self.collection_name)

            index_url = f"{coll_url}/index?wait=true"
            for field_name in _KEYWORD_INDEX_FIELDS:
                if field_name not in payload_schema:
                    await client.put(index_url, json={"field_name": field_name, "field_schema": "keyword"})
            # Temporal fields are compared with range filters, so they need a datetime index.
            for field_name in _DATETIME_INDEX_FIELDS:
                current = (payload_schema.get(field_name) or {}).get("data_type")
                if current == "datetime":
                    continue
                if current:
                    await client.delete(f"{coll_url}/index/{field_name}?wait=true")
                await client.put(index_url, json={"field_name": field_name, "field_schema": "datetime"})
            if "chunk_index" not in payload_schema:
                await client.put(index_url, json={"field_name": "chunk_index", "field_schema": "integer"})

            # Ensure full-text index on 'text' field for BM25 / keyword search
            await client.put(
                f"{self.base_url}/collections/{self.collection_name}/index",
                json={
                    "field_name": "text",
                    "field_schema": {
                        "type": "text",
                        "tokenizer": "word",
                        "min_token_len": 2,
                        "max_token_len": 40,
                        "lowercase": True,
                    },
                },
            )

            self._initialized = True
        except Exception as exc:
            logger.warning("Could not initialize Qdrant collection '%s': %s", self.collection_name, exc)

    async def upsert_chunks(
        self,
        chunks: List[DocumentChunk],
        vectors: List[List[float]],
        tenant_id: str,
        title: str,
        filename: Optional[str] = None,
        file_type: Optional[str] = None,
        department: Optional[str] = None,
        allowed_roles: Optional[List[str]] = None,
        batch_size: int = 100,
    ) -> int:
        if len(chunks) != len(vectors):
            raise VectorStoreError("Chunk count does not match vector count")

        await self.ensure_collection()
        roles = allowed_roles or ["*"]
        now = int(time.time())

        points: List[Dict[str, Any]] = []
        for c, v in zip(chunks, vectors, strict=True):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{c.doc_id}_{c.chunk_index}"))
            heading = c.metadata.get("heading") or c.metadata.get("heading_path") or ""
            heading_path = c.metadata.get("heading_path") or c.metadata.get("heading") or ""
            parent_id = c.metadata.get("parent_id", "")
            content_type = c.metadata.get("content_type", "text")
            strategy = c.metadata.get("strategy", "hybrid_structural_semantic")
            char_length = c.metadata.get("char_length", len(c.text))
            token_count = c.metadata.get("token_count", max(1, len(c.text) // 4))

            payload = {
                "chunk_id": getattr(c, "chunk_id", f"{c.doc_id}_{c.chunk_index}"),
                "doc_id": c.doc_id,
                "parent_id": parent_id,
                "tenant_id": tenant_id,
                "chunk_index": c.chunk_index,
                "title": title,
                "filename": filename or title,
                "file_type": file_type or "text",
                "department": department or "",
                "allowed_roles": roles,
                "page_number": c.page_number,
                "source_page": c.metadata.get("source_page", c.page_number),
                "heading": heading,
                "heading_path": heading_path,
                "text": c.text,
                "content_type": content_type,
                "strategy": strategy,
                "char_length": char_length,
                "token_count": token_count,
                "created_at": now,
                **{
                    k: val
                    for k, val in c.metadata.items()
                    if k not in {
                        "source_page",
                        "heading",
                        "heading_path",
                        "parent_id",
                        "content_type",
                        "strategy",
                        "char_length",
                        "token_count",
                    }
                },
            }

            search_text = c.metadata.get("search_text") or c.text
            sparse_vec = self.compute_sparse_vector(search_text)
            points.append({
                "id": point_id,
                "vector": {
                    "": v,
                    "text-sparse": sparse_vec,
                },
                "payload": payload,
            })

        upserted_count = 0
        try:
            client = await self._get_client()
            for i in range(0, len(points), batch_size):
                batch = points[i : i + batch_size]
                res = await client.put(
                    f"{self.base_url}/collections/{self.collection_name}/points?wait=true",
                    json={"points": batch},
                )
                if res.status_code == 400 and ("text-sparse" in res.text or "Not existing vector name" in res.text):
                    legacy_batch = [
                        {"id": p["id"], "vector": p["vector"][""], "payload": p["payload"]}
                        for p in batch
                    ]
                    res = await client.put(
                        f"{self.base_url}/collections/{self.collection_name}/points?wait=true",
                        json={"points": legacy_batch},
                    )
                res.raise_for_status()
                upserted_count += len(batch)
        except Exception as exc:
            logger.error("Failed to upsert points to Qdrant: %s", exc)
            raise VectorStoreError(f"Qdrant upsert failed: {exc}") from exc

        return upserted_count

    @staticmethod
    def _build_filter_conditions(
        tenant_id: str,
        user_role: str = "user",
        department: Optional[str] = None,
        doc_ids: Optional[List[str]] = None,
        content_type: Optional[str] = None,
        heading_path: Optional[str] = None,
        effective_status: Optional[str] = "ACTIVE",
        as_of_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        # Tenancy isolation: match current workspace tenant + shared global knowledge base
        clean_tid = (tenant_id or "global").strip()
        if clean_tid.lower() in ("global", "proj_default", "system", "*"):
            tenant_variants = ["global", "proj_default"]
        else:
            tenant_variants = list(set([clean_tid, clean_tid.upper(), clean_tid.lower(), "global", "proj_default"]))

        must_conditions: List[Dict[str, Any]] = [
            {"key": "tenant_id", "match": {"any": tenant_variants}}
        ]

        if department:
            must_conditions.append({"key": "department", "match": {"value": department}})

        if doc_ids:
            must_conditions.append({"key": "doc_id", "match": {"any": doc_ids}})

        if content_type:
            must_conditions.append({"key": "content_type", "match": {"value": content_type}})

        if heading_path:
            must_conditions.append({"key": "heading_path", "match": {"value": heading_path}})

        # Role ACL check: allowed_roles must match '*' or user_role
        must_conditions.append({
            "should": [
                {"key": "allowed_roles", "match": {"value": "*"}},
                {"key": "allowed_roles", "match": {"value": user_role}},
            ]
        })

        # FR-RET-06: Temporal compliance filter for retrospective auditing vs current validity
        # Qdrant Missing Field Behavior Note (Audit Item 6 - Issue 3):
        # In Qdrant, if a point lacks a field (e.g. effective_from or expiry_date is null/absent),
        # range conditions on that field evaluate to FALSE. Inside a 'must_not' clause, FALSE means
        # the exclusion condition is NOT met, so the point PASSES THROUGH. This is by design:
        # timeless documents (e.g. evergreen corporate guidelines, glossaries, general FAQs)
        # without explicit expiration dates are preserved in both current and retrospective searches.
        # Request DTOs validate the format, so a ValueError here is a programming error.
        norm_as_of_date = normalize_iso_date(as_of_date)

        if norm_as_of_date:
            # Retrospective auditing (Audit Item 6 - Issue 1):
            # Evaluate document validity strictly as of `as_of_date`.
            # Do NOT exclude documents whose current status is EXPIRED or SUPERSEDED, since they may have been
            # fully active and valid on the historical as_of_date.
            # Only exclude documents that were never in force (e.g. DRAFT, CANCELLED, VOID) or fell outside
            # the historical validity window.
            must_conditions.append({
                "must_not": [
                    {"key": "effective_status", "match": {"any": ["DRAFT", "PENDING", "REJECTED", "CANCELLED", "VOID"]}},
                    {"key": "effective_from", "range": {"gt": norm_as_of_date}},
                    {"key": "effective_date", "range": {"gt": norm_as_of_date}},
                    {"key": "effective_to", "range": {"lt": norm_as_of_date}},
                    {"key": "expiry_date", "range": {"lt": norm_as_of_date}},
                ]
            })
            if effective_status and effective_status != "ACTIVE":
                must_conditions.append({"key": "effective_status", "match": {"value": effective_status}})
        elif effective_status == "ACTIVE":
            # Current active document search (Audit Item 6 - Issue 2):
            # Exclude expired/deprecated statuses, past expiry dates, AND future effective dates (effective_from > now).
            today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            must_conditions.append({
                "must_not": [
                    {"key": "effective_status", "match": {"any": ["EXPIRED", "HET_HIEU_LUC", "ARCHIVED", "DEPRECATED", "SUPERSEDED", "DRAFT", "CANCELLED", "VOID"]}},
                    {"key": "effective_from", "range": {"gt": today_iso}},
                    {"key": "effective_date", "range": {"gt": today_iso}},
                    {"key": "effective_to", "range": {"lt": today_iso}},
                    {"key": "expiry_date", "range": {"lt": today_iso}},
                ]
            })
        elif effective_status:
            # Explicit non-default status query (e.g. explicitly requesting EXPIRED or DRAFT)
            must_conditions.append({"key": "effective_status", "match": {"value": effective_status}})

        return must_conditions

    @staticmethod
    def _extract_salient_keywords(query: str) -> List[str]:
        # 1. Domain-agnostic structural identifiers, decimal subsection numbers, document/decision numbers, employee IDs (e.g. 2.1, 145/QĐ-UBND, NV-2024, A1)
        special_codes = re.findall(
            r"\b\d+(?:\.\d+)+\b|"
            r"\b[A-Za-zĐđ0-9_\-]+/[A-Za-zĐđ0-9_\-\./]+\b|"
            r"\b[A-Za-zĐđ0-9]{1,8}[-_][A-Za-zĐđ0-9]{1,8}\b|"
            r"\b[A-Za-zĐđ]+\d+[A-Za-zĐđ0-9]*\b|"
            r"\b\d+[A-Za-zĐđ]+[A-Za-zĐđ0-9]*\b",
            query,
        )
        # 2. Universal dates (e.g. 15/04/2024, 2024-10-12)
        dates = re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", query)

        # 3. Quoted terms (explicit user exact phrase)
        quoted = re.findall(r'["\'](.*?)["\']', query)

        # 4. Content words (ignoring pure numbers)
        words = [w.lower() for w in re.findall(r"[\w]+", query) if len(w) >= 2]
        filtered_words = [w for w in words if not w.isdigit()]

        # 5. Natural consecutive bigrams from adjacent tokens (domain-agnostic, preserving word-number phrases)
        bigrams = []
        tokens = [w.lower() for w in re.findall(r"\b\w+\b", query)]
        for i in range(len(tokens) - 1):
            w1, w2 = tokens[i], tokens[i + 1]
            if not (w1.isdigit() and w2.isdigit()):
                bigrams.append(f"{w1} {w2}")

        combined = list(dict.fromkeys(special_codes + dates + quoted + bigrams + filtered_words))
        return combined[:20]

    @staticmethod
    def compute_sparse_vector(
        text: str,
        k1: Optional[float] = None,
        b: Optional[float] = None,
        avg_len: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Document-side BM25 sparse vector for Qdrant native sparse search.

        Values are the BM25 term-frequency saturation component; the IDF component is applied
        by Qdrant at query time (`modifier: idf`), so together they score as Okapi BM25.
        Terms are hashed to 28-bit indices, so the vocabulary needs no central dictionary.
        """
        k1_val = k1 if k1 is not None else float(rag_settings.bm25_k1)
        b_val = b if b is not None else float(rag_settings.bm25_b)
        avg_len_val = avg_len if avg_len is not None else float(rag_settings.sparse_avg_doc_len)

        tokens = _sparse_terms(text)
        if not tokens:
            return {"indices": [], "values": []}
        doc_len = len(tokens)
        weights: Dict[int, float] = {}
        for term, count in Counter(tokens).items():
            tf_norm = (count * (k1_val + 1.0)) / (count + k1_val * (1.0 - b_val + b_val * (doc_len / avg_len_val)))
            idx = _term_index(term)
            weights[idx] = max(weights.get(idx, 0.0), round(tf_norm, 4))  # hash collisions keep the stronger term
        return {"indices": list(weights.keys()), "values": list(weights.values())}

    @staticmethod
    def compute_sparse_query_vector(text: str) -> Dict[str, Any]:
        """Query-side sparse vector: each distinct term weighs 1.0 (BM25 query terms are binary)."""
        indices = sorted({_term_index(term) for term in _sparse_terms(text)})
        return {"indices": indices, "values": [1.0] * len(indices)}

    @staticmethod
    def _compute_bm25_scores(
        query_terms: List[str],
        candidates: List[Dict[str, Any]],
        k1: Optional[float] = None,
        b: Optional[float] = None,
    ) -> List[float]:
        if not query_terms or not candidates:
            return [0.0] * len(candidates)

        k1_val = k1 if k1 is not None else float(getattr(rag_settings, "bm25_k1", 1.5))
        b_val = b if b is not None else float(getattr(rag_settings, "bm25_b", 0.75))

        def tokenize(text: str) -> List[str]:
            return [w.lower() for w in re.findall(r"[\w]+", text) if len(w) >= 2]

        num_docs = len(candidates)
        raw_doc_texts = [c.get("payload", {}).get("text", "").lower() for c in candidates]
        tokenized_docs = [tokenize(t) for t in raw_doc_texts]
        tokenized_sets = [set(doc) for doc in tokenized_docs]
        doc_lengths = [len(doc) for doc in tokenized_docs]
        avg_doc_len = (sum(doc_lengths) / num_docs) if num_docs > 0 else 1.0

        # Exact token matching for words, phrase matching for bigrams
        df: Dict[str, int] = {}
        for term in query_terms:
            t_clean = term.lower().strip()
            if " " in t_clean:
                # Multi-word phrase match in raw text
                df[t_clean] = sum(1 for raw_t in raw_doc_texts if t_clean in raw_t)
            else:
                # Exact single-word match
                df[t_clean] = sum(1 for doc_set in tokenized_sets if t_clean in doc_set)

        idf: Dict[str, float] = {}
        for term, freq in df.items():
            # Standard Okapi BM25 non-negative smoothed IDF
            val = math.log((num_docs - freq + 0.5) / (freq + 0.5) + 1.0)
            idf[term] = max(0.1, val)

        raw_scores: List[float] = []
        for idx, (doc, doc_len) in enumerate(zip(tokenized_docs, doc_lengths)):
            raw_text = raw_doc_texts[idx]
            score = 0.0
            term_counts: Dict[str, int] = {}
            for t in doc:
                term_counts[t] = term_counts.get(t, 0) + 1

            for term in query_terms:
                t_clean = term.lower().strip()
                if " " in t_clean:
                    tf = raw_text.count(t_clean)
                else:
                    tf = term_counts.get(t_clean, 0)

                if tf > 0:
                    denom = tf + k1_val * (1.0 - b_val + b_val * (doc_len / avg_doc_len))
                    score += idf.get(t_clean, 0.0) * ((tf * (k1_val + 1.0)) / max(0.0001, denom))

            raw_scores.append(score)

        max_s = max(raw_scores) if raw_scores else 0.0
        if max_s > 0:
            return [s / max_s for s in raw_scores]
        return [0.0] * len(candidates)

    async def search_dense(
        self,
        query_vector: List[float],
        tenant_id: str,
        user_role: str = "user",
        department: Optional[str] = None,
        doc_ids: Optional[List[str]] = None,
        content_type: Optional[str] = None,
        heading_path: Optional[str] = None,
        top_k: int = 15,
        effective_status: Optional[str] = "ACTIVE",
        as_of_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Perform dense vector similarity search via Cosine distance."""
        must_conditions = self._build_filter_conditions(
            tenant_id,
            user_role,
            department,
            doc_ids,
            content_type=content_type,
            heading_path=heading_path,
            effective_status=effective_status,
            as_of_date=as_of_date,
        )
        # Dual-schema resilience: named dense vector "" for native dual-vector collections, fallback to unnamed
        search_payload = {
            "vector": {
                "name": "",
                "vector": query_vector,
            },
            "limit": top_k,
            "with_payload": True,
            "filter": {"must": must_conditions},
        }

        search_url = f"{self.base_url}/collections/{self.collection_name}/points/search"
        try:
            client = await self._get_client()
            res = await client.post(search_url, json=search_payload)
            if res.status_code == 400 and "Not existing vector name" in res.text:
                # Legacy collections with a single unnamed vector
                res = await client.post(
                    search_url,
                    json={
                        "vector": query_vector,
                        "limit": top_k,
                        "with_payload": True,
                        "filter": {"must": must_conditions},
                    },
                )
        except httpx.HTTPError as exc:
            raise VectorStoreError(f"Qdrant dense search unreachable: {exc}") from exc

        if res.status_code == 404:
            # Collection not created yet (nothing ingested): a genuine empty result.
            return []
        if res.status_code != 200:
            # Surfacing the failure keeps an outage from looking like "no relevant documents".
            raise VectorStoreError(f"Qdrant dense search failed: HTTP {res.status_code}: {res.text[:300]}")

        return [
            {
                "id": h.get("id"),
                "score": float(h.get("score", 0.0)),
                "payload": h.get("payload", {}),
                "dense_rank": rank,
                "sparse_rank": None,
            }
            for rank, h in enumerate(res.json().get("result", []), start=1)
        ]

    async def search_sparse_keywords(
        self,
        query_text: str,
        tenant_id: str,
        user_role: str = "user",
        department: Optional[str] = None,
        doc_ids: Optional[List[str]] = None,
        content_type: Optional[str] = None,
        heading_path: Optional[str] = None,
        top_k: int = 15,
        effective_status: Optional[str] = "ACTIVE",
        as_of_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Perform sparse keyword retrieval and BM25 ranking.
        Tier 1: Qdrant native on-disk sparse vector search ('text-sparse'),
        scaling to millions of documents on disk without in-memory candidate scroll.
        Tier 2: Resilient fallback to payload text-match scroll for legacy collections.
        """
        keywords = self._extract_salient_keywords(query_text)
        if not keywords:
            return []

        must_conditions = self._build_filter_conditions(
            tenant_id,
            user_role,
            department,
            doc_ids,
            content_type=content_type,
            heading_path=heading_path,
            effective_status=effective_status,
            as_of_date=as_of_date,
        )
        # 1. Native Qdrant On-Disk Sparse Vector Search (Scales to Millions of Documents)
        query_sparse = self.compute_sparse_query_vector(query_text)
        if query_sparse["indices"]:
            sparse_search_payload = {
                "vector": {
                    "name": "text-sparse",
                    "vector": query_sparse,
                },
                "limit": top_k,
                "with_payload": True,
                "filter": {"must": must_conditions},
            }
            try:
                client = await self._get_client()
                res = await client.post(
                    f"{self.base_url}/collections/{self.collection_name}/points/search",
                    json=sparse_search_payload,
                )
                if res.status_code == 200:
                    hits = res.json().get("result", [])
                    if hits:
                        results = []
                        for rank, h in enumerate(hits, start=1):
                            p = h.get("payload", {})
                            raw_sparse_score = float(h.get("score", 0.0))
                            norm_sparse = min(1.0, raw_sparse_score / 10.0) if raw_sparse_score > 0 else 0.0

                            results.append({
                                "id": h.get("id"),
                                "score": round(norm_sparse, 4),
                                "payload": p,
                                "bm25_score": round(norm_sparse, 4),
                                "sparse_rank": rank,
                                "dense_rank": None,
                            })
                        return results
                elif res.status_code != 404:
                    logger.warning("Native sparse search returned HTTP %s; using text-index fallback", res.status_code)
            except httpx.HTTPError as exc:
                logger.warning("Native sparse search unavailable (%s); using text-index fallback", exc)

        # 2. Resilient Fallback: Payload Text Scroll & Calibration (for legacy collections)
        should_clauses = [{"key": "text", "match": {"text": kw}} for kw in keywords]
        scroll_payload = {
            "filter": {
                "must": must_conditions,
                "should": should_clauses,
            },
            "limit": max(top_k * 3, 25),
            "with_payload": True,
        }

        try:
            client = await self._get_client()
            res = await client.post(
                f"{self.base_url}/collections/{self.collection_name}/points/scroll",
                json=scroll_payload,
            )
            if res.status_code == 200:
                points = res.json().get("result", {}).get("points", [])
                if not points:
                    return []

                bm25_scores = self._compute_bm25_scores(keywords, points)

                scored_candidates = []
                for p_obj, bm25_s in zip(points, bm25_scores):
                    p = p_obj.get("payload", {})
                    scored_candidates.append({
                        "id": p_obj.get("id"),
                        "score": round(bm25_s, 4),
                        "payload": p,
                        "bm25_score": round(bm25_s, 4),
                    })

                scored_candidates.sort(key=lambda x: x["score"], reverse=True)
                results = []
                for rank, item in enumerate(scored_candidates[:top_k], start=1):
                    item["sparse_rank"] = rank
                    item["dense_rank"] = None
                    results.append(item)
                return results
        except Exception as exc:
            logger.warning("Qdrant sparse keyword scroll failed: %s", exc)

        return []

    async def search(
        self,
        query_vector: List[float],
        tenant_id: str,
        query_text: Optional[str] = None,
        user_role: str = "user",
        department: Optional[str] = None,
        doc_ids: Optional[List[str]] = None,
        content_type: Optional[str] = None,
        heading_path: Optional[str] = None,
        top_k: int = 5,
        hybrid: bool = True,
        effective_status: Optional[str] = "ACTIVE",
        as_of_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Enterprise Hybrid Search (FEAT-ENG-04):
        Executes Dense Vector Search (Cosine similarity) and Sparse Keyword Search (BM25 + Qdrant Text Index)
        in parallel, then fuses via Reciprocal Rank Fusion (RRF):
            RRF_Score(d) = sum_{m in {Dense, Sparse}} 1 / (k + Rank_m(d))

        Note: BRD specifies linear convex S = α·S_dense + (1-α)·S_sparse (α=0.6).
        RRF is used instead because it is score-distribution-agnostic — dense cosine [0,1]
        and BM25 unbounded scores do not need calibration, and RRF consistently outperforms
        linear interpolation on heterogeneous retrieval signals (Cormack et al., 2009).
        """
        fetch_k = max(top_k * 5, 30)

        # 1 & 2. Concurrent Dense Semantic & Sparse Keyword Retrieval (FR-RET-01 / 50% latency reduction)
        if hybrid and query_text and query_text.strip():
            dense_coro = self.search_dense(
                query_vector=query_vector,
                tenant_id=tenant_id,
                user_role=user_role,
                department=department,
                doc_ids=doc_ids,
                content_type=content_type,
                heading_path=heading_path,
                top_k=fetch_k,
                effective_status=effective_status,
                as_of_date=as_of_date,
            )
            sparse_coro = self.search_sparse_keywords(
                query_text=query_text,
                tenant_id=tenant_id,
                user_role=user_role,
                department=department,
                doc_ids=doc_ids,
                content_type=content_type,
                heading_path=heading_path,
                top_k=fetch_k,
                effective_status=effective_status,
                as_of_date=as_of_date,
            )
            dense_results, sparse_results = await asyncio.gather(dense_coro, sparse_coro)
        else:
            dense_results = await self.search_dense(
                query_vector=query_vector,
                tenant_id=tenant_id,
                user_role=user_role,
                department=department,
                doc_ids=doc_ids,
                content_type=content_type,
                heading_path=heading_path,
                top_k=fetch_k,
                effective_status=effective_status,
                as_of_date=as_of_date,
            )
            sparse_results = []

        if not sparse_results:
            return dense_results[:top_k]

        # 3. Standard Reciprocal Rank Fusion (RRF with configurable k, Cormack et al.)
        rrf_k = float(getattr(rag_settings, "rrf_k", 60))
        chunks_map: Dict[str, Dict[str, Any]] = {}

        for rank, d in enumerate(dense_results, start=1):
            p = d.get("payload", {})
            key = str(d.get("id") or f"{p.get('doc_id')}_{p.get('chunk_index')}")
            d["dense_rank"] = rank
            d["rrf_score"] = 1.0 / (rrf_k + rank)
            chunks_map[key] = d

        for rank, s in enumerate(sparse_results, start=1):
            p = s.get("payload", {})
            key = str(s.get("id") or f"{p.get('doc_id')}_{p.get('chunk_index')}")
            sparse_rrf = 1.0 / (rrf_k + rank)
            s["sparse_rank"] = rank

            if key in chunks_map:
                existing = chunks_map[key]
                existing["sparse_rank"] = rank
                existing["rrf_score"] += sparse_rrf
                existing["score"] = max(existing["score"], s["score"])
            else:
                s["rrf_score"] = sparse_rrf
                chunks_map[key] = s

        combined = list(chunks_map.values())
        combined.sort(key=lambda x: (x.get("rrf_score", 0.0), x.get("score", 0.0)), reverse=True)
        return combined[:top_k]

    async def delete_stale_chunks(self, doc_id: str, tenant_id: str, keep_count: int) -> bool:
        """
        Delete points of `doc_id` with chunk_index >= keep_count.

        Point ids are uuid5(doc_id, chunk_index), so re-indexing overwrites chunks in place;
        only the tail left over from a longer previous version must be removed. The document
        therefore stays searchable during re-indexing, and a failed upsert leaves the previous
        version intact instead of an empty index.
        """
        if keep_count <= 0:
            return await self.delete_by_doc_id(doc_id, tenant_id)
        tenant_variants = list({tenant_id, tenant_id.upper(), tenant_id.lower()})
        try:
            client = await self._get_client()
            res = await client.post(
                f"{self.base_url}/collections/{self.collection_name}/points/delete?wait=true",
                json={
                    "filter": {
                        "must": [
                            {"key": "doc_id", "match": {"value": doc_id}},
                            {"key": "tenant_id", "match": {"any": tenant_variants}},
                            {"key": "chunk_index", "range": {"gte": keep_count}},
                        ]
                    }
                },
            )
        except httpx.HTTPError as exc:
            raise VectorStoreError(f"Qdrant stale-chunk delete failed for doc_id={doc_id}: {exc}") from exc
        if res.status_code not in (200, 404):
            raise VectorStoreError(f"Qdrant stale-chunk delete failed: HTTP {res.status_code}: {res.text[:300]}")
        return True

    async def delete_by_doc_id(self, doc_id: str, tenant_id: str) -> bool:
        tenant_variants = list(set([tenant_id, tenant_id.upper(), tenant_id.lower()]))
        try:
            client = await self._get_client()
            res = await client.post(
                f"{self.base_url}/collections/{self.collection_name}/points/delete",
                json={
                    "filter": {
                        "must": [
                            {"key": "doc_id", "match": {"value": doc_id}},
                            {"key": "tenant_id", "match": {"any": tenant_variants}},
                        ]
                    }
                },
            )
            return res.status_code == 200
        except Exception as exc:
            logger.warning("Failed to delete points from Qdrant for doc_id=%s: %s", doc_id, exc)
            return False
