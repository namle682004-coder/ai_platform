"""
Enterprise RAG Chat Orchestration Use Case.
Coordinates Query Reformulation, Intent Routing, Dense/Hybrid Retrieval,
Reranking & Grounding Guardrails, LLM Generation, Citation Linking, and Session Persistence.
"""

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from ...domain.exceptions import EmbeddingError, LLMGenerationError, RerankerError, VectorStoreError
from ...domain.entities import (
    DEFAULT_TENANT_ID,
    QueryIntent,
    normalize_tenant_id,
)
from ...domain.ports import (
    CachePort,
    EmbeddingPort,
    LLMPort,
    NullCacheAdapter,
    NullObservabilityAdapter,
    ObservabilityPort,
    RerankerPort,
    SessionRepositoryPort,
    VectorStorePort,
)
from ..components.hyde_generator import HyDEResult, hyde_generator
from ..components.intent_classifier import (
    RoutingDecision,
    intent_classifier,
)
from ..components.prompt_builder import (
    CHITCHAT_SYSTEM_PROMPT,
    REFUSAL_MESSAGE,
    prompt_builder,
)
from ..components.query_decomposer import DecomposedQuery, query_decomposer
from ..components.query_rewriter import RewrittenQuery, query_rewriter
from ..components.reranker import cross_encoder_reranker
from ..dtos import (
    CONFIDENCE_GATE_MIN_THRESHOLD,
    ClarificationDTO,
    RagChatRequestDTO,
    RagChatResponseDTO,
    RagCitationDTO,
)

logger = logging.getLogger("aip-rag.chat_use_case")
from ...config import rag_settings


def _build_citation_dto(c: Dict[str, Any]) -> RagCitationDTO:
    """Builds RagCitationDTO compliant with both legacy readers and EXEC-RAG-05 contract."""
    title = c.get("title") or c.get("document_name") or "Tài liệu tham khảo"
    page = int(c.get("page_number") or c.get("page") or 1)
    score = float(c.get("score") or c.get("relevance_score") or 0.0)
    excerpt = c.get("excerpt") or c.get("quote") or ""
    section = c.get("section") or c.get("heading") or c.get("heading_path") or None

    return RagCitationDTO(
        index=int(c.get("index", 1)),
        doc_id=str(c.get("doc_id", "")),
        title=title,
        page_number=page,
        score=score,
        excerpt=excerpt,
        document_name=title,
        page=page,
        section=section,
        relevance_score=score,
        quote=excerpt,
    )


def _deduplicate_citations(citations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicates citations by document source (doc_id and title).
    Keeps the highest-scoring chunk representation for each unique document
    and sequentially renumbers the citation index.
    """
    seen_keys = set()
    unique = []
    for c in citations:
        doc_key = str(c.get("doc_id") or c.get("title") or "").strip()
        title_key = str(c.get("title") or "").strip()
        if (doc_key and doc_key in seen_keys) or (title_key and title_key in seen_keys):
            continue
        if doc_key:
            seen_keys.add(doc_key)
        if title_key:
            seen_keys.add(title_key)
        unique.append(c)

    result = []
    for idx, c in enumerate(unique, start=1):
        item = dict(c)
        item["index"] = idx
        result.append(item)
    return result


def _filter_attributed_citations(
    citations: List[Dict[str, Any]],
    answer: str,
    strategy: str = "stuff",
) -> List[Dict[str, Any]]:
    """
    Filters citations to only include sources that actually contributed facts
    to the generated answer (Grounded Citation Attribution).
    Eliminates irrelevant retrieval trailing chunks (e.g. False Positive noise).
    """
    if not citations or not answer:
        return []

    import re
    # Check if answer expresses refusal or ungrounded general response
    refusal_signals = [
        "không nằm trong tài liệu",
        "không có thông tin trong tài liệu",
        "không tìm thấy thông tin",
        "tôi không tìm thấy thông tin",
        "không được đề cập trong tài liệu",
        "tài liệu không chứa",
        "không có nội dung nào",
        "không có trong tài liệu tham khảo được cung cấp",
    ]
    ans_lower = answer.lower()
    explicit_markers = set(re.findall(r"\[(\d+)\]", answer))

    if any(sig in ans_lower for sig in refusal_signals) or answer.strip() == REFUSAL_MESSAGE.strip():
        if not explicit_markers:
            return []

    if strategy in ("map_reduce", "refine", "multihop_cot"):
        return citations
    # 1. Check if LLM explicitly used in-text citation markers like [1], [2], etc.
    explicit_markers = set(re.findall(r"\[(\d+)\]", answer))
    if explicit_markers:
        matched = [c for c in citations if str(c.get("index")) in explicit_markers]
        if matched:
            return [dict(c) for c in matched]

    # 2. Factual N-gram / Key-phrase overlap attribution
    stop_words = {
        "là", "và", "các", "của", "trong", "có", "được", "đã", "những", "cho",
        "về", "này", "đó", "với", "khi", "để", "một", "thì", "sẽ", "ở", "tại",
        "ra", "lại", "theo", "nào", "ai", "gì", "từ", "làm", "thể", "cần",
        "sau", "hai", "cùng", "như", "rằng", "bởi", "nhiều", "toàn", "mỗi",
        "the", "and", "is", "in", "of", "to", "for", "with", "a", "an", "on", "at"
    }

    clean_ans = re.sub(r"[^\w\s]", " ", answer.lower())
    ans_words = clean_ans.split()

    ans_bigrams = set()
    for i in range(len(ans_words) - 1):
        w1, w2 = ans_words[i], ans_words[i + 1]
        if (w1 not in stop_words or w2 not in stop_words) and len(w1) > 1 and len(w2) > 1:
            ans_bigrams.add(f"{w1} {w2}")

    attributed = []
    for c in citations:
        text = (c.get("text") or c.get("excerpt") or "").lower()
        if not text and isinstance(c, dict):
            text = (c.get("payload", {}).get("text") or "").lower()

        clean_text = re.sub(r"[^\w\s]", " ", text)
        text_words = clean_text.split()

        chunk_bigrams = set()
        for i in range(len(text_words) - 1):
            w1, w2 = text_words[i], text_words[i + 1]
            if (w1 not in stop_words or w2 not in stop_words) and len(w1) > 1 and len(w2) > 1:
                chunk_bigrams.add(f"{w1} {w2}")

        overlap = ans_bigrams.intersection(chunk_bigrams)
        if len(overlap) >= 2:
            attributed.append(c)

    # Clean Grounded Attribution: never attach ungrounded citations when LLM answer does not reference them
    if strategy == "map_rerank" and attributed:
        attributed = [attributed[0]]

    result = []
    for idx, c in enumerate(attributed, start=1):
        item = dict(c)
        item["index"] = idx
        result.append(item)
    return result


class CandidateWrapper:
    """Wrapper normalizing Qdrant raw candidate payloads for prompt assembly."""

    def __init__(self, d: Dict[str, Any]):
        self.doc_id = d.get("payload", {}).get("doc_id", d.get("doc_id", ""))
        self.title = d.get("payload", {}).get("title", d.get("title", "Tài liệu"))
        self.page_number = d.get("payload", {}).get("page_number", d.get("page_number", 1))
        self.text = d.get("payload", {}).get("text", d.get("text", ""))
        self.score = d.get("score", 0.0)
        self.metadata = d.get("payload", {})


# Clarification menu for ambiguous e-invoice/e-signature symptoms (FR-RET-05).
# TODO(tenant-config): this is domain content for one deployment and belongs in per-tenant configuration.
AMBIGUOUS_CLARIFICATION: Dict[str, Any] = {
    "question": "Bạn đang gặp sự cố khi thực hiện nghiệp vụ nào dưới đây để hệ thống hướng dẫn chính xác?",
    "options": [
        "1. Lỗi khi xuất hoặc gửi Hóa đơn điện tử có mã của cơ quan Thuế",
        "2. Lỗi khi xuất Báo cáo tình hình sử dụng hóa đơn (BC26) hoặc bảng kê",
        "3. Lỗi kết nối ký số với USB Token (máy không nhận hoặc chưa cài plugin)",
        "4. Lỗi kết nối Chữ ký số từ xa (SmartCA)",
    ],
    "intent_context": "AMBIGUOUS_EXPORT_OR_SIGN_ERROR",
}
AMBIGUOUS_CLARIFICATION_TEXT = (
    "Để hỗ trợ bạn xử lý chính xác sự cố, vui lòng chọn nghiệp vụ bạn đang thực hiện:\n\n"
    "* **1.** Lỗi khi xuất/gửi Hóa đơn điện tử có mã cơ quan Thuế\n"
    "* **2.** Lỗi khi xuất Báo cáo tình hình sử dụng hóa đơn (BC26)\n"
    "* **3.** Lỗi kết nối ký số với USB Token (chưa nhận Token hoặc thiếu plugin)\n"
    "* **4.** Lỗi kết nối Chữ ký số từ xa (SmartCA)"
)


@dataclass
class _PreparedQuery:
    history: List[Dict[str, str]]
    rewrite: RewrittenQuery
    standalone_query: str
    generation_history: List[Dict[str, str]]
    effective_query: str
    routing: RoutingDecision


@dataclass
class _RetrievalOutcome:
    hyde: HyDEResult
    candidates: List[Dict[str, Any]]
    reranked: List[Dict[str, Any]]
    valid: List[Dict[str, Any]]
    top_score: float
    threshold: float
    refused: bool
    gate_latency_ms: float = 0.0


INFRASTRUCTURE_ERRORS = (EmbeddingError, RerankerError, VectorStoreError, LLMGenerationError)


class RagChatUseCase:
    """Enterprise RAG Chat Use Case complying with Clean Architecture."""

    def __init__(
        self,
        vector_store: VectorStorePort,
        embedding_service: EmbeddingPort,
        llm_service: LLMPort,
        session_repo: SessionRepositoryPort,
        cache_service: Optional[CachePort] = None,
        reranker_service: Optional[RerankerPort] = None,
        observability_service: Optional[ObservabilityPort] = None,
    ) -> None:
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        self.llm_service = llm_service
        self.session_repo = session_repo
        self.cache_service = cache_service or NullCacheAdapter()
        self.reranker_service = reranker_service or cross_encoder_reranker
        self.obs = observability_service or NullObservabilityAdapter()

    async def _build_and_persist_escalation(
        self,
        session_id: str,
        tenant_id: str,
        user_id: str,
        query: str,
        top1_score: float,
    ) -> Dict[str, Any]:
        """
        Generates standardized Graceful Escalation Payload and persists
        the unresolved query ticket into MongoDB (RER-RAG-02).
        """
        ticket_id = f"ticket_{uuid.uuid4().hex[:10]}"
        ticket_record = {
            "ticket_id": ticket_id,
            "session_id": session_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "query": query,
            "top1_score": round(top1_score, 4),
            "reason": "out_of_domain_or_insufficient_evidence",
            "created_at": time.time(),
        }
        if hasattr(self.session_repo, "record_escalation_ticket"):
            try:
                await self.session_repo.record_escalation_ticket(ticket_record)
            except Exception as exc:
                logger.warning("Could not persist escalation ticket: %s", exc)

        return {
            "status": "escalation_required",
            "reason": "out_of_domain_or_insufficient_evidence",
            "message": REFUSAL_MESSAGE,
            "escalation_data": {
                "hotline": rag_settings.escalation_hotline,
                "support_method": rag_settings.escalation_support_method,
                "instructions": rag_settings.escalation_instructions,
                "auto_ticket_created": True,
                "ticket_id": ticket_id,
            },
        }

    SESSION_TIMEOUT_SECONDS = 15 * 60  # BRD 5.2: 15-minute session inactivity timeout

    async def _resolve_history(
        self,
        session_id: str,
        user_id: str,
        tenant_id: str,
        explicit_history: Optional[List[Dict[str, str]]],
    ) -> List[Dict[str, str]]:
        if explicit_history:
            return explicit_history

        session_record = await self.session_repo.get_session(session_id, user_id, tenant_id)
        if not session_record:
            return []

        # BRD 5.2: Reset session after 15 minutes of inactivity
        updated_at = float(session_record.get("updated_at", 0.0))
        if updated_at and (time.time() - updated_at) > self.SESSION_TIMEOUT_SECONDS:
            logger.info("Session %s expired (>15min inactivity). Resetting history.", session_id)
            return []

        formatted: List[Dict[str, str]] = []
        for msg in session_record.get("messages", []):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role and content:
                formatted.append({"role": role, "content": content})
        return formatted[-6:]

    def _resolve_combine_strategy(
        self,
        requested_strategy: Optional[str],
        query: str,
        wrapped_chunks: List[Any],
    ) -> str:
        """
        Resolves whether to use 'stuff', 'map_reduce', 'refine', or 'map_rerank' combine strategy (Slide 80).
        """
        if requested_strategy in ("map_reduce", "refine", "map_rerank"):
            return requested_strategy
        if requested_strategy == "stuff":
            return "stuff"

        if len(wrapped_chunks) < 2:
            return "stuff"

        total_chars = sum(len(getattr(c, "text", "") or "") for c in wrapped_chunks)
        query_lower = query.lower()
        is_summary_query = any(
            k in query_lower
            for k in [
                "tổng hợp", "tóm tắt", "tổng kết", "toàn bộ các", "toàn bộ",
                "báo cáo tổng quan", "tổng quan"
            ]
        )

        # Trigger Map-Reduce for summary queries or large context (> 8000 chars)
        if is_summary_query or total_chars > 8000:
            return "map_reduce"

        return "stuff"

    @staticmethod
    def _parse_map_rerank_response(raw_text: str, chunk_index: int) -> Tuple[int, str]:
        """
        Parses confidence score (0-100) and answer text from LLM's Map-Rerank response (Slide 80).
        Format:
        ĐIỂM: <0-100>
        CÂU_TRẢ_LỜI: <answer text with [k]>
        """
        score = 0
        answer_lines: List[str] = []
        capturing_answer = False

        for line in raw_text.strip().split("\n"):
            line_str = line.strip()
            score_match = re.search(r'(?:ĐIỂM|SCORE|Điểm|Score)\s*:\s*(\d+)', line_str, re.IGNORECASE)
            if score_match and not capturing_answer:
                try:
                    score = int(score_match.group(1))
                except ValueError:
                    score = 0
                continue

            ans_match = re.match(r'(?:CÂU_TRẢ_LỜI|ANSWER|Câu trả lời|Answer)\s*:\s*(.*)', line_str, re.IGNORECASE)
            if ans_match:
                capturing_answer = True
                first_line = ans_match.group(1).strip()
                if first_line:
                    answer_lines.append(first_line)
                continue

            if capturing_answer:
                answer_lines.append(line)

        if answer_lines:
            answer = "\n".join(answer_lines).strip()
        else:
            answer = raw_text.strip()
            if f"[{chunk_index}]" not in answer and "KHÔNG_CÓ_THÔNG_TIN" not in answer:
                answer = f"{answer} [{chunk_index}]"

        # Sanitize non-informative responses
        if "KHÔNG_CÓ_THÔNG_TIN_LIÊN_QUAN" in answer or "KHÔNG_CÓ_THÔNG_TIN" in answer:
            score = 0
            answer = ""

        return score, answer

    async def _retrieve_and_rerank_hop(
        self,
        query_text: str,
        tenant_id: str,
        user_role: str,
        request: RagChatRequestDTO,
        target_top_k: int,
    ) -> List[Dict[str, Any]]:
        """
        Executes a single retrieval & reranking hop for Multi-Hop Iterative RAG (Slide 94-103).
        """
        query_vec = await self.embedding_service.get_embedding(query_text)
        hybrid_fetch_k = min(max(target_top_k * 6, 24), 36)
        candidates = await self.vector_store.search(
            query_vector=query_vec,
            tenant_id=tenant_id,
            query_text=query_text,
            user_role=user_role,
            department=request.department,
            doc_ids=request.doc_ids,
            top_k=hybrid_fetch_k,
            hybrid=True,
            as_of_date=request.as_of_date,
        )
        # Pass safety floor (0.20) to reranker to preserve Grey-Zone candidates
        reranked = await self.reranker_service.arerank(
            query=query_text,
            candidates=candidates,
            top_n=min(target_top_k, 3),
            min_threshold=0.20,
        )
        return [c for c in reranked if float(c.get("score", 0.0)) >= 0.20]

    async def _execute_multi_hop(
        self,
        request: RagChatRequestDTO,
        standalone_query: str,
        decomp: DecomposedQuery,
        history: List[Dict[str, str]],
        session_id: str,
        tenant_id: str,
        user_id: str,
        user_role: str,
        authorization: Optional[str],
        start_t: float,
        rewrite_decision: RewrittenQuery,
    ) -> RagChatResponseDTO:
        """
        Executes Multi-Hop Iterative RAG & Chain-of-Thought Synthesis (Slide 94-103).
        """
        sub_q1, sub_q2 = decomp.sub_queries[0], decomp.sub_queries[1]
        target_top_k = min(request.top_k, 4)

        if decomp.strategy == "COMPARATIVE":
            # Concurrent retrieval for comparative queries
            t1 = self._retrieve_and_rerank_hop(sub_q1, tenant_id, user_role, request, target_top_k)
            t2 = self._retrieve_and_rerank_hop(sub_q2, tenant_id, user_role, request, target_top_k)
            valid_cands1, valid_cands2 = await asyncio.gather(t1, t2)
            hops_executed = 2
        else:
            # Sequential iterative retrieval with bridging
            valid_cands1 = await self._retrieve_and_rerank_hop(sub_q1, tenant_id, user_role, request, target_top_k)
            bridged_q2 = query_decomposer.bridge_query(sub_q2, valid_cands1)
            valid_cands2 = await self._retrieve_and_rerank_hop(bridged_q2, tenant_id, user_role, request, target_top_k)
            hops_executed = 2

        seen_keys = set()
        all_valid_cands = []
        hop1_valid_cands = []
        hop2_valid_cands = []

        for c in valid_cands1:
            key = (c.get("payload", {}).get("doc_id", c.get("doc_id", "")), c.get("payload", {}).get("text", c.get("text", "")))
            hop1_valid_cands.append(c)
            if key not in seen_keys:
                seen_keys.add(key)
                all_valid_cands.append(c)

        for c in valid_cands2:
            key = (c.get("payload", {}).get("doc_id", c.get("doc_id", "")), c.get("payload", {}).get("text", c.get("text", "")))
            hop2_valid_cands.append(c)
            if key not in seen_keys:
                seen_keys.add(key)
                all_valid_cands.append(c)

        if not all_valid_cands:
            latency_ms = (time.time() - start_t) * 1000
            await self._save_session_turn(
                session_id=session_id,
                user_id=user_id,
                tenant_id=tenant_id,
                query=request.query,
                answer=REFUSAL_MESSAGE,
                citations=[],
                model=request.model,
                intent="REFUSAL",
                latency_ms=latency_ms,
            )
            return RagChatResponseDTO(
                answer=REFUSAL_MESSAGE,
                model=request.model,
                citations=[],
                latency_ms=round(latency_ms, 2),
                intent="REFUSAL",
                session_id=session_id,
                circuit_breaker_triggered=True,
                is_refusal=True,
                pre_retrieval_tier=rewrite_decision.tier,
                pre_retrieval_latency_ms=round(rewrite_decision.latency_ms, 2),
                is_multi_hop=True,
                sub_queries=decomp.sub_queries,
                hops_executed=hops_executed,
            )

        wrapped_all = [CandidateWrapper(c) for c in all_valid_cands]
        raw_citations, _ = prompt_builder.build_context_and_citations(wrapped_all)

        chunk_index_map = {}
        for c_dto in raw_citations:
            chunk_index_map[(c_dto["doc_id"], c_dto["excerpt"])] = c_dto["index"]

        def _format_hop_blocks(cand_list: List[Dict[str, Any]]) -> List[str]:
            blocks = []
            for c in cand_list:
                doc_id = c.get("payload", {}).get("doc_id", c.get("doc_id", ""))
                title = c.get("payload", {}).get("title", c.get("title", "Tài liệu"))
                text = c.get("payload", {}).get("text", c.get("text", ""))
                excerpt = text[:350].strip() + "..." if len(text) > 350 else text.strip()
                idx = chunk_index_map.get((doc_id, excerpt), len(blocks) + 1)
                blocks.append(f"[{idx}] (Nguồn: {title})\n{text}")
            return blocks

        hop1_blocks = _format_hop_blocks(hop1_valid_cands)
        hop2_blocks = _format_hop_blocks(hop2_valid_cands)

        messages = prompt_builder.build_multihop_cot_prompt(
            query=request.query,
            sub_queries=decomp.sub_queries,
            hop1_blocks=hop1_blocks,
            hop2_blocks=hop2_blocks,
            history=history[-4:],
        )

        answer, prompt_tokens, completion_tokens = await self.llm_service.generate(
            messages=messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=max(request.max_tokens or 0, 768),
            authorization=authorization,
        )

        deduped_raw_citations = _deduplicate_citations(raw_citations)

        citation_dtos = [_build_citation_dto(c) for c in deduped_raw_citations]

        latency_ms = (time.time() - start_t) * 1000

        await self._save_session_turn(
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            query=request.query,
            answer=answer,
            citations=deduped_raw_citations,
            model=request.model,
            intent="QA_MULTIHOP_COT",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
        )

        return RagChatResponseDTO(
            answer=answer,
            model=request.model,
            citations=citation_dtos,
            latency_ms=round(latency_ms, 2),
            intent="QA_MULTIHOP_COT",
            combine_strategy="multihop_cot",
            session_id=session_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            pre_retrieval_tier=rewrite_decision.tier,
            pre_retrieval_latency_ms=round(rewrite_decision.latency_ms, 2),
            is_multi_hop=True,
            sub_queries=decomp.sub_queries,
            hops_executed=hops_executed,
        )

    async def _stream_execute_multi_hop(
        self,
        request: RagChatRequestDTO,
        standalone_query: str,
        decomp: DecomposedQuery,
        history: List[Dict[str, str]],
        session_id: str,
        tenant_id: str,
        user_id: str,
        user_role: str,
        authorization: Optional[str],
        start_t: float,
        rewrite_decision: RewrittenQuery,
    ) -> AsyncGenerator[str, None]:
        """
        Executes streaming Multi-Hop Iterative RAG & Chain-of-Thought Synthesis (Slide 94-103).
        """
        sub_q1, sub_q2 = decomp.sub_queries[0], decomp.sub_queries[1]
        target_top_k = min(request.top_k, 4)

        if decomp.strategy == "COMPARATIVE":
            t1 = self._retrieve_and_rerank_hop(sub_q1, tenant_id, user_role, request, target_top_k)
            t2 = self._retrieve_and_rerank_hop(sub_q2, tenant_id, user_role, request, target_top_k)
            valid_cands1, valid_cands2 = await asyncio.gather(t1, t2)
            hops_executed = 2
        else:
            valid_cands1 = await self._retrieve_and_rerank_hop(sub_q1, tenant_id, user_role, request, target_top_k)
            bridged_q2 = query_decomposer.bridge_query(sub_q2, valid_cands1)
            valid_cands2 = await self._retrieve_and_rerank_hop(bridged_q2, tenant_id, user_role, request, target_top_k)
            hops_executed = 2

        seen_keys = set()
        all_valid_cands = []
        hop1_valid_cands = []
        hop2_valid_cands = []

        for c in valid_cands1:
            key = (c.get("payload", {}).get("doc_id", c.get("doc_id", "")), c.get("payload", {}).get("text", c.get("text", "")))
            hop1_valid_cands.append(c)
            if key not in seen_keys:
                seen_keys.add(key)
                all_valid_cands.append(c)

        for c in valid_cands2:
            key = (c.get("payload", {}).get("doc_id", c.get("doc_id", "")), c.get("payload", {}).get("text", c.get("text", "")))
            hop2_valid_cands.append(c)
            if key not in seen_keys:
                seen_keys.add(key)
                all_valid_cands.append(c)

        if not all_valid_cands:
            latency_ms = (time.time() - start_t) * 1000
            yield f"data: {json.dumps({'token': REFUSAL_MESSAGE, 'session_id': session_id})}\n\n"
            await self._save_session_turn(
                session_id=session_id,
                user_id=user_id,
                tenant_id=tenant_id,
                query=request.query,
                answer=REFUSAL_MESSAGE,
                citations=[],
                model=request.model,
                intent="REFUSAL",
                latency_ms=latency_ms,
            )
            yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'citations': [], 'circuit_breaker_triggered': True, 'is_refusal': True, 'pre_retrieval_tier': rewrite_decision.tier, 'ttft_ms': None, 'is_multi_hop': True, 'sub_queries': decomp.sub_queries, 'hops_executed': hops_executed})}\n\n"
            return

        wrapped_all = [CandidateWrapper(c) for c in all_valid_cands]
        raw_citations, _ = prompt_builder.build_context_and_citations(wrapped_all)

        chunk_index_map = {}
        for c_dto in raw_citations:
            chunk_index_map[(c_dto["doc_id"], c_dto["excerpt"])] = c_dto["index"]

        def _format_hop_blocks(cand_list: List[Dict[str, Any]]) -> List[str]:
            blocks = []
            for c in cand_list:
                doc_id = c.get("payload", {}).get("doc_id", c.get("doc_id", ""))
                title = c.get("payload", {}).get("title", c.get("title", "Tài liệu"))
                text = c.get("payload", {}).get("text", c.get("text", ""))
                excerpt = text[:350].strip() + "..." if len(text) > 350 else text.strip()
                idx = chunk_index_map.get((doc_id, excerpt), len(blocks) + 1)
                blocks.append(f"[{idx}] (Nguồn: {title})\n{text}")
            return blocks

        hop1_blocks = _format_hop_blocks(hop1_valid_cands)
        hop2_blocks = _format_hop_blocks(hop2_valid_cands)

        messages = prompt_builder.build_multihop_cot_prompt(
            query=request.query,
            sub_queries=decomp.sub_queries,
            hop1_blocks=hop1_blocks,
            hop2_blocks=hop2_blocks,
            history=history[-4:],
        )

        accumulated_text = []
        first_token_time = None
        async for token in self.llm_service.stream_generate(
            messages=messages,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            authorization=authorization,
        ):
            if first_token_time is None:
                first_token_time = time.time()
            accumulated_text.append(token)
            yield f"data: {json.dumps({'token': token, 'session_id': session_id})}\n\n"

        deduped_raw_citations = _deduplicate_citations(raw_citations)
        latency_ms = (time.time() - start_t) * 1000
        full_answer = "".join(accumulated_text)

        await self._save_session_turn(
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            query=request.query,
            answer=full_answer,
            citations=deduped_raw_citations,
            model=request.model,
            intent="QA_MULTIHOP_COT",
            latency_ms=latency_ms,
        )

        citation_dtos = [
            {
                "index": c["index"],
                "doc_id": c["doc_id"],
                "title": c["title"],
                "page_number": c["page_number"],
                "score": c["score"],
                "excerpt": c["excerpt"],
            }
            for c in deduped_raw_citations
        ]
        ttft_ms = round((first_token_time - start_t) * 1000, 2) if first_token_time else None
        yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'citations': citation_dtos, 'combine_strategy': 'multihop_cot', 'pre_retrieval_tier': rewrite_decision.tier, 'pre_retrieval_latency_ms': round(rewrite_decision.latency_ms, 2), 'ttft_ms': ttft_ms, 'is_multi_hop': True, 'sub_queries': decomp.sub_queries, 'hops_executed': hops_executed})}\n\n"

    # ------------------------------------------------------------------
    # Shared pipeline stages (used by both execute() and stream_execute())
    # ------------------------------------------------------------------

    @staticmethod
    def _truncate_query(request: RagChatRequestDTO) -> None:
        """Input guardrail against memory blow-up / token DoS."""
        max_q_len = rag_settings.max_query_length
        if request.query and len(request.query) > max_q_len:
            logger.warning("Truncated oversized query from %d to %d chars", len(request.query), max_q_len)
            request.query = request.query[:max_q_len]

    @staticmethod
    def _is_cacheable(request: RagChatRequestDTO) -> bool:
        # Results scoped to specific documents or an ad-hoc attachment are not covered by the cache key.
        return not request.doc_ids and not (request.adhoc_context and request.adhoc_context.strip())

    def _cache_key_args(
        self,
        request: RagChatRequestDTO,
        cache_query: str,
        tenant_id: str,
        user_role: str,
    ) -> Dict[str, Any]:
        # The requested strategy (not the resolved one) is used for both get and set so that
        # 'auto' requests can hit; cache_query is the standalone (history-resolved) query.
        return {
            "query": cache_query,
            "tenant_id": tenant_id,
            "combine_strategy": request.combine_strategy or "auto",
            "as_of_date": request.as_of_date,
            "user_role": user_role,
            "department": request.department,
            "similarity_threshold": request.similarity_threshold,
        }

    async def _cache_lookup(
        self,
        request: RagChatRequestDTO,
        cache_query: str,
        tenant_id: str,
        user_role: str,
        session_id: str,
        start_t: float,
    ) -> Optional[RagChatResponseDTO]:
        if not self._is_cacheable(request):
            return None
        cached_res = await self.cache_service.get(**self._cache_key_args(request, cache_query, tenant_id, user_role))
        if not cached_res:
            self.obs.record_cache_op("exact", "miss", tenant_id=tenant_id)
            return None
        self.obs.record_cache_op("exact", "hit", tenant_id=tenant_id)
        top_score = (cached_res.telemetry or {}).get("rerank_top1_score", 1.0)
        if request.similarity_threshold and request.similarity_threshold > top_score:
            return None
        cached_res.session_id = session_id
        cached_res.latency_ms = round((time.time() - start_t) * 1000, 2)
        logger.info("Serving query from cache (latency: %.2f ms)", cached_res.latency_ms)
        return cached_res

    async def _prepare_query(
        self,
        request: RagChatRequestDTO,
        history: List[Dict[str, str]],
        tenant_id: str,
    ) -> "_PreparedQuery":
        """Pre-retrieval: multi-turn reformulation + intent routing (Slides 66, 133-137)."""
        t_rew_0 = time.perf_counter()
        rewrite_decision: RewrittenQuery = await query_rewriter.rewrite_advanced(
            request.query,
            history,
            llm_port=self.llm_service,
            model=request.model,
            speculative_timeout=rag_settings.speculative_rewrite_timeout,
        )
        self.obs.record_stage_latency("rewrite", time.perf_counter() - t_rew_0, tenant_id=tenant_id)
        standalone_query = rewrite_decision.text

        t_int_0 = time.perf_counter()
        routing: RoutingDecision = await intent_classifier.classify_advanced(
            standalone_query,
            llm_port=self.llm_service,
            model=request.model,
        )
        self.obs.record_stage_latency("intent", time.perf_counter() - t_int_0, tenant_id=tenant_id)

        return _PreparedQuery(
            history=history,
            rewrite=rewrite_decision,
            standalone_query=standalone_query,
            # Multi-turn entity isolation: a standalone (new-topic) query must not see prior turns'
            # facts, otherwise small LLMs copy details from the previous entity into the answer.
            generation_history=[] if rewrite_decision.reason == "standalone_query" else history[-4:],
            effective_query=standalone_query if rewrite_decision.is_reformulated else request.query,
            routing=routing,
        )

    @staticmethod
    def _effective_threshold(request: RagChatRequestDTO) -> float:
        if request.similarity_threshold == 0.0:
            return 0.0
        return max(request.similarity_threshold, CONFIDENCE_GATE_MIN_THRESHOLD)

    async def _retrieve_and_gate(
        self,
        request: RagChatRequestDTO,
        prepared: "_PreparedQuery",
        tenant_id: str,
        user_role: str,
    ) -> "_RetrievalOutcome":
        """HyDE -> embedding -> hybrid search -> cross-encoder rerank -> confidence gate."""
        standalone_query = prepared.standalone_query
        hyde_res: HyDEResult = await hyde_generator.generate_hypothetical_doc(
            query=standalone_query,
            llm_port=self.llm_service,
            model=request.model,
            enable_hyde=getattr(request, "enable_hyde", None),
            timeout=1.0,
        )
        if hyde_res.is_active and hyde_res.hypothetical_document:
            query_vec, hyde_vec = await asyncio.gather(
                self.embedding_service.get_embedding(standalone_query),
                self.embedding_service.get_embedding(hyde_res.hypothetical_document),
            )
            query_vector = hyde_generator.fuse_embeddings(query_vec, hyde_vec, alpha=0.4)
        else:
            query_vector = await self.embedding_service.get_embedding(standalone_query)

        target_top_k = prepared.routing.adaptive_top_k or request.top_k or 4
        hybrid_fetch_k = min(
            max(target_top_k * rag_settings.hybrid_fetch_multiplier, 32),
            rag_settings.hybrid_fetch_ceiling,
        )
        sparse_query_text = getattr(prepared.rewrite, "sparse_query", None) or standalone_query
        t_ret_0 = time.perf_counter()
        candidates = await self.vector_store.search(
            query_vector=query_vector,
            tenant_id=tenant_id,
            query_text=sparse_query_text,
            user_role=user_role,
            department=request.department,
            doc_ids=request.doc_ids,
            top_k=hybrid_fetch_k,
            hybrid=True,
            as_of_date=request.as_of_date,
        )
        self.obs.record_stage_latency("retrieval_hybrid", time.perf_counter() - t_ret_0, tenant_id=tenant_id)
        self.obs.record_retrieval("hybrid", len(candidates), tenant_id=tenant_id)

        threshold = self._effective_threshold(request)
        t_rerank_0 = time.perf_counter()
        reranked = await self.reranker_service.arerank(
            query=standalone_query,
            candidates=candidates,
            top_n=target_top_k,
            min_threshold=threshold,
        )
        self.obs.record_stage_latency("rerank", time.perf_counter() - t_rerank_0, tenant_id=tenant_id)

        t_gate_0 = time.perf_counter()
        top_score = float(reranked[0].get("score", 0.0)) if reranked else 0.0
        refused = not reranked or (threshold > 0.0 and top_score < threshold)
        valid = (
            reranked
            if threshold == 0.0
            else [c for c in reranked if float(c.get("score", 0.0)) >= min(threshold, 0.20)]
        )
        gate_latency_ms = (time.perf_counter() - t_gate_0) * 1000
        self.obs.record_stage_latency("gatekeeper", gate_latency_ms / 1000, tenant_id=tenant_id)
        return _RetrievalOutcome(
            gate_latency_ms=gate_latency_ms,
            hyde=hyde_res,
            candidates=candidates,
            reranked=reranked,
            valid=valid,
            top_score=top_score,
            threshold=threshold,
            refused=refused,
        )

    async def _record_refusal(
        self,
        request: RagChatRequestDTO,
        session_id: str,
        tenant_id: str,
        user_id: str,
        top_score: float,
        latency_ms: float,
    ) -> Dict[str, Any]:
        await self._save_session_turn(
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            query=request.query,
            answer=REFUSAL_MESSAGE,
            citations=[],
            model=request.model,
            intent="REFUSAL",
            latency_ms=latency_ms,
        )
        return await self._build_and_persist_escalation(
            session_id=session_id,
            tenant_id=tenant_id,
            user_id=user_id,
            query=request.query,
            top1_score=top_score,
        )

    async def execute(
        self,
        request: RagChatRequestDTO,
        tenant_id: str = DEFAULT_TENANT_ID,
        user_id: str = "default_user",
        user_role: str = "user",
        authorization: Optional[str] = None,
    ) -> RagChatResponseDTO:
        start_t = time.time()
        tenant_id = normalize_tenant_id(tenant_id)
        session_id = request.conversation_id or f"sess_{uuid.uuid4().hex[:12]}"
        self._truncate_query(request)

        # 0. Exact cache (FR-EXEC-05). A first-turn query is looked up before any LLM call; a
        #    follow-up is looked up by its history-resolved standalone form after rewriting,
        #    so "what documents does it need?" never returns another conversation's answer.
        history = await self._resolve_history(session_id, user_id, tenant_id, request.history)
        if not history:
            cached_res = await self._cache_lookup(request, request.query, tenant_id, user_role, session_id, start_t)
            if cached_res:
                return cached_res

        # 1-2. Multi-turn reformulation and intent routing
        prepared = await self._prepare_query(request, history, tenant_id)
        rewrite_decision = prepared.rewrite
        standalone_query = prepared.standalone_query
        generation_history = prepared.generation_history
        effective_query = prepared.effective_query
        routing = prepared.routing
        cache_query = standalone_query if history else request.query
        if history:
            cached_res = await self._cache_lookup(request, cache_query, tenant_id, user_role, session_id, start_t)
            if cached_res:
                return cached_res

        # 2B. Handle AMBIGUOUS_SYMPTOM with Interactive Clarification (FR-RET-05 / BRD Pain Point 5)
        if routing.intent == QueryIntent.AMBIGUOUS_SYMPTOM:
            clarification_dto = ClarificationDTO(**AMBIGUOUS_CLARIFICATION)
            answer_text = AMBIGUOUS_CLARIFICATION_TEXT
            latency_ms = (time.time() - start_t) * 1000
            await self._save_session_turn(
                session_id=session_id,
                user_id=user_id,
                tenant_id=tenant_id,
                query=request.query,
                answer=answer_text,
                citations=[],
                model=request.model,
                intent="AMBIGUOUS_SYMPTOM",
                latency_ms=latency_ms,
            )
            return RagChatResponseDTO(
                answer=answer_text,
                model=request.model,
                citations=[],
                latency_ms=round(latency_ms, 2),
                intent="AMBIGUOUS_SYMPTOM",
                session_id=session_id,
                status="clarification_needed",
                clarification=clarification_dto,
                pre_retrieval_tier=rewrite_decision.tier,
                pre_retrieval_latency_ms=round(rewrite_decision.latency_ms, 2),
            )

        # 3. Handle CHITCHAT without vector search overhead

        if routing.intent == QueryIntent.CHITCHAT:
            chitchat_messages = [
                {"role": "system", "content": CHITCHAT_SYSTEM_PROMPT},
                *history[-4:],
                {"role": "user", "content": request.query},
            ]
            answer, prompt_tokens, completion_tokens = await self.llm_service.generate(
                messages=chitchat_messages,
                model=request.model,
                temperature=0.7,
                max_tokens=request.max_tokens,
                authorization=authorization,
            )
            latency_ms = (time.time() - start_t) * 1000

            # Auto-save session
            await self._save_session_turn(
                session_id=session_id,
                user_id=user_id,
                tenant_id=tenant_id,
                query=request.query,
                answer=answer,
                citations=[],
                model=request.model,
                intent="CHITCHAT",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
            )

            return RagChatResponseDTO(
                answer=answer,
                model=request.model,
                citations=[],
                latency_ms=round(latency_ms, 2),
                intent="CHITCHAT",
                session_id=session_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                pre_retrieval_tier=rewrite_decision.tier,
                pre_retrieval_latency_ms=round(rewrite_decision.latency_ms, 2),
            )

        # Check for Ad-hoc File Attachment in RAM (Ad-hoc RAG)
        if request.adhoc_context and request.adhoc_context.strip():
            adhoc_title = getattr(request, "adhoc_filename", None) or "Tài liệu đính kèm tạm thời"
            adhoc_excerpt = request.adhoc_context[:350].strip() + "..." if len(request.adhoc_context) > 350 else request.adhoc_context.strip()

            system_prompt = (
                f"Bạn là Trợ lý AI Chuyên nghiệp của AIP Platform. Người dùng đã đính kèm tài liệu cá nhân '{adhoc_title}'.\n"
                "Nhiệm vụ của bạn là đọc kỹ tài liệu đính kèm bên dưới và trả lời câu hỏi của người dùng một cách chính xác, trung thực, có cấu trúc rõ ràng (bảng biểu, gạch đầu dòng nếu phù hợp).\n"
                "Nếu thông tin không có trong tài liệu, hãy thành thật nêu rõ không có trong tài liệu.\n\n"
                f"=== NỘI DUNG TÀI LIỆU ĐÍNH KÈM ({adhoc_title}) ===\n"
                f"{request.adhoc_context[:16000]}\n"
                "=================================================="
            )

            adhoc_citations = [
                {
                    "index": 1,
                    "doc_id": "adhoc_attachment",
                    "title": adhoc_title,
                    "page_number": 1,
                    "score": 1.0,
                    "excerpt": adhoc_excerpt,
                }
            ]

            messages = [
                {"role": "system", "content": system_prompt},
                *history[-4:],
                {"role": "user", "content": request.query},
            ]

            answer, prompt_tokens, completion_tokens = await self.llm_service.generate(
                messages=messages,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                authorization=authorization,
            )
            latency_ms = (time.time() - start_t) * 1000

            await self._save_session_turn(
                session_id=session_id,
                user_id=user_id,
                tenant_id=tenant_id,
                query=request.query,
                answer=answer,
                citations=adhoc_citations,
                model=request.model,
                intent="ADHOC_QA",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency_ms,
            )

            citation_dtos = [_build_citation_dto(c) for c in adhoc_citations]

            return RagChatResponseDTO(
                answer=answer,
                model=request.model,
                citations=citation_dtos,
                latency_ms=round(latency_ms, 2),
                intent="ADHOC_QA",
                session_id=session_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                pre_retrieval_tier=rewrite_decision.tier,
                pre_retrieval_latency_ms=round(rewrite_decision.latency_ms, 2),
            )

        # 3.5. Multi-Hop Reasoning & Iterative RAG (Slide 94-103)
        multi_hop_flag = getattr(request, "multi_hop", None)
        should_run_multihop = False
        if multi_hop_flag is True:
            should_run_multihop = True
        elif multi_hop_flag is None:
            should_run_multihop = query_decomposer.should_decompose(standalone_query)

        if should_run_multihop:
            decomp = await query_decomposer.decompose(
                standalone_query,
                llm_port=self.llm_service,
                model=request.model,
                timeout=0.8,
            )
            if decomp.is_multi_hop and len(decomp.sub_queries) >= 2:
                return await self._execute_multi_hop(
                    request=request,
                    standalone_query=standalone_query,
                    decomp=decomp,
                    history=generation_history,
                    session_id=session_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    user_role=user_role,
                    authorization=authorization,
                    start_t=start_t,
                    rewrite_decision=rewrite_decision,
                )

        # 4-7. HyDE + hybrid retrieval + cross-encoder rerank + confidence gate (shared stage)
        outcome = await self._retrieve_and_gate(request, prepared, tenant_id, user_role)
        hyde_res = outcome.hyde
        reranked_candidates = outcome.reranked
        top_cand_score = outcome.top_score
        effective_min_threshold = outcome.threshold

        if outcome.refused:
            gate_latency_ms = outcome.gate_latency_ms
            logger.info(
                "Anti-Hallucination Gatekeeper (BRD-RAG-03): top score %.4f < %.2f; refusing.",
                top_cand_score,
                effective_min_threshold,
            )
            latency_ms = (time.time() - start_t) * 1000
            escalation_payload = await self._record_refusal(
                request, session_id, tenant_id, user_id, top_cand_score, latency_ms
            )
            telemetry_data = {
                "trace_id": f"tr_rag_{uuid.uuid4().hex[:8]}",
                "latency_ms": round(latency_ms, 2),
                "gate_latency_ms": round(gate_latency_ms, 2),
                "rerank_top1_score": round(top_cand_score, 4),
                "standalone_shield_activated": getattr(rewrite_decision, "is_standalone_shield_activated", False),
            }
            return RagChatResponseDTO(
                answer=REFUSAL_MESSAGE,
                model=request.model,
                citations=[],
                latency_ms=round(latency_ms, 2),
                intent="REFUSAL",
                session_id=session_id,
                circuit_breaker_triggered=True,
                is_refusal=True,
                status="escalation_required",
                escalation=escalation_payload,
                telemetry=telemetry_data,
                pre_retrieval_tier=rewrite_decision.tier,
                pre_retrieval_latency_ms=round(rewrite_decision.latency_ms, 2),
                hyde_active=hyde_res.is_active,
                hypothetical_doc=hyde_res.hypothetical_document if hyde_res.is_active else None,
                hyde_latency_ms=round(hyde_res.latency_ms, 2),
            )

        valid_candidates = outcome.valid

        # 7. Grounded Prompt Assembly: Apply Lost-in-the-Middle U-shaped ordering
        t_ctx_0 = time.perf_counter()
        reordered_candidates = prompt_builder.reorder_lost_in_middle(valid_candidates)
        wrapped = [CandidateWrapper(c) for c in reordered_candidates]
        raw_citations, default_system_prompt = prompt_builder.build_context_and_citations(wrapped, query=request.query)
        self.obs.record_stage_latency("context_assembly", time.perf_counter() - t_ctx_0, tenant_id=tenant_id)

        actual_strategy = self._resolve_combine_strategy(
            getattr(request, "combine_strategy", None),
            request.query,
            wrapped,
        )

        prompt_tokens = 0
        completion_tokens = 0
        t_gen_0 = time.perf_counter()

        # 8. LLM Generation via Combine Strategy (Stuff / Map-Reduce / Refine - Slide 80)
        if actual_strategy == "map_reduce" and len(wrapped) >= 2:
            async def _map_chunk(chunk_obj: Any, idx: int) -> Tuple[int, str]:
                map_msgs = prompt_builder.build_map_prompt(chunk_obj, request.query, chunk_index=idx)
                try:
                    summary, _, _ = await self.llm_service.generate(
                        messages=map_msgs,
                        model=request.model,
                        temperature=0.1,
                        max_tokens=384,
                        authorization=authorization,
                    )
                    return idx, summary.strip()
                except Exception as e:
                    logger.warning(f"Map phase error on chunk {idx}: {e}")
                    return idx, ""

            map_tasks = [_map_chunk(chunk_obj, i) for i, chunk_obj in enumerate(wrapped, start=1)]
            map_results = await asyncio.gather(*map_tasks)

            valid_summaries = []
            for idx, s in map_results:
                s_clean = s.strip()
                if (
                    s_clean
                    and "KHÔNG_CÓ_THÔNG_TIN_LIÊN_QUAN" not in s_clean
                    and "NO_RELEVANT_INFO" not in s_clean
                ):
                    valid_summaries.append(f"[{idx}] {s_clean}")

            if valid_summaries:
                reduce_msgs = prompt_builder.build_reduce_prompt(
                    query=request.query,
                    map_summaries=valid_summaries,
                    history=generation_history,
                )
                answer, prompt_tokens, completion_tokens = await self.llm_service.generate(
                    messages=reduce_msgs,
                    model=request.model,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    authorization=authorization,
                )
            else:
                # FR-GEN-02: Zero-context LLM calls strictly forbidden. Return standard refusal.
                logger.info("Map-reduce map phase produced no valid facts; returning standard refusal without calling LLM.")
                answer = REFUSAL_MESSAGE
                raw_citations = []
                prompt_tokens = 0
                completion_tokens = 0

        elif actual_strategy == "refine" and len(wrapped) >= 2:
            init_msgs = prompt_builder.build_refine_initial_prompt(
                chunk=wrapped[0],
                query=request.query,
                chunk_index=1,
                history=generation_history,
            )
            current_answer, prompt_tokens, completion_tokens = await self.llm_service.generate(
                messages=init_msgs,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                authorization=authorization,
            )

            for idx in range(1, len(wrapped)):
                step_msgs = prompt_builder.build_refine_step_prompt(
                    existing_answer=current_answer,
                    next_chunk=wrapped[idx],
                    query=request.query,
                    chunk_index=idx + 1,
                )
                refined, p_tok, c_tok = await self.llm_service.generate(
                    messages=step_msgs,
                    model=request.model,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    authorization=authorization,
                )
                if refined.strip() and "KHÔNG_CÓ_THÔNG_TIN_LIÊN_QUAN" not in refined:
                    current_answer = refined.strip()
                    prompt_tokens += p_tok
                    completion_tokens += c_tok

            answer = current_answer

        elif actual_strategy == "map_rerank" and len(wrapped) >= 1:
            async def _eval_chunk(chunk_obj: Any, idx: int) -> Tuple[int, int, str, int, int]:
                eval_msgs = prompt_builder.build_map_rerank_prompt(chunk_obj, request.query, chunk_index=idx)
                try:
                    raw_eval, p_tok, c_tok = await self.llm_service.generate(
                        messages=eval_msgs,
                        model=request.model,
                        temperature=0.1,
                        max_tokens=384,
                        authorization=authorization,
                    )
                    score, ans = self._parse_map_rerank_response(raw_eval, idx)
                    return idx, score, ans, p_tok, c_tok
                except Exception as e:
                    logger.warning(f"Map-rerank error on chunk {idx}: {e}")
                    return idx, 0, "", 0, 0

            rerank_tasks = [_eval_chunk(chunk_obj, i) for i, chunk_obj in enumerate(wrapped, start=1)]
            rerank_results = await asyncio.gather(*rerank_tasks)

            for _, _, _, p_tok, c_tok in rerank_results:
                prompt_tokens += p_tok
                completion_tokens += c_tok

            valid_evaluated = [
                (idx, score, ans) for idx, score, ans in [
                    (r[0], r[1], r[2]) for r in rerank_results
                ] if score > 0 and ans
            ]
            valid_evaluated.sort(key=lambda x: x[1], reverse=True)

            if valid_evaluated:
                winner_idx, top_score, winner_ans = valid_evaluated[0]
                answer = winner_ans
                winner_chunk_cands = [c for c in raw_citations if c.get("index") == winner_idx]
                other_cands = [c for c in raw_citations if c.get("index") != winner_idx]
                raw_citations = winner_chunk_cands + other_cands
            else:
                messages = [
                    {"role": "system", "content": default_system_prompt},
                    *generation_history,
                    {"role": "user", "content": effective_query},
                ]
                answer, prompt_tokens, completion_tokens = await self.llm_service.generate(
                    messages=messages,
                    model=request.model,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    authorization=authorization,
                )

        else:
            actual_strategy = "stuff"
            messages = [
                {"role": "system", "content": default_system_prompt},
                *generation_history,
                {"role": "user", "content": f"Câu hỏi của người dùng: {effective_query}\n(Trả lời bằng tiếng Việt:)"},
            ]
            answer, prompt_tokens, completion_tokens = await self.llm_service.generate(
                messages=messages,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                authorization=authorization,
            )

        deduped_raw_citations = _deduplicate_citations(raw_citations)
        attributed_raw_citations = _filter_attributed_citations(deduped_raw_citations, answer, strategy=actual_strategy)

        citation_dtos = [_build_citation_dto(c) for c in attributed_raw_citations]

        # Record LLM Generation Observability Metrics
        self.obs.record_stage_latency("llm_generate", time.perf_counter() - t_gen_0, tenant_id=tenant_id)
        self.obs.record_tokens(request.model, "prompt", prompt_tokens, tenant_id=tenant_id)
        self.obs.record_tokens(request.model, "completion", completion_tokens, tenant_id=tenant_id)

        # Anti-hallucination / Groundedness score (citations / retrieved chunks)
        groundedness_score = 0.0
        if citation_dtos and valid_candidates:
            groundedness_score = min(1.0, len(citation_dtos) / len(valid_candidates))
        self.obs.record_groundedness(groundedness_score, tenant_id=tenant_id)

        latency_ms = (time.time() - start_t) * 1000

        # 9. Session Persistence
        await self._save_session_turn(
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            query=request.query,
            answer=answer,
            citations=attributed_raw_citations,
            model=request.model,
            intent=f"QA_{actual_strategy.upper()}",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
        )

        top_cand_score = float(reranked_candidates[0].get("score", 0.0)) if reranked_candidates else 0.0
        telemetry_data = {
            "trace_id": f"tr_rag_{uuid.uuid4().hex[:8]}",
            "latency_ms": round(latency_ms, 2),
            "rerank_top1_score": round(top_cand_score, 4),
            "standalone_shield_activated": getattr(rewrite_decision, "is_standalone_shield_activated", False),
        }
        resp_dto = RagChatResponseDTO(
            answer=answer,
            model=request.model,
            citations=citation_dtos,
            latency_ms=round(latency_ms, 2),
            intent=f"QA_{actual_strategy.upper()}",
            combine_strategy=actual_strategy,
            session_id=session_id,
            status="success",
            escalation=None,
            telemetry=telemetry_data,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            pre_retrieval_tier=rewrite_decision.tier,
            pre_retrieval_latency_ms=round(rewrite_decision.latency_ms, 2),
            hyde_active=hyde_res.is_active,
            hypothetical_doc=hyde_res.hypothetical_document if hyde_res.is_active else None,
            hyde_latency_ms=round(hyde_res.latency_ms, 2),
        )

        # Store under the same key the lookup uses (requested strategy + standalone query).
        if self._is_cacheable(request):
            try:
                await self.cache_service.set(
                    response=resp_dto,
                    **self._cache_key_args(request, cache_query, tenant_id, user_role),
                )
            except Exception as cache_exc:
                logger.warning("Failed to write response cache: %s", cache_exc)

        return resp_dto

    async def stream_execute(
        self,
        request: RagChatRequestDTO,
        tenant_id: str = DEFAULT_TENANT_ID,
        user_id: str = "default_user",
        user_role: str = "user",
        authorization: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """SSE variant of execute(). Infrastructure failures end the stream with an explicit error event."""
        session_id = request.conversation_id or f"sess_{uuid.uuid4().hex[:12]}"
        request.conversation_id = session_id
        try:
            async for event in self._stream_execute_impl(request, tenant_id, user_id, user_role, authorization):
                yield event
        except INFRASTRUCTURE_ERRORS as exc:
            logger.error("RAG stream aborted by infrastructure failure: %s", exc)
            error_payload = {"error": type(exc).__name__, "message": "Dịch vụ tạm thời gián đoạn, vui lòng thử lại sau.", "session_id": session_id}
            yield f"event: error\ndata: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'status': 'service_unavailable'})}\n\n"

    async def _stream_execute_impl(
        self,
        request: RagChatRequestDTO,
        tenant_id: str,
        user_id: str,
        user_role: str,
        authorization: Optional[str],
    ) -> AsyncGenerator[str, None]:
        start_t = time.time()
        tenant_id = normalize_tenant_id(tenant_id)
        first_token_time: Optional[float] = None
        session_id = request.conversation_id or f"sess_{uuid.uuid4().hex[:12]}"
        self._truncate_query(request)

        history = await self._resolve_history(session_id, user_id, tenant_id, request.history)
        prepared = await self._prepare_query(request, history, tenant_id)
        rewrite_decision = prepared.rewrite
        standalone_query = prepared.standalone_query
        generation_history = prepared.generation_history
        effective_query = prepared.effective_query
        routing = prepared.routing

        accumulated_text = []

        # Handle AMBIGUOUS_SYMPTOM with Clarification Event in streaming (FR-RET-05 / EXEC-RAG-03)
        if routing.intent == QueryIntent.AMBIGUOUS_SYMPTOM:
            clarification_payload = dict(AMBIGUOUS_CLARIFICATION)
            clarification_text = AMBIGUOUS_CLARIFICATION_TEXT
            yield f"event: clarification\ndata: {json.dumps(clarification_payload, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'token': clarification_text, 'session_id': session_id}, ensure_ascii=False)}\n\n"
            latency_ms = (time.time() - start_t) * 1000
            await self._save_session_turn(
                session_id=session_id,
                user_id=user_id,
                tenant_id=tenant_id,
                query=request.query,
                answer=clarification_text,
                citations=[],
                model=request.model,
                intent="AMBIGUOUS_SYMPTOM",
                latency_ms=latency_ms,
            )
            yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'status': 'clarification_needed', 'clarification': clarification_payload, 'citations': [], 'total_latency_ms': round(latency_ms, 2)})}\n\n"
            return

        if routing.intent == QueryIntent.CHITCHAT:
            chitchat_messages = [
                {"role": "system", "content": CHITCHAT_SYSTEM_PROMPT},
                *history[-4:],
                {"role": "user", "content": request.query},
            ]
            async for token in self.llm_service.stream_generate(
                messages=chitchat_messages,
                model=request.model,
                temperature=0.7,
                max_tokens=request.max_tokens,
                authorization=authorization,
            ):
                if first_token_time is None:
                    first_token_time = time.time()
                accumulated_text.append(token)
                yield f"data: {json.dumps({'token': token, 'session_id': session_id})}\n\n"

            latency_ms = (time.time() - start_t) * 1000
            full_answer = "".join(accumulated_text)
            await self._save_session_turn(
                session_id=session_id,
                user_id=user_id,
                tenant_id=tenant_id,
                query=request.query,
                answer=full_answer,
                citations=[],
                model=request.model,
                intent="CHITCHAT",
                latency_ms=latency_ms,
            )
            ttft_ms = round((first_token_time - start_t) * 1000, 2) if first_token_time else None
            yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'citations': [], 'pre_retrieval_tier': rewrite_decision.tier, 'ttft_ms': ttft_ms})}\n\n"
            return

        # Check for Ad-hoc File Attachment in RAM (Ad-hoc RAG Streaming)
        if request.adhoc_context and request.adhoc_context.strip():
            adhoc_title = getattr(request, "adhoc_filename", None) or "Tài liệu đính kèm tạm thời"
            adhoc_excerpt = request.adhoc_context[:350].strip() + "..." if len(request.adhoc_context) > 350 else request.adhoc_context.strip()

            system_prompt = (
                f"Bạn là Trợ lý AI Chuyên nghiệp của AIP Platform. Người dùng đã đính kèm tài liệu cá nhân '{adhoc_title}'.\n"
                "Nhiệm vụ của bạn là đọc kỹ tài liệu đính kèm bên dưới và trả lời câu hỏi của người dùng một cách chính xác, trung thực, có cấu trúc rõ ràng (bảng biểu, gạch đầu dòng nếu phù hợp).\n"
                "Nếu thông tin không có trong tài liệu, hãy thành thật nêu rõ không có trong tài liệu.\n\n"
                f"=== NỘI DUNG TÀI LIỆU ĐÍNH KÈM ({adhoc_title}) ===\n"
                f"{request.adhoc_context[:16000]}\n"
                "=================================================="
            )

            adhoc_citations = [
                {
                    "index": 1,
                    "doc_id": "adhoc_attachment",
                    "title": adhoc_title,
                    "page_number": 1,
                    "score": 1.0,
                    "excerpt": adhoc_excerpt,
                }
            ]

            messages = [
                {"role": "system", "content": system_prompt},
                *history[-4:],
                {"role": "user", "content": request.query},
            ]

            async for token in self.llm_service.stream_generate(
                messages=messages,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                authorization=authorization,
            ):
                if first_token_time is None:
                    first_token_time = time.time()
                accumulated_text.append(token)
                yield f"data: {json.dumps({'token': token, 'session_id': session_id})}\n\n"

            latency_ms = (time.time() - start_t) * 1000
            full_answer = "".join(accumulated_text)
            await self._save_session_turn(
                session_id=session_id,
                user_id=user_id,
                tenant_id=tenant_id,
                query=request.query,
                answer=full_answer,
                citations=adhoc_citations,
                model=request.model,
                intent="ADHOC_QA",
                latency_ms=latency_ms,
            )

            ttft_ms = round((first_token_time - start_t) * 1000, 2) if first_token_time else None
            yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'citations': adhoc_citations, 'pre_retrieval_tier': rewrite_decision.tier, 'ttft_ms': ttft_ms})}\n\n"
            return

        # 3.5. Multi-Hop Reasoning & Iterative RAG (Slide 94-103)
        multi_hop_flag = getattr(request, "multi_hop", None)
        should_run_multihop = False
        if multi_hop_flag is True:
            should_run_multihop = True
        elif multi_hop_flag is None:
            should_run_multihop = query_decomposer.should_decompose(standalone_query)

        if should_run_multihop:
            decomp = await query_decomposer.decompose(
                standalone_query,
                llm_port=self.llm_service,
                model=request.model,
                timeout=0.8,
            )
            if decomp.is_multi_hop and len(decomp.sub_queries) >= 2:
                async for event in self._stream_execute_multi_hop(
                    request=request,
                    standalone_query=standalone_query,
                    decomp=decomp,
                    history=generation_history,
                    session_id=session_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    user_role=user_role,
                    authorization=authorization,
                    start_t=start_t,
                    rewrite_decision=rewrite_decision,
                ):
                    yield event
                return

        # 4-6. HyDE + hybrid retrieval + cross-encoder rerank + confidence gate (shared stage)
        outcome = await self._retrieve_and_gate(request, prepared, tenant_id, user_role)
        hyde_res = outcome.hyde
        top_cand_score = outcome.top_score

        if outcome.refused:
            logger.info(
                "Anti-Hallucination Gatekeeper (RER-RAG-02): top score %.4f < %.2f; refusing stream.",
                top_cand_score,
                outcome.threshold,
            )
            latency_ms = (time.time() - start_t) * 1000
            yield f"data: {json.dumps({'token': REFUSAL_MESSAGE, 'session_id': session_id})}\n\n"
            escalation_payload = await self._record_refusal(
                request, session_id, tenant_id, user_id, top_cand_score, latency_ms
            )
            yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'status': 'escalation_required', 'escalation': escalation_payload, 'citations': [], 'circuit_breaker_triggered': True, 'is_refusal': True, 'pre_retrieval_tier': rewrite_decision.tier, 'ttft_ms': round(latency_ms, 2), 'total_latency_ms': round(latency_ms, 2), 'trace_id': f'tr_rag_{uuid.uuid4().hex[:8]}', 'hyde_active': hyde_res.is_active, 'rerank_top1_score': round(top_cand_score, 4), 'standalone_shield_activated': getattr(rewrite_decision, 'is_standalone_shield_activated', False)})}\n\n"
            return

        # Grounded Prompt Assembly: Apply Lost-in-the-Middle U-shaped ordering
        reordered_candidates = prompt_builder.reorder_lost_in_middle(outcome.valid)
        wrapped = [CandidateWrapper(c) for c in reordered_candidates]
        raw_citations, default_system_prompt = prompt_builder.build_context_and_citations(wrapped, query=request.query)

        actual_strategy = self._resolve_combine_strategy(
            getattr(request, "combine_strategy", None),
            request.query,
            wrapped,
        )

        if actual_strategy == "map_reduce" and len(wrapped) >= 2:
            async def _map_chunk(chunk_obj: Any, idx: int) -> Tuple[int, str]:
                map_msgs = prompt_builder.build_map_prompt(chunk_obj, request.query, chunk_index=idx)
                try:
                    summary, _, _ = await self.llm_service.generate(
                        messages=map_msgs,
                        model=request.model,
                        temperature=0.1,
                        max_tokens=384,
                        authorization=authorization,
                    )
                    return idx, summary.strip()
                except Exception as e:
                    logger.warning(f"Map phase error on chunk {idx}: {e}")
                    return idx, ""

            map_tasks = [_map_chunk(chunk_obj, i) for i, chunk_obj in enumerate(wrapped, start=1)]
            map_results = await asyncio.gather(*map_tasks)

            valid_summaries = []
            for idx, s in map_results:
                s_clean = s.strip()
                if (
                    s_clean
                    and "KHÔNG_CÓ_THÔNG_TIN_LIÊN_QUAN" not in s_clean
                    and "NO_RELEVANT_INFO" not in s_clean
                ):
                    valid_summaries.append(f"[{idx}] {s_clean}")

            if valid_summaries:
                reduce_msgs = prompt_builder.build_reduce_prompt(
                    query=request.query,
                    map_summaries=valid_summaries,
                    history=generation_history,
                )
                async for token in self.llm_service.stream_generate(
                    messages=reduce_msgs,
                    model=request.model,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    authorization=authorization,
                ):
                    if first_token_time is None:
                        first_token_time = time.time()
                    accumulated_text.append(token)
                    yield f"data: {json.dumps({'token': token, 'session_id': session_id})}\n\n"
            else:
                # FR-GEN-02: Zero-context LLM calls strictly forbidden. Return standard refusal.
                logger.info("Map-reduce streaming map phase produced no valid facts; returning standard refusal.")
                yield f"data: {json.dumps({'token': REFUSAL_MESSAGE, 'session_id': session_id})}\n\n"
                accumulated_text.append(REFUSAL_MESSAGE)
                raw_citations = []

        elif actual_strategy == "refine" and len(wrapped) >= 2:
            init_msgs = prompt_builder.build_refine_initial_prompt(
                chunk=wrapped[0],
                query=request.query,
                chunk_index=1,
                history=generation_history,
            )
            current_answer, _, _ = await self.llm_service.generate(
                messages=init_msgs,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                authorization=authorization,
            )

            for idx in range(1, len(wrapped) - 1):
                step_msgs = prompt_builder.build_refine_step_prompt(
                    existing_answer=current_answer,
                    next_chunk=wrapped[idx],
                    query=request.query,
                    chunk_index=idx + 1,
                )
                refined, _, _ = await self.llm_service.generate(
                    messages=step_msgs,
                    model=request.model,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    authorization=authorization,
                )
                if refined.strip() and "KHÔNG_CÓ_THÔNG_TIN_LIÊN_QUAN" not in refined:
                    current_answer = refined.strip()

            last_idx = len(wrapped) - 1
            final_step_msgs = prompt_builder.build_refine_step_prompt(
                existing_answer=current_answer,
                next_chunk=wrapped[last_idx],
                query=request.query,
                chunk_index=last_idx + 1,
            )
            async for token in self.llm_service.stream_generate(
                messages=final_step_msgs,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                authorization=authorization,
            ):
                if first_token_time is None:
                    first_token_time = time.time()
                accumulated_text.append(token)
                yield f"data: {json.dumps({'token': token, 'session_id': session_id})}\n\n"

        elif actual_strategy == "map_rerank" and len(wrapped) >= 1:
            async def _eval_chunk_stream(chunk_obj: Any, idx: int) -> Tuple[int, int, str]:
                eval_msgs = prompt_builder.build_map_rerank_prompt(chunk_obj, request.query, chunk_index=idx)
                try:
                    raw_eval, _, _ = await self.llm_service.generate(
                        messages=eval_msgs,
                        model=request.model,
                        temperature=0.1,
                        max_tokens=384,
                        authorization=authorization,
                    )
                    score, ans = self._parse_map_rerank_response(raw_eval, idx)
                    return idx, score, ans
                except Exception as e:
                    logger.warning(f"Map-rerank stream eval error on chunk {idx}: {e}")
                    return idx, 0, ""

            rerank_tasks = [_eval_chunk_stream(chunk_obj, i) for i, chunk_obj in enumerate(wrapped, start=1)]
            rerank_results = await asyncio.gather(*rerank_tasks)

            valid_evaluated = [
                (idx, score, ans) for idx, score, ans in rerank_results if score > 0 and ans
            ]
            valid_evaluated.sort(key=lambda x: x[1], reverse=True)

            if valid_evaluated:
                winner_idx, top_score, winner_ans = valid_evaluated[0]
                first_token_time = time.time()
                words = winner_ans.split(" ")
                for i, w in enumerate(words):
                    part = w + (" " if i < len(words) - 1 else "")
                    accumulated_text.append(part)
                    yield f"data: {json.dumps({'token': part, 'session_id': session_id})}\n\n"
                    await asyncio.sleep(0.01)

                winner_chunk_cands = [c for c in raw_citations if c.get("index") == winner_idx]
                other_cands = [c for c in raw_citations if c.get("index") != winner_idx]
                raw_citations = winner_chunk_cands + other_cands
            else:
                messages = [
                    {"role": "system", "content": default_system_prompt},
                    *generation_history,
                    {"role": "user", "content": effective_query},
                ]
                async for token in self.llm_service.stream_generate(
                    messages=messages,
                    model=request.model,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    authorization=authorization,
                ):
                    if first_token_time is None:
                        first_token_time = time.time()
                    accumulated_text.append(token)
                    yield f"data: {json.dumps({'token': token, 'session_id': session_id})}\n\n"

        else:
            actual_strategy = "stuff"
            messages = [
                {"role": "system", "content": default_system_prompt},
                *generation_history,
                {"role": "user", "content": f"Câu hỏi của người dùng: {effective_query}\n(Trả lời bằng tiếng Việt:)"},
            ]
            async for token in self.llm_service.stream_generate(
                messages=messages,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                authorization=authorization,
            ):
                if first_token_time is None:
                    first_token_time = time.time()
                accumulated_text.append(token)
                yield f"data: {json.dumps({'token': token, 'session_id': session_id})}\n\n"

        deduped_raw_citations = _deduplicate_citations(raw_citations)
        latency_ms = (time.time() - start_t) * 1000
        full_answer = "".join(accumulated_text)
        attributed_raw_citations = _filter_attributed_citations(deduped_raw_citations, full_answer, strategy=actual_strategy)

        await self._save_session_turn(
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            query=request.query,
            answer=full_answer,
            citations=attributed_raw_citations,
            model=request.model,
            intent=f"QA_{actual_strategy.upper()}",
            latency_ms=latency_ms,
        )

        citation_dtos = [_build_citation_dto(c).model_dump() for c in attributed_raw_citations]
        ttft_ms = round((first_token_time - start_t) * 1000, 2) if first_token_time else None
        yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'status': 'success', 'escalation': None, 'citations': citation_dtos, 'combine_strategy': actual_strategy, 'pre_retrieval_tier': rewrite_decision.tier, 'pre_retrieval_latency_ms': round(rewrite_decision.latency_ms, 2), 'ttft_ms': ttft_ms, 'total_latency_ms': round(latency_ms, 2), 'trace_id': f'tr_rag_{uuid.uuid4().hex[:8]}', 'hyde_active': hyde_res.is_active, 'hypothetical_doc': hyde_res.hypothetical_document if hyde_res.is_active else None})}\n\n"

    async def _save_session_turn(
        self,
        session_id: str,
        user_id: str,
        tenant_id: str,
        query: str,
        answer: str,
        citations: List[Dict[str, Any]],
        model: Optional[str] = None,
        intent: Optional[str] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        latency_ms: float = 0.0,
    ) -> None:
        try:
            now = time.time()
            user_msg = {
                "message_id": f"msg_{uuid.uuid4().hex[:12]}",
                "role": "user",
                "content": query,
                "timestamp": now,
                "citations": [],
                "model": model,
                "intent": intent,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": 0,
                "latency_ms": 0.0,
            }
            assistant_msg = {
                "message_id": f"msg_{uuid.uuid4().hex[:12]}",
                "role": "assistant",
                "content": answer,
                "timestamp": now,
                "citations": citations,
                "model": model,
                "intent": intent,
                "prompt_tokens": 0,
                "completion_tokens": completion_tokens,
                "latency_ms": round(latency_ms, 2),
            }

            if hasattr(self.session_repo, "append_turn"):
                await self.session_repo.append_turn(
                    session_id=session_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    user_msg=user_msg,
                    assistant_msg=assistant_msg,
                )
            else:
                existing = await self.session_repo.get_session(session_id, user_id, tenant_id)
                messages = list(existing.get("messages", [])) if existing else []
                title = existing.get("title", "") if existing else ""
                if not title:
                    title = query[:40] + ("..." if len(query) > 40 else "")

                messages.append(user_msg)
                messages.append(assistant_msg)

                await self.session_repo.save_session(
                    session_id=session_id,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    title=title,
                    messages=messages,
                )
        except Exception as exc:
            logger.warning("Could not persist session %s: %s", session_id, exc)
