"""
Remote Cross-Encoder Reranker adapter (BAAI/bge-reranker-v2-m3 via the `rerank-standard` alias).

Scores [query, passage] pairs on the embedding-server `/v1/rerank` endpoint (sigmoid scores in
[0, 1]) and applies the shared score-threshold / information-cliff filtering policy.

Failures raise RerankerError instead of silently re-using retrieval scores: the confidence
gate is calibrated on cross-encoder scores, and fused retrieval scores are on another scale.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from ...application.components.reranker import NeuralCrossEncoderReranker
from ...config import rag_settings
from ...domain.exceptions import RerankerError
from ...domain.ports import CandidateType, RerankerPort
from .model_registry import (
    ModelEndpointNotFoundError,
    ModelEndpointResolver,
    ModelRuntimeError,
    model_endpoint_resolver,
    post_json_with_retry,
    runtime_headers,
)

logger = logging.getLogger("aip-rag.adapter.reranker")

# Keep request bodies bounded; bge-reranker-v2-m3 truncates at reranker_max_length tokens anyway.
_MAX_PASSAGE_CHARS = 4000


class HttpCrossEncoderReranker(RerankerPort):
    def __init__(
        self,
        base_url: Optional[str] = None,
        model_alias: Optional[str] = None,
        resolver: Optional[ModelEndpointResolver] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.override_url = base_url if base_url is not None else rag_settings.reranker_base_url
        self.model_alias = model_alias or rag_settings.reranker_model_alias
        self.resolver = resolver or model_endpoint_resolver
        self.timeout = timeout or rag_settings.reranker_timeout_seconds
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(limits=httpx.Limits(max_keepalive_connections=20, max_connections=50))
        return self._client

    @staticmethod
    def _passages(candidates: List[CandidateType]) -> List[str]:
        passages = []
        for c in candidates:
            text, title = NeuralCrossEncoderReranker._extract_cand_text_title(c)
            if title and not text.startswith(f"[Tài liệu: {title}"):
                text = f"[Tài liệu: {title}]\n{text}"
            passages.append(text[:_MAX_PASSAGE_CHARS])
        return passages

    def _apply_scores(
        self,
        candidates: List[CandidateType],
        results: List[Dict[str, Any]],
        top_n: int,
        min_threshold: float,
    ) -> List[CandidateType]:
        scored: List[CandidateType] = []
        for rank, item in enumerate(sorted(results, key=lambda r: r["relevance_score"], reverse=True), start=1):
            idx = int(item["index"])
            if not 0 <= idx < len(candidates):
                raise RerankerError(f"Reranker returned out-of-range index {idx}")
            score = round(float(item["relevance_score"]), 4)
            scored.append(NeuralCrossEncoderReranker._clone_with_score(candidates[idx], score, rank=rank))
        return NeuralCrossEncoderReranker.filter_candidates(scored, top_n=top_n, min_threshold=min_threshold)

    async def arerank(
        self,
        query: str,
        candidates: List[CandidateType],
        top_n: int = 5,
        min_threshold: float = 0.75,
    ) -> List[CandidateType]:
        if not candidates:
            return []
        try:
            endpoint = await self.resolver.resolve(self.model_alias, override_url=self.override_url)
        except ModelEndpointNotFoundError as exc:
            raise RerankerError(str(exc)) from exc

        t0 = time.perf_counter()
        try:
            data = await post_json_with_retry(
                self._get_client(),
                f"{endpoint.base_url}/rerank",
                {"model": self.model_alias, "query": query, "documents": self._passages(candidates)},
                headers=runtime_headers(),
                timeout=self.timeout,
            )
        except ModelRuntimeError as exc:
            raise RerankerError(f"Reranker runtime '{self.model_alias}' at {endpoint.base_url} unavailable: {exc}") from exc

        results = data.get("results")
        if not isinstance(results, list) or len(results) != len(candidates):
            raise RerankerError("Reranker response is missing scores for some candidates")
        filtered = self._apply_scores(candidates, results, top_n, min_threshold)
        logger.info(
            "bge-reranker scored %d -> %d chunks in %.1fms (top=%.4f)",
            len(candidates),
            len(filtered),
            (time.perf_counter() - t0) * 1000,
            NeuralCrossEncoderReranker._get_item_score(filtered[0]) if filtered else 0.0,
        )
        return filtered

    def rerank(
        self,
        query: str,
        candidates: List[CandidateType],
        top_n: int = 5,
        min_threshold: float = 0.75,
    ) -> List[CandidateType]:
        """Blocking variant for scripts and offline evaluation; the API pipeline uses `arerank`."""
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.arerank(query, candidates, top_n=top_n, min_threshold=min_threshold))
        raise RuntimeError("HttpCrossEncoderReranker.rerank() called inside an event loop; await arerank() instead")

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None


def build_reranker() -> RerankerPort:
    """Composition-root factory honouring RAG_RERANKER_BACKEND."""
    if rag_settings.reranker_backend == "local":
        from ...application.components.reranker import cross_encoder_reranker

        logger.warning("Using in-process FlashRank reranker (%s); scores are not calibrated for Vietnamese", rag_settings.reranker_model)
        return cross_encoder_reranker
    return HttpCrossEncoderReranker()
