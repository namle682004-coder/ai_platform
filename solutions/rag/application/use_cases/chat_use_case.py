"""
Enterprise RAG Chat Orchestration Use Case.

Pipeline per turn (Advanced / Modular RAG):
  1. Query analysis — one LLM call rewrites the message into a standalone query using the
     conversation history and detects the intent (document question, support request, feedback,
     contact details, ticket status, greeting, out-of-scope per tenant policy).
  2. Hybrid retrieval — dense + BM25 with RRF fusion over a wide candidate pool (optional HyDE).
  3. Cross-encoder reranking of the whole pool, plus whole-document expansion of the best documents.
  4. Evidence gate — refuse without generation only when neither the reranker nor IDF-weighted
     keyword coverage finds support; unknown identifiers are answered deterministically.
  5. Adaptive context — every passage close to the best one, within a budget, in document order.
  6. Generation with a Self-RAG style refusal sentence, then structural post-processing
     (source footer, citation renumbering, suggestions) for both streaming and non-streaming.
"""

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from ...domain.exceptions import EmbeddingError, LLMGenerationError, RerankerError, VectorStoreError
from ...domain.entities import (
    DEFAULT_TENANT_ID,
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
from ..components.answer_postprocessor import (
    AnswerStreamFilter,
    SanitizeContext,
    build_sources_footer,
    build_suggestions,
    collect_image_urls,
    remap_citations,
    sanitize_answer,
)
from ..components.context_selector import (
    build_document_card,
    candidate_key,
    document_card_candidate,
    outline_from_candidates,
    payload_of,
    select_adaptive_context,
)
from ..components.conversation_policy import (
    SupportResponder,
    last_ticket_in_history,
    last_unanswered_question,
)
from ..components.hyde_generator import HyDEResult, hyde_generator
from ..components.intent_classifier import intent_classifier
from ..components.lexical_evidence import (
    candidate_text,
    has_vietnamese_diacritics,
    nearest_existing_codes,
    restore_diacritics_from_corpus,
    score_evidence,
    unique_in_order,
)
from ..components.prompt_builder import (
    ANSWER_RULES,
    PROCEDURE_RULES,
    REFUSAL_MESSAGE,
    prompt_builder,
)
from ..components.query_analyzer import Intent, QueryAnalysis, QueryAnalyzer
from ..components.query_decomposer import DecomposedQuery, query_decomposer
from ..components.query_rewriter import RewrittenQuery, query_rewriter
from ..components.reranker import cross_encoder_reranker
from ..dtos import (
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
class _TurnPlan:
    """Everything decided before generation for one chat turn."""

    analysis: QueryAnalysis
    rewrite: RewrittenQuery
    standalone_query: str
    kind: str = "direct"  # "direct" | "generate" | "multihop" | "clarification"
    intent: str = "QA"
    answer: str = ""
    status: str = "success"
    is_refusal: bool = False
    escalation: Optional[Dict[str, Any]] = None
    generation_history: List[Dict[str, str]] = field(default_factory=list)
    hyde: Optional[HyDEResult] = None
    decomp: Optional[DecomposedQuery] = None
    top_score: float = 0.0
    gate_latency_ms: float = 0.0
    titles: List[str] = field(default_factory=list)
    outline: List[str] = field(default_factory=list)
    context_chunks: List[Dict[str, Any]] = field(default_factory=list)
    suggestion_pool: List[Dict[str, Any]] = field(default_factory=list)
    wrapped: List[Any] = field(default_factory=list)
    raw_citations: List[Dict[str, Any]] = field(default_factory=list)
    system_prompt: str = ""
    user_content: str = ""
    strategy: str = "stuff"
    sanitize_ctx: Optional[SanitizeContext] = None


INFRASTRUCTURE_ERRORS = (EmbeddingError, RerankerError, VectorStoreError, LLMGenerationError)
# Combine strategies whose final answer is synthesised over several passes and cites by original index.
SYNTHESIS_STRATEGIES = ("map_reduce", "refine")


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
        query_analyzer: Optional[QueryAnalyzer] = None,
        support_responder: Optional[SupportResponder] = None,
    ) -> None:
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        self.llm_service = llm_service
        self.session_repo = session_repo
        self.cache_service = cache_service or NullCacheAdapter()
        self.reranker_service = reranker_service or cross_encoder_reranker
        self.obs = observability_service or NullObservabilityAdapter()
        self.query_analyzer = query_analyzer or QueryAnalyzer(
            out_of_scope_policy=rag_settings.out_of_scope_policy,
            timeout=rag_settings.query_analysis_timeout,
            history_messages=rag_settings.query_analysis_history_turns,
            enabled=rag_settings.query_analysis_enabled,
        )
        self.support = support_responder or SupportResponder(
            hotline=rag_settings.escalation_hotline,
            support_method=rag_settings.escalation_support_method,
            instructions=rag_settings.escalation_instructions,
        )

    async def _build_and_persist_escalation(
        self,
        session_id: str,
        tenant_id: str,
        user_id: str,
        query: str,
        top1_score: float,
        reason: str = "out_of_domain_or_insufficient_evidence",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generates the escalation payload and persists the ticket (unanswered question, handoff
        request, callback number or feedback) into MongoDB (RER-RAG-02).
        """
        ticket_id = f"ticket_{uuid.uuid4().hex[:10]}"
        ticket_record = {
            "ticket_id": ticket_id,
            "session_id": session_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "query": query,
            "top1_score": round(top1_score, 4),
            "reason": reason,
            "created_at": time.time(),
            **(extra or {}),
        }
        if hasattr(self.session_repo, "record_escalation_ticket"):
            try:
                await self.session_repo.record_escalation_ticket(ticket_record)
            except Exception as exc:
                logger.warning("Could not persist escalation ticket: %s", exc)

        return {
            "status": "escalation_required",
            "reason": reason,
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
        if not candidates:
            return []
        # A hop passage counts if the reranker supports it or it shares content words with the
        # sub-query; the final synthesis prompt still verifies every fact against the passages.
        reranked = await self.reranker_service.arerank(
            query=query_text,
            candidates=candidates,
            top_n=len(candidates),
            min_threshold=0.0,
        )
        evidence = score_evidence(query_text, reranked)
        scored = []
        for i, c in enumerate(reranked):
            rerank = float(c.get("score", 0.0) or 0.0)
            per = evidence.per_candidate[i]
            if rerank >= 0.20 or per.matched_terms or per.identifier_hits:
                scored.append((max(rerank, per.coverage), c))
        scored.sort(key=lambda sc: sc[0], reverse=True)
        return [c for _, c in scored[: min(target_top_k, 3)]]

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
    # Shared helpers
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

    @staticmethod
    def _effective_threshold(request: RagChatRequestDTO) -> float:
        """The client's reranker threshold is used as-is (0.0 disables the evidence gate)."""
        return max(0.0, float(request.similarity_threshold or 0.0))

    # ------------------------------------------------------------------
    # Turn planning: query analysis -> routing -> retrieval -> evidence gate -> context
    # ------------------------------------------------------------------

    async def _resolve_history(
        self,
        session_id: str,
        user_id: str,
        tenant_id: str,
        explicit_history: Optional[List[Dict[str, str]]],
    ) -> List[Dict[str, str]]:
        window = max(2, int(rag_settings.history_window_messages))
        if explicit_history:
            return list(explicit_history)[-window:]

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
                item = {"role": role, "content": content}
                if msg.get("standalone"):
                    item["standalone"] = msg["standalone"]
                if msg.get("intent"):
                    item["intent"] = msg["intent"]
                formatted.append(item)
        return formatted[-window:]

    @staticmethod
    def _llm_history(history: List[Dict[str, str]], turns: int = 4, max_chars: int = 800) -> List[Dict[str, str]]:
        """Role/content-only view of the history for chat completions (extra keys are not sent)."""
        out = []
        for m in history[-turns:]:
            content = m.get("content") or ""
            if m.get("role") == "assistant" and len(content) > max_chars:
                content = content[:max_chars] + "…"
            out.append({"role": m.get("role", "user"), "content": content})
        return out

    async def _record_ticket(
        self,
        session_id: str,
        tenant_id: str,
        user_id: str,
        query: str,
        reason: str,
        top1_score: float = 0.0,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        """Persists a support ticket and returns (ticket_id, escalation payload for the API)."""
        payload = await self._build_and_persist_escalation(
            session_id=session_id,
            tenant_id=tenant_id,
            user_id=user_id,
            query=query,
            top1_score=top1_score,
            reason=reason,
            extra=extra,
        )
        return payload["escalation_data"]["ticket_id"], payload

    async def _search_candidates(
        self,
        request: RagChatRequestDTO,
        query_text: str,
        sparse_query: str,
        tenant_id: str,
        user_role: str,
    ) -> Tuple[List[Dict[str, Any]], HyDEResult]:
        """Hybrid dense + BM25 retrieval (optionally HyDE-fused) of a wide candidate pool for reranking."""
        enable_hyde = getattr(request, "enable_hyde", None)
        if enable_hyde is None and not rag_settings.hyde_auto_enabled:
            enable_hyde = False
        hyde_res: HyDEResult = await hyde_generator.generate_hypothetical_doc(
            query=query_text,
            llm_port=self.llm_service,
            model=request.model,
            enable_hyde=enable_hyde,
            timeout=1.0,
        )
        if hyde_res.is_active and hyde_res.hypothetical_document:
            query_vec, hyde_vec = await asyncio.gather(
                self.embedding_service.get_embedding(query_text),
                self.embedding_service.get_embedding(hyde_res.hypothetical_document),
            )
            query_vector = hyde_generator.fuse_embeddings(query_vec, hyde_vec, alpha=0.4)
        else:
            query_vector = await self.embedding_service.get_embedding(query_text)

        fetch_k = min(
            max((request.top_k or 4) * rag_settings.hybrid_fetch_multiplier, 32),
            rag_settings.hybrid_fetch_ceiling,
        )
        t0 = time.perf_counter()
        candidates = await self.vector_store.search(
            query_vector=query_vector,
            tenant_id=tenant_id,
            query_text=sparse_query or query_text,
            user_role=user_role,
            department=request.department,
            doc_ids=request.doc_ids,
            top_k=fetch_k,
            hybrid=True,
            as_of_date=request.as_of_date,
        )
        self.obs.record_stage_latency("retrieval_hybrid", time.perf_counter() - t0, tenant_id=tenant_id)
        self.obs.record_retrieval("hybrid", len(candidates), tenant_id=tenant_id)
        return list(candidates or []), hyde_res

    async def _expand_documents(
        self,
        pool: List[Dict[str, Any]],
        scores: Dict[str, float],
        tenant_id: str,
        user_role: str,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Reads every chunk of the best-scoring documents so sections and headers are complete."""
        fetch_chunks = getattr(self.vector_store, "fetch_document_chunks", None)
        if rag_settings.doc_expansion_max_chunks <= 0 or fetch_chunks is None:
            return {}
        doc_order: List[str] = []
        for c in sorted(pool, key=lambda c: scores.get(candidate_key(c), 0.0), reverse=True):
            doc_id = str(payload_of(c).get("doc_id") or "")
            if doc_id and doc_id not in doc_order:
                doc_order.append(doc_id)
            if len(doc_order) >= rag_settings.doc_expansion_max_docs:
                break
        if not doc_order:
            return {}
        fetched = await asyncio.gather(
            *[
                fetch_chunks(
                    doc_id=d, tenant_id=tenant_id, user_role=user_role, limit=rag_settings.doc_expansion_max_chunks + 1
                )
                for d in doc_order
            ],
            return_exceptions=True,
        )
        out: Dict[str, List[Dict[str, Any]]] = {}
        for doc_id, chunks in zip(doc_order, fetched, strict=True):
            if isinstance(chunks, Exception) or not chunks:
                continue
            if len(chunks) > rag_settings.doc_expansion_max_chunks:
                continue  # too large to read whole; rely on retrieval only
            out[doc_id] = list(chunks)
        return out

    async def _plan_turn(
        self,
        request: RagChatRequestDTO,
        history: List[Dict[str, str]],
        tenant_id: str,
        user_id: str,
        user_role: str,
        session_id: str,
        authorization: Optional[str],
    ) -> "_TurnPlan":
        # 1. Query analysis: conversational rewriting + intent detection (one LLM call).
        t0 = time.perf_counter()
        analysis = await self.query_analyzer.analyze(
            request.query, history, self.llm_service, request.model, authorization=authorization
        )
        self.obs.record_stage_latency("query_analysis", time.perf_counter() - t0, tenant_id=tenant_id)
        standalone = analysis.standalone_query or request.query
        rewrite: RewrittenQuery = await query_rewriter.rewrite_advanced(standalone, None, llm_port=None)
        plan = _TurnPlan(analysis=analysis, rewrite=rewrite, standalone_query=rewrite.text or standalone)
        plan.generation_history = [] if (analysis.new_topic or not history) else self._llm_history(history)

        # 2. Non-document turns get deterministic support replies.
        if not analysis.is_document_question:
            return await self._plan_support_turn(plan, request, history, tenant_id, user_id, user_role, session_id)

        if intent_classifier.is_ambiguous_symptom(plan.standalone_query):
            plan.kind = "clarification"
            return plan

        multi_hop_flag = getattr(request, "multi_hop", None)
        if multi_hop_flag is True or (multi_hop_flag is None and query_decomposer.should_decompose(plan.standalone_query)):
            decomp = await query_decomposer.decompose(
                plan.standalone_query, llm_port=self.llm_service, model=request.model, timeout=0.8
            )
            if decomp.is_multi_hop and len(decomp.sub_queries) >= 2:
                plan.kind = "multihop"
                plan.decomp = decomp
                return plan

        await self._plan_document_turn(plan, request, tenant_id, user_id, user_role, session_id)
        return plan

    async def _plan_support_turn(
        self,
        plan: "_TurnPlan",
        request: RagChatRequestDTO,
        history: List[Dict[str, str]],
        tenant_id: str,
        user_id: str,
        user_role: str,
        session_id: str,
    ) -> "_TurnPlan":
        analysis = plan.analysis
        plan.kind = "direct"
        if analysis.intent == Intent.GREETING:
            plan.intent, plan.answer = "CHITCHAT", self.support.greeting()
        elif analysis.intent == Intent.OUT_OF_SCOPE:
            plan.intent, plan.answer = "OUT_OF_SCOPE", self.support.out_of_scope(analysis.out_of_scope_category)
        elif analysis.intent == Intent.SUPPORT_REQUEST:
            ticket_id, escalation = await self._record_ticket(
                session_id, tenant_id, user_id, request.query, reason="handoff_request"
            )
            plan.intent, plan.status, plan.escalation = "ESCALATION", "escalation_required", escalation
            plan.answer = self.support.handoff(ticket_id)
        elif analysis.intent == Intent.CONTACT_INFO:
            question = last_unanswered_question(history)
            ticket_id, escalation = await self._record_ticket(
                session_id, tenant_id, user_id, question or request.query, reason="callback_request",
                extra={"contact_phone": analysis.phone, "related_ticket": last_ticket_in_history(history)},
            )
            plan.intent, plan.status, plan.escalation = "CONTACT_CAPTURED", "escalation_required", escalation
            plan.answer = self.support.contact_saved(analysis.phone or request.query, ticket_id, question)
        elif analysis.intent == Intent.DECLINE_CONTACT:
            plan.intent, plan.answer = "SUPPORT_INFO", self.support.contact_declined()
        elif analysis.intent == Intent.TICKET_STATUS:
            plan.intent = "TICKET_STATUS"
            plan.answer = self.support.ticket_status(last_ticket_in_history(history), last_unanswered_question(history))
        else:
            # FEEDBACK / UNCLEAR: show what the documents contain so the user can rephrase.
            titles, outline = await self._documents_overview(request, history, tenant_id, user_role)
            if analysis.intent == Intent.FEEDBACK:
                ticket_id, escalation = await self._record_ticket(
                    session_id, tenant_id, user_id, request.query, reason="user_feedback",
                    extra={"previous_question": last_unanswered_question(history) or self._last_user_question(history)},
                )
                plan.intent, plan.escalation = "FEEDBACK", escalation
                plan.answer = self.support.feedback(ticket_id, titles, outline)
            else:
                plan.intent, plan.answer = "CLARIFICATION", self.support.clarify(titles, outline)
        return plan

    @staticmethod
    def _last_user_question(history: List[Dict[str, str]]) -> Optional[str]:
        for m in reversed(history or []):
            if m.get("role") == "user" and (m.get("content") or "").strip():
                return m.get("content")
        return None

    async def _documents_overview(
        self,
        request: RagChatRequestDTO,
        history: List[Dict[str, str]],
        tenant_id: str,
        user_role: str,
    ) -> Tuple[List[str], List[str]]:
        """Titles and top-level sections of the documents closest to the conversation."""
        probe = self._last_user_question(history) or request.query
        try:
            candidates, _ = await self._search_candidates(request, probe, probe, tenant_id, user_role)
        except INFRASTRUCTURE_ERRORS as exc:
            logger.warning("Overview retrieval failed: %s", exc)
            return [], []
        titles = unique_in_order(str(payload_of(c).get("title") or "") for c in candidates[:8])[:2]
        return titles, outline_from_candidates(candidates[:16])

    async def _plan_document_turn(
        self,
        plan: "_TurnPlan",
        request: RagChatRequestDTO,
        tenant_id: str,
        user_id: str,
        user_role: str,
        session_id: str,
    ) -> None:
        analysis = plan.analysis
        query = plan.standalone_query
        candidates, plan.hyde = await self._search_candidates(
            request, query, plan.rewrite.sparse_query or query, tenant_id, user_role
        )

        # Unaccented queries are re-accented from the vocabulary of the retrieved passages.
        rerank_query = query
        if candidates and not has_vietnamese_diacritics(query):
            rerank_query = restore_diacritics_from_corpus(query, (candidate_text(c) for c in candidates))

        t_rerank = time.perf_counter()
        reranked = await self.reranker_service.arerank(
            query=rerank_query, candidates=candidates, top_n=max(1, len(candidates)), min_threshold=0.0
        ) if candidates else []
        self.obs.record_stage_latency("rerank", time.perf_counter() - t_rerank, tenant_id=tenant_id)
        rerank_scores = {candidate_key(c): float(c.get("score", 0.0) or 0.0) for c in reranked}
        plan.top_score = max(rerank_scores.values(), default=0.0)

        # Whole-document expansion for the best documents (sections, headers).
        pool: List[Dict[str, Any]] = list(reranked)
        # Evidence is measured on the user's own wording; acronym expansions only widen retrieval recall.
        lexical_query = rerank_query
        prelim = score_evidence(lexical_query, pool) if pool else None
        prelim_scores = {
            candidate_key(c): max(rerank_scores.get(candidate_key(c), 0.0), prelim.coverage_of(i) if prelim else 0.0)
            for i, c in enumerate(pool)
        }
        expanded = await self._expand_documents(pool, prelim_scores, tenant_id, user_role) if pool else {}
        known = {(str(payload_of(c).get("doc_id")), int(payload_of(c).get("chunk_index", 0) or 0)) for c in pool}
        for chunks in expanded.values():
            for c in chunks:
                k = (str(payload_of(c).get("doc_id")), int(payload_of(c).get("chunk_index", 0) or 0))
                if k not in known:
                    known.add(k)
                    pool.append(c)

        t_gate = time.perf_counter()
        evidence = score_evidence(lexical_query, pool) if pool else None
        blended: Dict[str, float] = {}
        for i, c in enumerate(pool):
            r = rerank_scores.get(candidate_key(c), 0.0)
            lex = evidence.coverage_of(i) if evidence else 0.0
            blended[candidate_key(c)] = max(r, lex) + 0.25 * min(r, lex)
        best_lexical = evidence.best_coverage if evidence else 0.0
        texts = [candidate_text(c) for c in pool]
        plan.titles = unique_in_order(str(payload_of(c).get("title") or "") for c in sorted(
            pool, key=lambda c: blended.get(candidate_key(c), 0.0), reverse=True)[:6])[:2]
        plan.outline = outline_from_candidates(
            [c for c in pool if str(payload_of(c).get("doc_id")) in set(expanded) or c in reranked[:16]]
        )

        # 3. Evidence gate. Identifiers the documents do not contain are answered deterministically.
        if evidence and evidence.query_identifiers and len(evidence.missing_identifiers) == len(evidence.query_identifiers):
            code = evidence.missing_identifiers[0]
            scope, codes = nearest_existing_codes(code, texts)
            plan.kind, plan.intent = "direct", "IDENTIFIER_NOT_FOUND"
            plan.answer = self.support.identifier_not_found(code, scope, codes)
            plan.gate_latency_ms = (time.perf_counter() - t_gate) * 1000
            return

        threshold = self._effective_threshold(request)
        no_evidence = (
            not pool
            or (
                threshold > 0.0
                and plan.top_score < min(threshold, rag_settings.gate_min_rerank_score)
                and best_lexical < rag_settings.gate_min_lexical_coverage
                and not analysis.about_document
            )
        )
        plan.gate_latency_ms = (time.perf_counter() - t_gate) * 1000
        self.obs.record_stage_latency("gatekeeper", plan.gate_latency_ms / 1000, tenant_id=tenant_id)
        if no_evidence:
            logger.info(
                "Evidence gate: no support (rerank %.3f, lexical %.3f); refusing without generation.",
                plan.top_score, best_lexical,
            )
            await self._make_refusal_plan(plan, request, tenant_id, user_id, session_id)
            return

        # 4. Adaptive context: every passage close to the best one, in document order.
        selection = select_adaptive_context(
            pool,
            blended,
            relative_cutoff=(
                rag_settings.context_list_relative_cutoff if analysis.wants_list else rag_settings.context_relative_cutoff
            ),
            char_budget=rag_settings.context_char_budget,
            min_k=max(1, request.top_k or 4),
            max_k=rag_settings.context_max_chunks,
        )
        chosen = list(selection.chunks)
        if analysis.about_document:
            for doc_id in unique_in_order(str(payload_of(c).get("doc_id") or "") for c in chosen)[:2]:
                doc_chunks = expanded.get(doc_id) or [c for c in pool if str(payload_of(c).get("doc_id")) == doc_id]
                card = build_document_card(doc_chunks)
                if card:
                    chosen.insert(0, document_card_candidate(card))

        plan.kind = "generate"
        plan.context_chunks = chosen
        plan.suggestion_pool = chosen + [
            c for c in sorted(pool, key=lambda c: blended.get(candidate_key(c), 0.0), reverse=True)[:12]
            if c not in chosen
        ]
        plan.wrapped = [CandidateWrapper(c) for c in chosen]
        plan.raw_citations, plan.system_prompt = prompt_builder.build_context_and_citations(
            plan.wrapped, query=query
        )
        user_content = f"Câu hỏi của người dùng: {request.query}"
        if query.strip() != request.query.strip():
            user_content += f"\n(Câu hỏi đầy đủ theo ngữ cảnh hội thoại: {query})"
        if analysis.challenge:
            user_content += "\n(Người dùng đang phản bác hoặc chỉ ra thiếu sót của câu trả lời trước: đối chiếu lại tài liệu.)"
        plan.user_content = user_content + "\n(Trả lời bằng tiếng Việt.)"
        plan.sanitize_ctx = SanitizeContext(
            titles=unique_in_order(str(c.get("title") or "") for c in plan.raw_citations),
            allowed_image_urls=collect_image_urls(c.get("text", "") for c in plan.raw_citations),
            prompt_text=ANSWER_RULES + "\n" + PROCEDURE_RULES,
            valid_indices={int(c.get("index", 0)) for c in plan.raw_citations},
        )

    async def _make_refusal_plan(
        self,
        plan: "_TurnPlan",
        request: RagChatRequestDTO,
        tenant_id: str,
        user_id: str,
        session_id: str,
    ) -> None:
        ticket_id, escalation = await self._record_ticket(
            session_id, tenant_id, user_id, request.query,
            reason="out_of_domain_or_insufficient_evidence", top1_score=plan.top_score,
        )
        plan.kind, plan.intent, plan.status = "direct", "REFUSAL", "escalation_required"
        plan.is_refusal, plan.escalation = True, escalation
        plan.answer = self.support.not_found(ticket_id, plan.titles, plan.outline)

    # ------------------------------------------------------------------
    # Generation (stuff by default; explicit combine strategies kept)
    # ------------------------------------------------------------------

    def _resolve_combine_strategy(
        self,
        requested_strategy: Optional[str],
        query: str,
        wrapped_chunks: List[Any],
    ) -> str:
        """
        Explicit strategies are honoured. 'auto' stuffs the selected context into one prompt and only
        falls back to map-reduce when the context is larger than twice the configured budget.
        """
        if requested_strategy in ("map_reduce", "refine", "map_rerank", "stuff"):
            return requested_strategy
        if len(wrapped_chunks) < 2:
            return "stuff"
        total_chars = sum(len(getattr(c, "text", "") or "") for c in wrapped_chunks)
        return "map_reduce" if total_chars > 2 * rag_settings.context_char_budget else "stuff"

    def _stuff_messages(self, plan: "_TurnPlan") -> List[Dict[str, str]]:
        return [
            {"role": "system", "content": plan.system_prompt},
            *plan.generation_history,
            {"role": "user", "content": plan.user_content},
        ]

    async def _map_phase(self, plan: "_TurnPlan", request: RagChatRequestDTO, authorization: Optional[str]) -> List[str]:
        async def _map_chunk(chunk_obj: Any, idx: int) -> Tuple[int, str]:
            map_msgs = prompt_builder.build_map_prompt(chunk_obj, plan.standalone_query, chunk_index=idx)
            try:
                summary, _, _ = await self.llm_service.generate(
                    messages=map_msgs, model=request.model, temperature=0.1, max_tokens=384, authorization=authorization
                )
                return idx, summary.strip()
            except Exception as e:  # noqa: BLE001
                logger.warning("Map phase error on chunk %s: %s", idx, e)
                return idx, ""

        results = await asyncio.gather(*[_map_chunk(c, i) for i, c in enumerate(plan.wrapped, start=1)])
        return [
            f"[{idx}] {s}" for idx, s in results
            if s and "KHÔNG_CÓ_THÔNG_TIN_LIÊN_QUAN" not in s and "NO_RELEVANT_INFO" not in s
        ]

    async def _refine_until_last(
        self, plan: "_TurnPlan", request: RagChatRequestDTO, authorization: Optional[str], include_last: bool
    ) -> Tuple[str, int, int]:
        init_msgs = prompt_builder.build_refine_initial_prompt(
            chunk=plan.wrapped[0], query=plan.standalone_query, chunk_index=1, history=plan.generation_history
        )
        current, p_tok, c_tok = await self.llm_service.generate(
            messages=init_msgs, model=request.model, temperature=request.temperature,
            max_tokens=request.max_tokens, authorization=authorization,
        )
        last = len(plan.wrapped) if include_last else len(plan.wrapped) - 1
        for idx in range(1, last):
            step_msgs = prompt_builder.build_refine_step_prompt(
                existing_answer=current, next_chunk=plan.wrapped[idx], query=plan.standalone_query, chunk_index=idx + 1
            )
            refined, p, c = await self.llm_service.generate(
                messages=step_msgs, model=request.model, temperature=request.temperature,
                max_tokens=request.max_tokens, authorization=authorization,
            )
            if refined.strip() and "KHÔNG_CÓ_THÔNG_TIN_LIÊN_QUAN" not in refined:
                current = refined.strip()
                p_tok += p
                c_tok += c
        return current, p_tok, c_tok

    async def _map_rerank_answer(
        self, plan: "_TurnPlan", request: RagChatRequestDTO, authorization: Optional[str]
    ) -> Tuple[Optional[str], int, int]:
        async def _eval_chunk(chunk_obj: Any, idx: int) -> Tuple[int, int, str, int, int]:
            eval_msgs = prompt_builder.build_map_rerank_prompt(chunk_obj, plan.standalone_query, chunk_index=idx)
            try:
                raw_eval, p_tok, c_tok = await self.llm_service.generate(
                    messages=eval_msgs, model=request.model, temperature=0.1, max_tokens=384, authorization=authorization
                )
                score, ans = self._parse_map_rerank_response(raw_eval, idx)
                return idx, score, ans, p_tok, c_tok
            except Exception as e:  # noqa: BLE001
                logger.warning("Map-rerank error on chunk %s: %s", idx, e)
                return idx, 0, "", 0, 0

        results = await asyncio.gather(*[_eval_chunk(c, i) for i, c in enumerate(plan.wrapped, start=1)])
        p_total = sum(r[3] for r in results)
        c_total = sum(r[4] for r in results)
        valid = sorted([(r[0], r[1], r[2]) for r in results if r[1] > 0 and r[2]], key=lambda x: x[1], reverse=True)
        if not valid:
            return None, p_total, c_total
        winner_idx, _, winner_ans = valid[0]
        plan.raw_citations = [c for c in plan.raw_citations if c.get("index") == winner_idx] + [
            c for c in plan.raw_citations if c.get("index") != winner_idx
        ]
        return winner_ans, p_total, c_total

    async def _generate_full(
        self, plan: "_TurnPlan", request: RagChatRequestDTO, authorization: Optional[str]
    ) -> Tuple[str, int, int]:
        strategy = plan.strategy
        if strategy == "map_reduce" and len(plan.wrapped) >= 2:
            summaries = await self._map_phase(plan, request, authorization)
            if summaries:
                msgs = prompt_builder.build_reduce_prompt(
                    query=plan.standalone_query, map_summaries=summaries, history=plan.generation_history
                )
                return await self.llm_service.generate(
                    messages=msgs, model=request.model, temperature=request.temperature,
                    max_tokens=request.max_tokens, authorization=authorization,
                )
            plan.strategy = "stuff"
        elif strategy == "refine" and len(plan.wrapped) >= 2:
            return await self._refine_until_last(plan, request, authorization, include_last=True)
        elif strategy == "map_rerank" and plan.wrapped:
            answer, p_tok, c_tok = await self._map_rerank_answer(plan, request, authorization)
            if answer is not None:
                return answer, p_tok, c_tok
        else:
            plan.strategy = "stuff"
        return await self.llm_service.generate(
            messages=self._stuff_messages(plan), model=request.model, temperature=request.temperature,
            max_tokens=request.max_tokens, authorization=authorization,
        )

    async def _generate_stream(
        self, plan: "_TurnPlan", request: RagChatRequestDTO, authorization: Optional[str]
    ) -> AsyncGenerator[str, None]:
        strategy = plan.strategy
        messages: Optional[List[Dict[str, str]]] = None
        if strategy == "map_reduce" and len(plan.wrapped) >= 2:
            summaries = await self._map_phase(plan, request, authorization)
            if summaries:
                messages = prompt_builder.build_reduce_prompt(
                    query=plan.standalone_query, map_summaries=summaries, history=plan.generation_history
                )
            else:
                plan.strategy = "stuff"
        elif strategy == "refine" and len(plan.wrapped) >= 2:
            current, _, _ = await self._refine_until_last(plan, request, authorization, include_last=False)
            messages = prompt_builder.build_refine_step_prompt(
                existing_answer=current, next_chunk=plan.wrapped[-1], query=plan.standalone_query,
                chunk_index=len(plan.wrapped),
            )
        elif strategy == "map_rerank" and plan.wrapped:
            answer, _, _ = await self._map_rerank_answer(plan, request, authorization)
            if answer is not None:
                words = answer.split(" ")
                for i, w in enumerate(words):
                    yield w + (" " if i < len(words) - 1 else "")
                return
        else:
            plan.strategy = "stuff"
        if messages is None:
            messages = self._stuff_messages(plan)
        async for token in self.llm_service.stream_generate(
            messages=messages, model=request.model, temperature=request.temperature,
            max_tokens=request.max_tokens, authorization=authorization,
        ):
            yield token

    async def _finalize_answer(
        self,
        plan: "_TurnPlan",
        request: RagChatRequestDTO,
        clean_text: str,
        marker_map: Dict[int, int],
        refused: bool,
        tenant_id: str,
        user_id: str,
        session_id: str,
    ) -> Tuple[str, List[Dict[str, Any]], str]:
        """Returns (tail to append, cited sources, intent). A model refusal becomes an escalation reply."""
        if refused or not clean_text.strip():
            await self._make_refusal_plan(plan, request, tenant_id, user_id, session_id)
            return plan.answer, [], "REFUSAL"
        if plan.strategy in SYNTHESIS_STRATEGIES:
            # Multi-pass synthesis keeps the original markers; every passage it read is a source.
            cited = _deduplicate_citations(plan.raw_citations)
        elif marker_map:
            cited = remap_citations(plan.raw_citations, marker_map)
        else:
            cited = _filter_attributed_citations(_deduplicate_citations(plan.raw_citations), clean_text, strategy=plan.strategy)
        tail = build_sources_footer(cited)
        if rag_settings.suggestions_enabled and not plan.analysis.wants_brief:
            tail += build_suggestions(clean_text, plan.suggestion_pool)
        return tail, cited, f"QA_{plan.strategy.upper()}"

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

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

        history = await self._resolve_history(session_id, user_id, tenant_id, request.history)
        if not history:
            cached_res = await self._cache_lookup(request, request.query, tenant_id, user_role, session_id, start_t)
            if cached_res:
                return cached_res

        if request.adhoc_context and request.adhoc_context.strip():
            return await self._execute_adhoc(request, history, session_id, tenant_id, user_id, authorization, start_t)

        plan = await self._plan_turn(request, history, tenant_id, user_id, user_role, session_id, authorization)
        rewrite_decision = plan.rewrite
        if history and plan.kind == "generate":
            cached_res = await self._cache_lookup(request, plan.standalone_query, tenant_id, user_role, session_id, start_t)
            if cached_res:
                return cached_res

        if plan.kind == "multihop":
            return await self._execute_multi_hop(
                request=request, standalone_query=plan.standalone_query, decomp=plan.decomp,
                history=plan.generation_history, session_id=session_id, tenant_id=tenant_id, user_id=user_id,
                user_role=user_role, authorization=authorization, start_t=start_t, rewrite_decision=rewrite_decision,
            )

        if plan.kind == "clarification":
            plan.kind, plan.intent, plan.status = "direct", "AMBIGUOUS_SYMPTOM", "clarification_needed"
            plan.answer = AMBIGUOUS_CLARIFICATION_TEXT

        if plan.kind == "direct":
            latency_ms = (time.time() - start_t) * 1000
            await self._save_session_turn(
                session_id=session_id, user_id=user_id, tenant_id=tenant_id, query=request.query,
                answer=plan.answer, citations=[], model=request.model, intent=plan.intent, latency_ms=latency_ms,
                standalone_query=plan.standalone_query,
            )
            return RagChatResponseDTO(
                answer=plan.answer,
                model=request.model,
                citations=[],
                latency_ms=round(latency_ms, 2),
                intent=plan.intent,
                session_id=session_id,
                status=plan.status,
                escalation=plan.escalation,
                clarification=ClarificationDTO(**AMBIGUOUS_CLARIFICATION) if plan.intent == "AMBIGUOUS_SYMPTOM" else None,
                is_refusal=plan.is_refusal,
                circuit_breaker_triggered=plan.is_refusal,
                telemetry=self._telemetry(plan, latency_ms),
                pre_retrieval_tier=rewrite_decision.tier,
                pre_retrieval_latency_ms=round(plan.analysis.latency_ms, 2),
                hyde_active=plan.hyde.is_active if plan.hyde else False,
            )

        plan.strategy = self._resolve_combine_strategy(getattr(request, "combine_strategy", None), plan.standalone_query, plan.wrapped)
        plan.sanitize_ctx.renumber = plan.strategy not in SYNTHESIS_STRATEGIES
        t_gen_0 = time.perf_counter()
        raw_answer, prompt_tokens, completion_tokens = await self._generate_full(plan, request, authorization)
        self.obs.record_stage_latency("llm_generate", time.perf_counter() - t_gen_0, tenant_id=tenant_id)
        self.obs.record_tokens(request.model, "prompt", prompt_tokens, tenant_id=tenant_id)
        self.obs.record_tokens(request.model, "completion", completion_tokens, tenant_id=tenant_id)

        clean_text, marker_map, refused = sanitize_answer(raw_answer, plan.sanitize_ctx)
        tail, cited, intent = await self._finalize_answer(
            plan, request, clean_text, marker_map, refused, tenant_id, user_id, session_id
        )
        answer = plan.answer if intent == "REFUSAL" else clean_text + tail
        citation_dtos = [_build_citation_dto(c) for c in cited]
        if citation_dtos and plan.context_chunks:
            self.obs.record_groundedness(min(1.0, len(citation_dtos) / len(plan.context_chunks)), tenant_id=tenant_id)

        latency_ms = (time.time() - start_t) * 1000
        await self._save_session_turn(
            session_id=session_id, user_id=user_id, tenant_id=tenant_id, query=request.query, answer=answer,
            citations=cited, model=request.model, intent=intent, prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens, latency_ms=latency_ms, standalone_query=plan.standalone_query,
        )
        resp_dto = RagChatResponseDTO(
            answer=answer,
            model=request.model,
            citations=citation_dtos,
            latency_ms=round(latency_ms, 2),
            intent=intent,
            combine_strategy=plan.strategy,
            session_id=session_id,
            status=plan.status if intent == "REFUSAL" else "success",
            escalation=plan.escalation if intent == "REFUSAL" else None,
            is_refusal=intent == "REFUSAL",
            circuit_breaker_triggered=False,
            telemetry=self._telemetry(plan, latency_ms),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            pre_retrieval_tier=rewrite_decision.tier,
            pre_retrieval_latency_ms=round(plan.analysis.latency_ms, 2),
            hyde_active=plan.hyde.is_active if plan.hyde else False,
            hypothetical_doc=plan.hyde.hypothetical_document if plan.hyde and plan.hyde.is_active else None,
            hyde_latency_ms=round(plan.hyde.latency_ms, 2) if plan.hyde else 0.0,
        )
        if intent != "REFUSAL" and self._is_cacheable(request):
            cache_query = plan.standalone_query if history else request.query
            try:
                await self.cache_service.set(response=resp_dto, **self._cache_key_args(request, cache_query, tenant_id, user_role))
            except Exception as cache_exc:  # noqa: BLE001
                logger.warning("Failed to write response cache: %s", cache_exc)
        return resp_dto

    @staticmethod
    def _telemetry(plan: "_TurnPlan", latency_ms: float) -> Dict[str, Any]:
        return {
            "trace_id": f"tr_rag_{uuid.uuid4().hex[:8]}",
            "latency_ms": round(latency_ms, 2),
            "gate_latency_ms": round(plan.gate_latency_ms, 2),
            "rerank_top1_score": round(plan.top_score, 4),
            "query_analysis": plan.analysis.source,
            "query_intent": plan.analysis.intent.value,
            "standalone_query": plan.standalone_query,
            "context_chunks": len(plan.context_chunks),
        }

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

    @staticmethod
    def _sse_token(token: str, session_id: str) -> str:
        return f"data: {json.dumps({'token': token, 'session_id': session_id}, ensure_ascii=False)}\n\n"

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
        session_id = request.conversation_id or f"sess_{uuid.uuid4().hex[:12]}"
        self._truncate_query(request)

        history = await self._resolve_history(session_id, user_id, tenant_id, request.history)

        if request.adhoc_context and request.adhoc_context.strip():
            async for event in self._stream_adhoc(request, history, session_id, tenant_id, user_id, authorization, start_t):
                yield event
            return

        plan = await self._plan_turn(request, history, tenant_id, user_id, user_role, session_id, authorization)
        rewrite_decision = plan.rewrite

        if plan.kind == "multihop":
            async for event in self._stream_execute_multi_hop(
                request=request, standalone_query=plan.standalone_query, decomp=plan.decomp,
                history=plan.generation_history, session_id=session_id, tenant_id=tenant_id, user_id=user_id,
                user_role=user_role, authorization=authorization, start_t=start_t, rewrite_decision=rewrite_decision,
            ):
                yield event
            return

        if plan.kind == "clarification":
            clarification_payload = dict(AMBIGUOUS_CLARIFICATION)
            yield f"event: clarification\ndata: {json.dumps(clarification_payload, ensure_ascii=False)}\n\n"
            yield self._sse_token(AMBIGUOUS_CLARIFICATION_TEXT, session_id)
            latency_ms = (time.time() - start_t) * 1000
            await self._save_session_turn(
                session_id=session_id, user_id=user_id, tenant_id=tenant_id, query=request.query,
                answer=AMBIGUOUS_CLARIFICATION_TEXT, citations=[], model=request.model, intent="AMBIGUOUS_SYMPTOM",
                latency_ms=latency_ms, standalone_query=plan.standalone_query,
            )
            yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'status': 'clarification_needed', 'clarification': clarification_payload, 'citations': [], 'total_latency_ms': round(latency_ms, 2)})}\n\n"
            return

        if plan.kind == "direct":
            latency_ms = (time.time() - start_t) * 1000
            yield self._sse_token(plan.answer, session_id)
            await self._save_session_turn(
                session_id=session_id, user_id=user_id, tenant_id=tenant_id, query=request.query,
                answer=plan.answer, citations=[], model=request.model, intent=plan.intent, latency_ms=latency_ms,
                standalone_query=plan.standalone_query,
            )
            done = {
                "done": True, "session_id": session_id, "status": plan.status, "intent": plan.intent,
                "escalation": plan.escalation, "citations": [], "circuit_breaker_triggered": plan.is_refusal,
                "is_refusal": plan.is_refusal, "pre_retrieval_tier": rewrite_decision.tier,
                "ttft_ms": round(latency_ms, 2), "total_latency_ms": round(latency_ms, 2),
                "trace_id": f"tr_rag_{uuid.uuid4().hex[:8]}",
                "hyde_active": plan.hyde.is_active if plan.hyde else False,
                "rerank_top1_score": round(plan.top_score, 4),
                "standalone_query": plan.standalone_query,
            }
            yield f"data: {json.dumps(done, ensure_ascii=False)}\n\n"
            return

        plan.strategy = self._resolve_combine_strategy(getattr(request, "combine_strategy", None), plan.standalone_query, plan.wrapped)
        plan.sanitize_ctx.renumber = plan.strategy not in SYNTHESIS_STRATEGIES
        stream_filter = AnswerStreamFilter(plan.sanitize_ctx)
        first_token_time: Optional[float] = None
        token_stream = self._generate_stream(plan, request, authorization)
        try:
            async for token in token_stream:
                for piece in stream_filter.feed(token):
                    if first_token_time is None:
                        first_token_time = time.time()
                    yield self._sse_token(piece, session_id)
                if stream_filter.refused:
                    break  # the model declined: stop generating and escalate instead
        finally:
            await token_stream.aclose()
        for piece in stream_filter.finish():
            if first_token_time is None:
                first_token_time = time.time()
            yield self._sse_token(piece, session_id)

        tail, cited, intent = await self._finalize_answer(
            plan, request, stream_filter.text, dict(stream_filter.marker_map), stream_filter.refused,
            tenant_id, user_id, session_id,
        )
        if tail:
            if first_token_time is None:
                first_token_time = time.time()
            yield self._sse_token(tail, session_id)
        answer = plan.answer if intent == "REFUSAL" else stream_filter.text + tail
        latency_ms = (time.time() - start_t) * 1000
        await self._save_session_turn(
            session_id=session_id, user_id=user_id, tenant_id=tenant_id, query=request.query, answer=answer,
            citations=cited, model=request.model, intent=intent, latency_ms=latency_ms,
            standalone_query=plan.standalone_query,
        )
        ttft_ms = round((first_token_time - start_t) * 1000, 2) if first_token_time else None
        done = {
            "done": True,
            "session_id": session_id,
            "status": plan.status if intent == "REFUSAL" else "success",
            "intent": intent,
            "escalation": plan.escalation if intent == "REFUSAL" else None,
            "citations": [_build_citation_dto(c).model_dump() for c in cited],
            "combine_strategy": plan.strategy,
            "is_refusal": intent == "REFUSAL",
            "circuit_breaker_triggered": False,
            "pre_retrieval_tier": rewrite_decision.tier,
            "pre_retrieval_latency_ms": round(plan.analysis.latency_ms, 2),
            "ttft_ms": ttft_ms,
            "total_latency_ms": round(latency_ms, 2),
            "trace_id": f"tr_rag_{uuid.uuid4().hex[:8]}",
            "hyde_active": plan.hyde.is_active if plan.hyde else False,
            "hypothetical_doc": plan.hyde.hypothetical_document if plan.hyde and plan.hyde.is_active else None,
            "rerank_top1_score": round(plan.top_score, 4),
            "standalone_query": plan.standalone_query,
        }
        yield f"data: {json.dumps(done, ensure_ascii=False)}\n\n"

    # ------------------------------------------------------------------
    # Ad-hoc attachment QA (the attached text is the only context)
    # ------------------------------------------------------------------

    @staticmethod
    def _adhoc_messages(request: RagChatRequestDTO, history: List[Dict[str, str]]) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
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
        citations = [{
            "index": 1, "doc_id": "adhoc_attachment", "title": adhoc_title,
            "page_number": 1, "score": 1.0, "excerpt": adhoc_excerpt,
        }]
        messages = [
            {"role": "system", "content": system_prompt},
            *RagChatUseCase._llm_history(history),
            {"role": "user", "content": request.query},
        ]
        return messages, citations

    async def _execute_adhoc(
        self, request: RagChatRequestDTO, history: List[Dict[str, str]], session_id: str, tenant_id: str,
        user_id: str, authorization: Optional[str], start_t: float,
    ) -> RagChatResponseDTO:
        messages, adhoc_citations = self._adhoc_messages(request, history)
        answer, prompt_tokens, completion_tokens = await self.llm_service.generate(
            messages=messages, model=request.model, temperature=request.temperature,
            max_tokens=request.max_tokens, authorization=authorization,
        )
        latency_ms = (time.time() - start_t) * 1000
        await self._save_session_turn(
            session_id=session_id, user_id=user_id, tenant_id=tenant_id, query=request.query, answer=answer,
            citations=adhoc_citations, model=request.model, intent="ADHOC_QA", prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens, latency_ms=latency_ms,
        )
        return RagChatResponseDTO(
            answer=answer, model=request.model, citations=[_build_citation_dto(c) for c in adhoc_citations],
            latency_ms=round(latency_ms, 2), intent="ADHOC_QA", session_id=session_id,
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
        )

    async def _stream_adhoc(
        self, request: RagChatRequestDTO, history: List[Dict[str, str]], session_id: str, tenant_id: str,
        user_id: str, authorization: Optional[str], start_t: float,
    ) -> AsyncGenerator[str, None]:
        messages, adhoc_citations = self._adhoc_messages(request, history)
        accumulated: List[str] = []
        first_token_time: Optional[float] = None
        async for token in self.llm_service.stream_generate(
            messages=messages, model=request.model, temperature=request.temperature,
            max_tokens=request.max_tokens, authorization=authorization,
        ):
            if first_token_time is None:
                first_token_time = time.time()
            accumulated.append(token)
            yield self._sse_token(token, session_id)
        latency_ms = (time.time() - start_t) * 1000
        await self._save_session_turn(
            session_id=session_id, user_id=user_id, tenant_id=tenant_id, query=request.query,
            answer="".join(accumulated), citations=adhoc_citations, model=request.model, intent="ADHOC_QA",
            latency_ms=latency_ms,
        )
        ttft_ms = round((first_token_time - start_t) * 1000, 2) if first_token_time else None
        yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'citations': adhoc_citations, 'ttft_ms': ttft_ms})}\n\n"

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
        standalone_query: Optional[str] = None,
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
            if standalone_query and standalone_query.strip() != (query or "").strip():
                user_msg["standalone"] = standalone_query
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
