"""
Neural Cross-Encoder Re-ranker Component for AIP Enterprise RAG Solution.
Implements the Re-ranking stage according to TS. Lương Văn Thiện's architecture (Slides 85-88).
Passes [Query, Passage] pairs through a Cross-Encoder to compute joint self-attention relevance scores,
and applies score_threshold / relative drop-off filtering (Slides 59, 60, 91) to eliminate irrelevant chunks.
"""

from __future__ import annotations

from dataclasses import is_dataclass, replace
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from ...domain.ports import CandidateType, RerankerPort

logger = logging.getLogger("aip-rag.reranker")


class NeuralCrossEncoderReranker(RerankerPort):
    """Production Neural Cross-Encoder Re-ranker adhering to standard CrossEncoder retrieval architecture."""

    def __init__(self, model_name: Optional[str] = None) -> None:
        if model_name is None:
            try:
                from ...config import rag_settings
                model_name = rag_settings.reranker_model
            except Exception:
                try:
                    from solutions.rag.config import rag_settings
                    model_name = rag_settings.reranker_model
                except Exception:
                    model_name = os.getenv("RAG_RERANKER_MODEL", "ms-marco-MiniLM-L-12-v2")
        self.model_name = model_name
        self._ranker: Optional[Any] = None
        self._initialized = False

    def _get_ranker(self) -> Optional[Any]:
        if not self._initialized:
            try:
                from flashrank import Ranker
                cache_dir = os.getenv("RAG_RERANKER_CACHE_DIR", "/tmp")
                self._ranker = Ranker(model_name=self.model_name, cache_dir=cache_dir)
                logger.info("Initialized Neural Cross-Encoder Re-ranker with model '%s'", self.model_name)
            except Exception as exc:
                logger.warning("FlashRank Cross-Encoder initialization failed (%s); fallback mode enabled", exc)
                self._ranker = None
            self._initialized = True
        return self._ranker

    def warmup(self) -> None:
        """Eagerly warm up Cross-Encoder model on server startup to eliminate cold-start latency."""
        try:
            ranker = self._get_ranker()
            if ranker:
                from flashrank import RerankRequest
                req = RerankRequest(query="warmup", passages=[{"id": "0", "text": "warmup text"}])
                ranker.rerank(req)
                logger.info("Neural Cross-Encoder Re-ranker successfully warmed up.")
        except Exception as exc:
            logger.warning("Neural Cross-Encoder warmup failed: %s", exc)

    @staticmethod
    def _get_item_score(item: CandidateType) -> float:
        if isinstance(item, dict):
            return float(item.get("score", 0.0))
        return float(getattr(item, "score", 0.0))

    @staticmethod
    def _extract_cand_text_title(item: CandidateType) -> Tuple[str, str]:
        if isinstance(item, dict):
            p = item.get("payload", {})
            text = p.get("text") or item.get("text", "")
            title = str(p.get("title") or item.get("title") or "").strip()
            return text, title
        return getattr(item, "text", ""), str(getattr(item, "title", "")).strip()

    @staticmethod
    def _clone_with_score(item: CandidateType, score: float, rank: Optional[int] = None) -> CandidateType:
        if isinstance(item, dict):
            orig = item.copy()
            orig["score"] = score
            if rank is not None:
                orig["raw_rerank_score"] = score
                orig["cross_encoder_score"] = score
                orig["cross_encoder_rank"] = rank
            return orig
        elif is_dataclass(item):
            return replace(item, score=score)
        return item

    @classmethod
    def filter_candidates(
        cls,
        items: List[CandidateType],
        top_n: int = 4,
        min_threshold: float = 0.75,
        max_relative_gap: float = 0.25,
        max_step_gap: float = 0.15,
    ) -> List[CandidateType]:
        """
        Filters candidates using standard score_threshold and Information Cliff relative cutoff.
        Prunes out trailing chunks when their relevance plunges below threshold or falls off an information cliff.
        Always preserves viable candidates above safety floor (0.30) to support Grey-Zone LLM Verification.
        """
        if not items:
            return []

        sorted_items = sorted(items, key=lambda x: cls._get_item_score(x), reverse=True)
        top_score = cls._get_item_score(sorted_items[0])

        if min_threshold <= 0.0:
            return sorted_items[:top_n]

        # Candidate safety floor for non-refusal routing (Three-Zone: preserves Grey-Zone candidates >= 0.20)
        safety_floor = min(min_threshold, 0.20)
        if top_score < safety_floor:
            return []

        filtered: List[CandidateType] = [sorted_items[0]]
        prev_score = top_score

        for item in sorted_items[1:top_n]:
            s = cls._get_item_score(item)
            if s < safety_floor:
                break

            # 1. Information Cliff: cumulative gap from Top-1
            effective_max_gap = 0.12 if top_score >= 0.95 else (0.20 if top_score >= 0.90 else (0.25 if top_score >= 0.75 else max_relative_gap))
            if (top_score - s) > effective_max_gap:
                logger.info(
                    "Information Cliff cutoff: pruned candidate (score=%.4f, gap=%.4f > %.4f from top=%.4f)",
                    s, top_score - s, effective_max_gap, top_score
                )
                break

            # 2. Information Cliff: steep plunge between adjacent ranked items
            if (prev_score - s) > max_step_gap and len(filtered) >= 2:
                logger.info(
                    "Information Cliff step plunge: pruned candidate (score=%.4f, plunge=%.4f > %.4f from prev=%.4f)",
                    s, prev_score - s, max_step_gap, prev_score
                )
                break

            # 3. Minimum relative ratio check
            if (s / top_score if top_score > 0 else 0) < 0.60:
                break

            filtered.append(item)
            prev_score = s
        return filtered

    # Backwards-compatibility alias
    filter_elbow_dropoff = filter_candidates

    def rerank(
        self,
        query: str,
        candidates: List[CandidateType],
        top_n: int = 4,
        min_threshold: float = 0.75,
    ) -> List[CandidateType]:
        """
        Rerank retrieved candidates (e.g. Top-20 from Hybrid Search) using Cross-Encoder attention,
        returning top_n most contextually relevant chunks with genuine raw model scores.
        """
        if not candidates:
            return []

        ranker = self._get_ranker()
        if ranker is None:
            fallback_candidates = [
                self._clone_with_score(c, round(self._get_item_score(c), 4))
                for c in candidates
            ]
            return self.filter_candidates(fallback_candidates, top_n=top_n, min_threshold=min_threshold)

        start_t = time.time()
        passages: List[Dict[str, Any]] = []
        for idx, c in enumerate(candidates):
            text, cand_title = self._extract_cand_text_title(c)
            if cand_title and not text.startswith(f"[Tài liệu: {cand_title}"):
                passage_text = f"[Tài liệu: {cand_title}]\n{text}"
            else:
                passage_text = text
            passages.append({"id": idx, "text": passage_text})

        try:
            from flashrank import RerankRequest
            req = RerankRequest(query=query, passages=passages)
            ranked_passages = ranker.rerank(req)

            scored_results: List[CandidateType] = []
            for rank, rp in enumerate(ranked_passages, start=1):
                idx = rp["id"]
                raw_rerank_score = round(float(rp.get("score", 0.0)), 4)
                scored = self._clone_with_score(candidates[idx], raw_rerank_score, rank=rank)
                scored_results.append(scored)

            filtered_results = self.filter_candidates(scored_results, top_n=top_n, min_threshold=min_threshold)

            latency_ms = (time.time() - start_t) * 1000
            top_score = self._get_item_score(filtered_results[0]) if filtered_results else 0.0
            logger.info(
                "Neural Cross-Encoder reranked %d -> %d chunks in %.2fms (top score=%.4f)",
                len(candidates),
                len(filtered_results),
                latency_ms,
                top_score,
            )
            return filtered_results

        except Exception as exc:
            logger.warning("Neural Cross-Encoder reranking encountered error: %s; falling back", exc)
            fallback_list = [
                self._clone_with_score(c, round(self._get_item_score(c), 4))
                for c in candidates
            ]
            return self.filter_candidates(fallback_list, top_n=top_n, min_threshold=min_threshold)


cross_encoder_reranker = NeuralCrossEncoderReranker()
