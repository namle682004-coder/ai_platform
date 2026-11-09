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
from contextlib import asynccontextmanager
import hashlib
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, AsyncIterator, Dict, List, Optional, Sequence, Set, Tuple

from ...domain.exceptions import (
    EmbeddingError,
    LLMGenerationError,
    LLMStreamInterruptedError,
    RerankerError,
    ServiceOverloadedError,
    VectorStoreError,
)
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
    NullTableStore,
    NullTraceStore,
    ObservabilityPort,
    TableStorePort,
    RerankerPort,
    SessionRepositoryPort,
    TraceStorePort,
    VectorStorePort,
)
from ..components import media_assets
from ..components.session_ids import new_session_id
from ..components.answer_postprocessor import (
    AnswerStreamFilter,
    SanitizeContext,
    build_sources_footer,
    build_suggestions,
    collect_image_urls,
    has_substantive_content,
    remap_citations,
    sanitize_answer,
)
from ..components.answer_verifier import (
    build_grounding,
    extractive_answer,
    focus_locations,
    focus_present,
    format_missing,
    is_english_text,
    missing_items,
    specific_focus_terms,
)
from ..components.context_selector import (
    build_document_card,
    candidate_key,
    chunk_order_key,
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
    absent_numeric_details,
    candidate_heading,
    candidate_text,
    strip_diacritics,
    extract_identifiers,
    mostly_unaccented,
    nearest_existing_codes,
    normalize_for_match,
    restore_diacritics_from_corpus,
    score_evidence,
    unique_in_order,
)
from ..components.prompt_builder import (
    REFUSAL_MESSAGE,
    instruction_text,
    prompt_builder,
    strip_breadcrumb,
)
from ..components.query_analyzer import ANALYZER_MARKER, Intent, QueryAnalysis, QueryAnalyzer
from ..components.query_decomposer import DecomposedQuery, query_decomposer
from ..components.query_rewriter import RewrittenQuery, query_rewriter
from ..components.reranker import cross_encoder_reranker
from ..components.run_trace import (
    TurnTrace,
    begin_turn,
    chunk_refs,
    current_trace_id,
    dropped_sentences,
    end_turn,
    trace_stage,
)
from ..components.reference_ambiguity import ambiguous_reference
from ..components.reference_ambiguity import clarification_text as reference_clarification_text
from ..components.table_query import parse_plan as parse_table_plan
from ..components.table_query import planner_messages as table_planner_messages
from ..components.table_query import render_result as render_table_result
from ..components.table_query import run_query as run_table_query
from ..components.table_store import TableRecord
from ..components.numeric_tables import (
    compute_answer as compute_numeric_answer,
)
from ..components.numeric_tables import (
    column_named,
    expand_to_families,
    label_named,
    parse_numeric_tables,
)
from ..components.numeric_tables import (
    parse_plan as parse_numeric_plan,
)
from ..components.numeric_tables import (
    planner_messages as numeric_planner_messages,
)
from ..components.table_rows import (
    build_schema,
    TablePlan,
    counts_column,
    listing_summary,
    names_value,
    parse_plan,
    parse_table_rows,
    planner_messages,
    question_filters,
    reconcile_plan,
    refine_plan,
    render_items,
    row_items,
)
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
        images=[str(u) for u in (c.get("images") or [])],
        file_type=str(c.get("file_type") or "") or None,
    )


def media_secret() -> str:
    """HMAC key of document image URLs (configured, or derived from the deployment's storage secret)."""
    if rag_settings.media_signing_secret:
        return rag_settings.media_signing_secret
    material = f"aip-media:{rag_settings.minio_root_password}:{rag_settings.mongo_uri}"
    return hashlib.sha256(material.encode()).hexdigest()


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
    # Generated answer with the document's images placed under their steps (None: no image placed in it).
    inline_body: Optional[str] = None
    section_pool: List[Dict[str, Any]] = field(default_factory=list)  # passages of the answered documents (images by section)
    speculative: Optional[Any] = None  # asyncio.Task: retrieval + rerank of a first message, run during analysis
    speculative_query: str = ""
    wrapped: List[Any] = field(default_factory=list)
    raw_citations: List[Dict[str, Any]] = field(default_factory=list)
    system_prompt: str = ""
    user_content: str = ""
    max_tokens: Optional[int] = None  # completion budget left by the prompt in the model window
    unverified_feedback: bool = False  # labelled feedback on a session's first turn; retrieval decides
    direct_citations: List[Dict[str, Any]] = field(default_factory=list)  # sources of a direct (structured) answer
    answer_replaced: bool = False  # the generated answer was replaced (refusal, out-of-scope, feedback)
    policy_category: str = ""  # labelled out-of-scope by the analyzer; answered only on strong evidence
    strategy: str = "stuff"
    support: Optional[Any] = None
    sanitize_ctx: Optional[SanitizeContext] = None


INFRASTRUCTURE_ERRORS = (EmbeddingError, RerankerError, VectorStoreError, LLMGenerationError, ServiceOverloadedError)
BUSY_MESSAGE = "Hệ thống đang bận do nhiều người dùng cùng lúc, vui lòng thử lại sau ít phút."
OUTAGE_MESSAGE = "Dịch vụ tạm thời gián đoạn, vui lòng thử lại sau."


def overload_retry_after(exc: BaseException) -> Optional[int]:
    """Retry-After of an overload anywhere in the exception chain (None when it is another failure)."""
    seen = set()
    cur: Optional[BaseException] = exc
    while cur is not None and id(cur) not in seen:
        if isinstance(cur, ServiceOverloadedError):
            return cur.retry_after
        seen.add(id(cur))
        cur = cur.__cause__ or cur.__context__
    return None


def unavailable_reply(exc: BaseException) -> Tuple[str, int, bool]:
    """(message, Retry-After seconds, busy) for a turn that could not be served."""
    retry_after = overload_retry_after(exc)
    return (BUSY_MESSAGE, retry_after, True) if retry_after is not None else (OUTAGE_MESSAGE, 5, False)


class ChatAdmission:
    """
    Turns in progress in this process. Each turn makes several model calls, so a turn admitted beyond
    what the runtimes can serve only waits, holds memory and delays everyone: it is refused at once.
    """

    def __init__(self, limit: Optional[int] = None) -> None:
        self._limit = limit
        self.in_flight = 0
        self.rejected = 0

    @property
    def limit(self) -> int:
        return max(1, self._limit or rag_settings.chat_max_inflight)

    @asynccontextmanager
    async def turn(self) -> AsyncIterator[None]:
        if self.in_flight >= self.limit:
            self.rejected += 1
            raise ServiceOverloadedError(f"{self.in_flight} chat turns in progress (limit {self.limit})",
                                         retry_after=int(rag_settings.runtime_queue_timeout_seconds))
        self.in_flight += 1
        try:
            yield
        finally:
            self.in_flight -= 1
# Combine strategies whose final answer is synthesised over several passes and cites by original index.
SYNTHESIS_STRATEGIES = ("map_reduce", "refine")
# A document is "related" to the question when its best passage scores at least this share of the best one.
RELATED_DOCUMENT_RATIO = 0.5
# Candidates kept after merging the question, focus and paraphrase retrievals (all are reranked).
MERGED_CANDIDATE_LIMIT = 48
# Fewer parsed table items than this: the document is not tabular enough for the structured path.
STRUCTURED_MIN_ITEMS = 3
# An automatically triggered (not explicitly requested) structured answer must list at least this many items.
STRUCTURED_AUTO_MIN_SELECTED = 3
# Rows of a computed figures table: a ranking shows the top ones, a "list them all" question all of them.
PROMPT_TEMPLATE_TOKENS = 8  # per chat message, for the template's role markers
FAQ_CANDIDATES = 3  # a Q&A pair among the best few passages is checked question-to-question
# Word overlap (Jaccard) from which the analyzer's rewrite of a first message is that message.
SPECULATIVE_MIN_OVERLAP = 0.75
STREAM_RESTARTS = 2  # answers regenerated after the runtime cut them off before any text was shown
CITATION_MAX_IMAGES = 8  # images listed on one cited passage (its own and its section's)
NUMERIC_SORT_MAX_ROWS = 15
NUMERIC_LIST_MAX_ROWS = 60
# Weak reranking: documents whose share of the hybrid search results is below this fraction of the
# leading document's are not what the question is about (rank smoothing constant of that share).
DOCUMENT_FOCUS_MIN_SHARE = 0.5
DOCUMENT_SHARE_RANK_OFFSET = 10


def leading_documents(candidates: Sequence[Dict[str, Any]]) -> Set[str]:
    """
    Documents the hybrid search (dense + BM25 over the whole question) points to, by reciprocal-rank share
    of its results. Empty when the results come from a single document.
    """
    share: Dict[str, float] = {}
    for i, c in enumerate(candidates):
        doc_id = str(payload_of(c).get("doc_id") or "")
        if doc_id:
            share[doc_id] = share.get(doc_id, 0.0) + 1.0 / (DOCUMENT_SHARE_RANK_OFFSET + i)
    if len(share) < 2:
        return set()
    top = max(share.values())
    return {d for d, s in share.items() if s >= DOCUMENT_FOCUS_MIN_SHARE * top}


# Per-turn conversation memory stored with session messages and shown to the query analyzer.
MEMORY_KEYS = ("focus", "scope", "identifiers", "asked_contact")
# Support replies that end by inviting the user to leave a phone number.
CONTACT_INVITING_INTENTS = ("REFUSAL", "ESCALATION")


def _turn_memory_user(plan: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if plan.analysis.focus_terms:
        out["focus"] = list(plan.analysis.focus_terms)
    if plan.analysis.scope_terms:
        out["scope"] = list(plan.analysis.scope_terms)
    return out


def _turn_memory_assistant(answer: str, intent: Optional[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    ids = extract_identifiers((answer or "").split("**Nguồn:**")[0])
    if ids:
        out["identifiers"] = ids[:12]
    if (intent or "").upper() in CONTACT_INVITING_INTENTS:
        out["asked_contact"] = True
    return out


def _enrich_history(history: List[Dict[str, Any]], stored: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Copies stored per-turn metadata onto a client-sent transcript (matched by role and content)."""
    index = {
        (m.get("role"), (m.get("content") or "").strip()): m
        for m in stored or []
        if m.get("content")
    }
    for item in history:
        meta = index.get((item.get("role"), (item.get("content") or "").strip()))
        if not meta:
            continue
        for key in ("standalone", "intent", *MEMORY_KEYS):
            if meta.get(key) and not item.get(key):
                item[key] = meta[key]
    return history


def unique_in_order_objects(items: Any) -> List[Any]:
    seen, out = set(), []
    for it in items:
        if id(it) not in seen:
            seen.add(id(it))
            out.append(it)
    return out


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
        trace_store: Optional[TraceStorePort] = None,
        table_store: Optional[TableStorePort] = None,
        support_repo: Optional[Any] = None,
    ) -> None:
        self.table_store = table_store or NullTableStore()
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        self.llm_service = llm_service
        self.session_repo = session_repo
        self.cache_service = cache_service or NullCacheAdapter()
        self.reranker_service = reranker_service or cross_encoder_reranker
        self.obs = observability_service or NullObservabilityAdapter()
        self.trace_store = trace_store or NullTraceStore()
        self.admission = ChatAdmission()
        self._trace_tasks: set = set()
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
        self.support_repo = support_repo

    async def _support_for_tenant(self, tenant_id: str) -> SupportResponder:
        if self.support_repo is not None:
            try:
                cfg = await self.support_repo.get_support_config(tenant_id)
                if cfg and (cfg.get("hotline") or cfg.get("support_method")):
                    return SupportResponder(
                        hotline=cfg.get("hotline") or "",
                        support_method=cfg.get("support_method") or "",
                        instructions=cfg.get("instructions") or "",
                    )
            except Exception as exc:
                logger.debug("Support config lookup for tenant=%s failed: %s", tenant_id, exc)
        return self.support

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

        responder = await self._support_for_tenant(tenant_id)
        return {
            "status": "escalation_required",
            "reason": reason,
            "message": REFUSAL_MESSAGE,
            "escalation_data": {
                "hotline": responder.hotline,
                "support_method": responder.support_method,
                "instructions": responder.instructions,
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
            temperature=self._answer_temperature(request),
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
            temperature=self._answer_temperature(request),
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
                "file_type": c.get("file_type") or None,
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
            history = [dict(m) for m in list(explicit_history)[-window:]]
            try:
                record = await self.session_repo.get_session(session_id, user_id, tenant_id)
            except Exception as exc:  # noqa: BLE001 - enrichment only
                logger.debug("Session lookup for history enrichment failed: %s", exc)
                record = None
            return _enrich_history(history, (record or {}).get("messages", []))

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
            if msg.get("author") == "agent":
                continue  # written by customer service, not an answer of the bot from the documents
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role and content:
                item = {"role": role, "content": content}
                if msg.get("standalone"):
                    item["standalone"] = msg["standalone"]
                if msg.get("intent"):
                    item["intent"] = msg["intent"]
                for key in MEMORY_KEYS:
                    if msg.get(key):
                        item[key] = msg[key]
                formatted.append(item)
        return formatted[-window:]

    def _generation_history(self, history: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """
        History shown to the answer model. In "questions" mode (default) earlier answers are replaced by
        what they were about: a follow-up is resolved by the analyzer into a standalone question, and the
        figures of a previous answer must not leak into the new one (a model asked "and the lowest?"
        rewrites the previous numbers instead of reading the documents).
        """
        if rag_settings.generation_history_mode == "full":
            return self._llm_history(history)
        out: List[Dict[str, str]] = []
        for m in history[-6:]:
            if m.get("role") == "user":
                out.append({"role": "user", "content": (m.get("standalone") or m.get("content") or "")[:400]})
            else:
                about = ", ".join(m.get("identifiers") or [])
                out.append({"role": "assistant", "content": "(Đã trả lời từ tài liệu" + (f"; các mã đã nêu: {about}" if about else "") + ".)"})
        return out

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
        allow_hyde: bool = True,
    ) -> Tuple[List[Dict[str, Any]], HyDEResult]:
        """Hybrid dense + BM25 retrieval (optionally HyDE-fused) of a wide candidate pool for reranking."""
        enable_hyde = getattr(request, "enable_hyde", None) if allow_hyde else False
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
        trace_stage(
            "retrieval", ms=(time.perf_counter() - t0) * 1000, query=query_text, sparse_query=sparse_query,
            hyde=bool(hyde_res.is_active), fetch_k=fetch_k, candidates=chunk_refs(candidates, limit=fetch_k),
        )
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
        raw_query = await self._reaccented_query(request, tenant_id, user_role)
        # A first message needs no conversational rewriting, so the search for it does not have to wait
        # for the analyzer: retrieval + rerank of the message run during the analysis LLM call and are
        # reused when the analyzer's question is (nearly) the message itself.
        spec_task: Optional[asyncio.Task] = None
        spec_query = ""
        if rag_settings.speculative_retrieval_enabled and not history:
            spec_rewrite = await query_rewriter.rewrite_advanced(raw_query, None, llm_port=None)
            spec_query = spec_rewrite.text or raw_query
            spec_task = asyncio.ensure_future(self._speculative_retrieval(
                request, spec_query, spec_rewrite.sparse_query or spec_query, tenant_id, user_role))
        try:
            analyzer_model = getattr(request, "analyzer_model", None) or rag_settings.query_analysis_model or request.model
            analysis = await self.query_analyzer.analyze(
                raw_query, history, self.llm_service, analyzer_model, authorization=authorization,
            )
        except BaseException:
            if spec_task is not None:
                spec_task.cancel()
            raise
        self.obs.record_stage_latency("query_analysis", time.perf_counter() - t0, tenant_id=tenant_id)
        if analysis.source == "fallback" and history and analysis.is_document_question:
            analysis = await self._check_fallback_carryover(analysis, raw_query or request.query, request, tenant_id, user_role)
        # Without a rewrite from the analyzer, the re-accented message (not the raw one) is the question.
        standalone = analysis.standalone_query or raw_query or request.query
        rewrite: RewrittenQuery = await query_rewriter.rewrite_advanced(standalone, None, llm_port=None)
        plan = _TurnPlan(analysis=analysis, rewrite=rewrite, standalone_query=rewrite.text or standalone)
        plan.support = await self._support_for_tenant(tenant_id)
        plan.speculative, plan.speculative_query = spec_task, spec_query
        plan.generation_history = [] if (analysis.new_topic or not history) else self._generation_history(history)
        trace_stage(
            "query_analysis", ms=(time.perf_counter() - t0) * 1000, source=analysis.source,
            intent=analysis.intent.value, message_kind=analysis.message_kind, standalone_query=plan.standalone_query,
            sparse_query=rewrite.sparse_query, focus=list(analysis.focus_terms), scope=list(analysis.scope_terms),
            flags={k: getattr(analysis, k) for k in (
                "new_topic", "challenge", "about_document", "wants_list", "wants_brief", "wants_location",
                "compare", "answer_format", "aggregate", "count_unit",
            )},
            history_messages=len(history), generation_history_messages=len(plan.generation_history),
        )

        # 2. Non-document turns get deterministic support replies. "unclear" is a weak judgement of a
        # small model ("RAG học ở lớp mấy?" can look vague without the corpus), so it is verified
        # against retrieval: the evidence gate answers it when the documents support it and asks
        # the user to rephrase otherwise.
        if analysis.intent == Intent.FEEDBACK and not any(m.get("role") == "assistant" for m in history):
            # Nothing answered in this session yet: a document question is often mislabelled as feedback.
            # Retrieval decides; without evidence the message is still recorded as feedback.
            analysis.intent, plan.unverified_feedback = Intent.UNCLEAR, True
        if analysis.intent == Intent.CONTACT_INFO and not analysis.phone:
            analysis.intent = Intent.UNCLEAR  # asking FOR contact details is not giving one's own
        if analysis.intent == Intent.OUT_OF_SCOPE and rag_settings.out_of_scope_verify_with_retrieval:
            # The policy label comes from the question alone; a question the tenant's own documents
            # clearly answer ("rights of data subjects" in a curriculum) is not a request for private data.
            # Retrieval decides: strong evidence answers it, otherwise the policy reply is given.
            plan.policy_category = analysis.out_of_scope_category or "ngoài phạm vi"
            analysis.intent = Intent.DOCUMENT_QUESTION
        if not analysis.is_document_question and analysis.intent != Intent.UNCLEAR:
            self._drop_speculative(plan)
            await self._plan_support_turn(plan, request, history, tenant_id, user_id, user_role, session_id)
            trace_stage("route", route="support", intent=plan.intent)
            return plan

        if intent_classifier.is_ambiguous_symptom(plan.standalone_query):
            self._drop_speculative(plan)
            plan.kind = "clarification"
            trace_stage("route", route="clarification", intent="AMBIGUOUS_SYMPTOM")
            return plan

        multi_hop_flag = getattr(request, "multi_hop", None)
        if multi_hop_flag is True or (multi_hop_flag is None and query_decomposer.should_decompose(plan.standalone_query)):
            decomp = await query_decomposer.decompose(
                plan.standalone_query, llm_port=self.llm_service, model=analyzer_model, timeout=0.8
            )
            if decomp.is_multi_hop and len(decomp.sub_queries) >= 2:
                self._drop_speculative(plan)
                plan.kind = "multihop"
                plan.decomp = decomp
                trace_stage("route", route="multihop", sub_queries=list(decomp.sub_queries))
                return plan

        try:
            await self._plan_document_turn(plan, request, tenant_id, user_id, user_role, session_id, authorization)
        finally:
            self._drop_speculative(plan)
        return plan

    async def _check_fallback_carryover(
        self, analysis: QueryAnalysis, message: str, request: RagChatRequestDTO, tenant_id: str, user_role: str
    ) -> QueryAnalysis:
        """
        Without the analyzer (timeout, runtime down), a short message is joined to the previous question as a
        follow-up. A message none of whose words the documents contain ("hi", a complaint about the answer)
        is not a follow-up: carrying the previous question over would answer it again. It is treated as
        unclear instead, so the user is asked what to look up.
        """
        message = (message or "").strip()
        if not message or analysis.standalone_query.strip() == message:
            return analysis
        try:
            candidates, _ = await self._search_candidates(request, message, message, tenant_id, user_role, allow_hyde=False)
        except Exception as exc:  # noqa: BLE001 - keep the follow-up reading
            logger.debug("Fallback carry-over check failed: %s", exc)
            return analysis
        if score_evidence(message, candidates).best_coverage < rag_settings.gate_min_lexical_coverage:
            analysis.intent, analysis.standalone_query = Intent.UNCLEAR, message
            trace_stage("fallback_carryover", carried=False, message=message)
        return analysis

    @staticmethod
    def _drop_speculative(plan: "_TurnPlan") -> None:
        """A speculative search nobody will use (support turn, rewritten question) stops loading the runtimes."""
        task, plan.speculative = plan.speculative, None
        if task is not None and not task.done():
            task.cancel()

    async def _speculative_retrieval(
        self, request: RagChatRequestDTO, query: str, sparse_query: str, tenant_id: str, user_role: str
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
        """(candidates, rerank scores) of the user's message, computed while the analyzer runs."""
        candidates, _ = await self._search_candidates(request, query, sparse_query, tenant_id, user_role, allow_hyde=False)
        if not candidates:
            return [], {}
        ranked = await self.reranker_service.arerank(
            query=query, candidates=candidates, top_n=max(1, len(candidates)), min_threshold=0.0
        )
        return candidates, {candidate_key(c): float(c.get("score", 0.0) or 0.0) for c in ranked}

    @staticmethod
    def _same_question(a: str, b: str) -> bool:
        """The analyzer's rewrite of a first message is the message (accents or a typo fixed at most)."""
        ta, tb = set(normalize_for_match(a).split()), set(normalize_for_match(b).split())
        if not ta or not tb:
            return False
        return len(ta & tb) / len(ta | tb) >= SPECULATIVE_MIN_OVERLAP

    async def _reaccented_query(self, request: RagChatRequestDTO, tenant_id: str, user_role: str) -> str:
        """
        A message typed without diacritics, re-accented from the vocabulary of the passages it retrieves,
        before the analyzer reads it: a small model rewrites "mang no ron nhan tao hoc lop may" into an
        unrelated question, while the documents know the words are "mạng nơ-ron nhân tạo học lớp mấy".
        """
        query = request.query
        if not (rag_settings.reaccent_before_analysis and mostly_unaccented(query)):
            return query
        try:
            candidates, _ = await self._search_candidates(request, query, query, tenant_id, user_role, allow_hyde=False)
        except Exception as exc:  # noqa: BLE001 - best effort: the analyzer still gets the raw message
            logger.debug("Re-accenting search failed: %s", exc)
            return query
        restored = restore_diacritics_from_corpus(query, (candidate_text(c) for c in candidates))
        if restored != query:
            trace_stage("reaccent", query=query, restored=restored)
        return restored

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
        support = plan.support or await self._support_for_tenant(tenant_id)
        analysis = plan.analysis
        plan.kind = "direct"
        if analysis.intent == Intent.GREETING:
            plan.intent, plan.answer = "CHITCHAT", support.greeting()
        elif analysis.intent == Intent.OUT_OF_SCOPE:
            plan.intent, plan.answer = "OUT_OF_SCOPE", support.out_of_scope(analysis.out_of_scope_category)
        elif analysis.intent == Intent.SUPPORT_REQUEST:
            ticket_id, escalation = await self._record_ticket(
                session_id, tenant_id, user_id, request.query, reason="handoff_request"
            )
            plan.intent, plan.status, plan.escalation = "ESCALATION", "escalation_required", escalation
            plan.answer = support.handoff(ticket_id)
        elif analysis.intent == Intent.CONTACT_INFO:
            question = last_unanswered_question(history)
            ticket_id, escalation = await self._record_ticket(
                session_id, tenant_id, user_id, question or request.query, reason="callback_request",
                extra={"contact_phone": analysis.phone, "related_ticket": last_ticket_in_history(history)},
            )
            plan.intent, plan.status, plan.escalation = "CONTACT_CAPTURED", "escalation_required", escalation
            plan.answer = support.contact_saved(analysis.phone or request.query, ticket_id, question)
        elif analysis.intent == Intent.DECLINE_CONTACT:
            plan.intent, plan.answer = "SUPPORT_INFO", support.contact_declined()
        elif analysis.intent == Intent.TICKET_STATUS:
            plan.intent = "TICKET_STATUS"
            plan.answer = support.ticket_status(last_ticket_in_history(history), last_unanswered_question(history))
        else:
            # FEEDBACK / UNCLEAR: show what the documents contain so the user can rephrase.
            titles, outline = await self._documents_overview(request, history, tenant_id, user_role)
            if analysis.intent == Intent.FEEDBACK:
                ticket_id, escalation = await self._record_ticket(
                    session_id, tenant_id, user_id, request.query, reason="user_feedback",
                    extra={"previous_question": last_unanswered_question(history) or self._last_user_question(history)},
                )
                plan.intent, plan.escalation = "FEEDBACK", escalation
                plan.answer = support.feedback(ticket_id, titles, outline)
            else:
                plan.intent, plan.answer = "CLARIFICATION", support.clarify(titles, outline)
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

    async def _rerank_pool(
        self, rerank_query: str, candidates: List[Dict[str, Any]], tenant_id: str, user_role: str,
        known_scores: Optional[Dict[str, float]] = None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, float], Dict[str, List[Dict[str, Any]]]]:
        """
        (reranked, pool incl. expanded documents, rerank scores, expanded chunks by document).
        `known_scores`: cross-encoder scores already computed for this same query; only the others are scored.
        """
        t_rerank = time.perf_counter()
        known = known_scores or {}
        fresh = [c for c in candidates if candidate_key(c) not in known]
        scored = await self.reranker_service.arerank(
            query=rerank_query, candidates=fresh, top_n=max(1, len(fresh)), min_threshold=0.0
        ) if fresh else []
        reused = [dict(c, score=known[candidate_key(c)]) for c in candidates if candidate_key(c) in known]
        reranked = sorted([*scored, *reused], key=lambda c: float(c.get("score", 0.0) or 0.0), reverse=True)
        self.obs.record_stage_latency("rerank", time.perf_counter() - t_rerank, tenant_id=tenant_id)
        rerank_scores = {candidate_key(c): float(c.get("score", 0.0) or 0.0) for c in reranked}

        # Whole-document expansion for the best documents (sections, headers, every table row).
        pool: List[Dict[str, Any]] = list(reranked)
        prelim = score_evidence(rerank_query, pool) if pool else None
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
        trace_stage(
            "rerank", ms=(time.perf_counter() - t_rerank) * 1000, query=rerank_query,
            ranked=chunk_refs(reranked, rerank_scores, text_chars=rag_settings.trace_pool_text_chars,
                              limit=MERGED_CANDIDATE_LIMIT),
            expanded_docs={d: len(chunks) for d, chunks in expanded.items()},
        )
        return reranked, pool, rerank_scores, expanded

    def _llm_wait_allowance(self) -> float:
        """Seconds to add to a model call's own timeout while every runtime slot is taken (queue wait)."""
        allowance = getattr(self.llm_service, "queue_allowance", None)
        try:
            return float(allowance()) if callable(allowance) else 0.0
        except Exception:  # noqa: BLE001
            return 0.0

    async def _paraphrases(self, query: str, request: RagChatRequestDTO, authorization: Optional[str]) -> List[str]:
        """LLM rewrites of the question in formal / domain terms (multi-query retrieval)."""
        n = max(1, rag_settings.multi_query_count)
        messages = [
            {"role": "system", "content": (
                f"{ANALYZER_MARKER} Viết lại câu hỏi tra cứu thành {n} câu khác nhau, dùng thuật ngữ chính thức/chuyên môn "
                "tương đương (giải nghĩa từ viết tắt, đổi cách nói đời thường sang thuật ngữ), cùng ngôn ngữ, không trả lời. "
                'Trả về DUY NHẤT JSON {"queries": ["..."]}.'
            )},
            {"role": "user", "content": f"CÂU HỎI: {query}\n\nJSON:"},
        ]
        try:
            raw, _, _ = await asyncio.wait_for(
                self.llm_service.generate(messages=messages, model=request.model, temperature=0.0, max_tokens=200,
                                          authorization=authorization),
                timeout=rag_settings.query_analysis_timeout + self._llm_wait_allowance(),
            )
        except Exception as exc:  # noqa: BLE001 - recall booster only
            logger.debug("Paraphrase generation failed: %s", exc)
            return []
        s = raw or ""
        start, end = s.find("{"), s.rfind("}")
        try:
            data = json.loads(s[start:end + 1]) if start != -1 and end > start else {}
        except ValueError:
            data = {}
        queries = data.get("queries") if isinstance(data, dict) else None
        if not isinstance(queries, list):
            return []
        return [str(q).strip() for q in queries if str(q).strip() and str(q).strip() != query][:n]

    @staticmethod
    def _merge_candidates(*lists: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        """Round-robin union of candidate lists (each list keeps its own ranking)."""
        merged, seen = [], set()
        for rank in range(max((len(x) for x in lists), default=0)):
            for lst in lists:
                if rank < len(lst):
                    key = candidate_key(lst[rank])
                    if key not in seen:
                        seen.add(key)
                        merged.append(lst[rank])
        return merged[:limit]

    async def _plan_document_turn(
        self,
        plan: "_TurnPlan",
        request: RagChatRequestDTO,
        tenant_id: str,
        user_id: str,
        user_role: str,
        session_id: str,
        authorization: Optional[str] = None,
    ) -> None:
        analysis = plan.analysis
        query = plan.standalone_query
        focus_terms = [t for t in analysis.focus_terms if normalize_for_match(t)]
        focus_query = " ".join(focus_terms)

        # 1. Retrieval: the full question and, in parallel, the asked-about terms alone, so that scope
        #    words of the question cannot hide the passages where the subject actually is.
        use_focus = bool(
            rag_settings.focus_retrieval_enabled and focus_query
            and normalize_for_match(focus_query) != normalize_for_match(query)
        )
        # The search already made for the first message during analysis is this search when the analyzer
        # kept the question (accents or a typo fixed at most): its candidates and scores are reused.
        spec_task, plan.speculative = plan.speculative, None
        reuse = spec_task is not None and self._same_question(plan.speculative_query, query)
        if spec_task is not None and not reuse:
            spec_task.cancel()
        searches = [] if reuse else [
            self._search_candidates(request, query, plan.rewrite.sparse_query or query, tenant_id, user_role)]
        if use_focus:
            searches.append(self._search_candidates(request, focus_query, focus_query, tenant_id, user_role, allow_hyde=False))
        known_scores: Optional[Dict[str, float]] = None
        if reuse:
            try:
                spec_candidates, known_scores = await spec_task
            except Exception as exc:  # noqa: BLE001 - fall back to the regular search
                logger.debug("Speculative retrieval failed: %s", exc)
                reuse, known_scores = False, None
                searches.insert(0, self._search_candidates(
                    request, query, plan.rewrite.sparse_query or query, tenant_id, user_role))
        results = await asyncio.gather(*searches) if searches else []
        if reuse:
            candidates = spec_candidates
            plan.hyde = HyDEResult(hypothetical_document="", original_query=query, is_active=False,
                                   trigger_reason="speculative_reuse", latency_ms=0.0)
            if use_focus:
                candidates = self._merge_candidates(candidates, results[0][0], limit=MERGED_CANDIDATE_LIMIT)
            trace_stage("speculative_retrieval", reused=True, query=plan.speculative_query)
        else:
            candidates, plan.hyde = results[0]
            if use_focus:
                candidates = self._merge_candidates(candidates, results[1][0], limit=MERGED_CANDIDATE_LIMIT)

        # Unaccented queries are re-accented from the vocabulary of the retrieved passages.
        rerank_query = plan.speculative_query if reuse else query
        if candidates and mostly_unaccented(rerank_query):
            rerank_query = restore_diacritics_from_corpus(rerank_query, (candidate_text(c) for c in candidates))
        reranked, pool, rerank_scores, expanded = await self._rerank_pool(
            rerank_query, candidates, tenant_id, user_role,
            known_scores=known_scores if reuse and rerank_query == plan.speculative_query else None,
        )
        lexical_query = " ".join([rerank_query, *focus_terms]) if focus_terms else rerank_query
        evidence = score_evidence(lexical_query, pool) if pool else None

        # 2. Weak evidence: retrieve again with paraphrases in domain terms (synonyms, abbreviations).
        threshold = self._effective_threshold(request)
        weak = (
            not pool
            or (max(rerank_scores.values(), default=0.0) < min(threshold or 1.0, rag_settings.gate_min_rerank_score)
                and (evidence.best_coverage if evidence else 0.0) < rag_settings.gate_min_lexical_coverage)
        )
        if weak and rag_settings.multi_query_on_weak_evidence:
            paraphrases = await self._paraphrases(query, request, authorization)
            trace_stage("multi_query", reason="weak_evidence", paraphrases=paraphrases)
            if paraphrases:
                extra = await asyncio.gather(*[
                    self._search_candidates(request, p, p, tenant_id, user_role, allow_hyde=False) for p in paraphrases
                ])
                candidates = self._merge_candidates(candidates, *[e[0] for e in extra], limit=MERGED_CANDIDATE_LIMIT)
                # The cross-encoder scores against the question plus its first domain-term rewrite.
                reranked, pool, rerank_scores, expanded = await self._rerank_pool(
                    f"{rerank_query} ({paraphrases[0]})", candidates, tenant_id, user_role
                )
                lexical_query = " ".join([lexical_query, *paraphrases])
                evidence = score_evidence(lexical_query, pool) if pool else None
        plan.top_score = max(rerank_scores.values(), default=0.0)

        # 2b. An administrator's Q&A pair that clearly matches the question answers it as approved:
        # rewording it through the model could only drift from what the admin wrote (and is slower).
        if await self._plan_faq_answer(plan, reranked, rerank_scores):
            return

        # 2c. No passage is a clear match for the reranker: the lexical score then decides, and it rewards
        # any document sharing common words of the question ("tài liệu", "văn bản"), which with several
        # documents in the project fills the context with the wrong one. The hybrid search over the whole
        # question still points to the right document: keep only the documents it leads to. Q&A pairs are
        # one passage each, never "leading" by count: they always stay in competition.
        if pool and plan.top_score < rag_settings.gate_min_rerank_score:
            leading = leading_documents(candidates)

            def keep(c: Dict[str, Any]) -> bool:
                p = payload_of(c)
                return str(p.get("doc_id")) in leading or str(p.get("file_type") or "") == "faq"

            kept = [c for c in pool if keep(c)] if leading else []
            if kept and len(kept) < len(pool):
                dropped_docs = unique_in_order(
                    str(payload_of(c).get("title") or "") for c in pool if c not in kept
                )
                pool = kept
                reranked = [c for c in reranked if keep(c)]
                expanded = {d: v for d, v in expanded.items() if d in leading}
                evidence = score_evidence(lexical_query, pool)
                # Not "dropped": that key holds verification's (problem, sentence) records in every trace.
                trace_stage("document_focus", leading=sorted(leading), excluded_documents=dropped_docs[:8])

        t_gate = time.perf_counter()
        blended: Dict[str, float] = {}
        for i, c in enumerate(pool):
            r = rerank_scores.get(candidate_key(c), 0.0)
            lex = evidence.coverage_of(i) if evidence else 0.0
            blended[candidate_key(c)] = max(r, lex) + 0.25 * min(r, lex)
        best_lexical = evidence.best_coverage if evidence else 0.0
        texts = [candidate_text(c) for c in pool]
        # Documents named to the user (refusal / clarification) must be the ones that matched, not every
        # document of the shared knowledge base that happened to be retrieved.
        ranked = sorted(pool, key=lambda c: blended.get(candidate_key(c), 0.0), reverse=True)
        best_blended = blended.get(candidate_key(ranked[0]), 0.0) if ranked else 0.0
        related = [c for c in ranked if blended.get(candidate_key(c), 0.0) >= RELATED_DOCUMENT_RATIO * best_blended]
        plan.titles = unique_in_order(str(payload_of(c).get("title") or "") for c in related[:6])[:2]
        titled_docs = [d for d in unique_in_order(str(payload_of(c).get("doc_id")) for c in related)
                       if any(str(payload_of(c).get("title") or "") in plan.titles for c in related
                              if str(payload_of(c).get("doc_id")) == d)]
        plan.outline = outline_from_candidates([
            c for c in pool
            if str(payload_of(c).get("doc_id")) in titled_docs
            and (str(payload_of(c).get("doc_id")) in set(expanded) or c in reranked[:16])
        ])
        document_chunks = [c for d in titled_docs for c in expanded.get(d, [])]
        plan.section_pool = document_chunks or list(pool)

        gate_trace = {
            "top_rerank": round(plan.top_score, 4), "best_lexical": round(best_lexical, 4), "threshold": threshold,
            "min_rerank": rag_settings.gate_min_rerank_score, "min_lexical": rag_settings.gate_min_lexical_coverage,
            "query_identifiers": list(evidence.query_identifiers) if evidence else [],
            "missing_identifiers": list(evidence.missing_identifiers) if evidence else [],
            "pool": len(pool), "titles": plan.titles,
        }

        # 3. Evidence gate. Identifiers the documents do not contain are answered deterministically.
        if evidence and evidence.query_identifiers and len(evidence.missing_identifiers) == len(evidence.query_identifiers):
            code = evidence.missing_identifiers[0]
            scope, codes = nearest_existing_codes(code, texts)
            plan.kind, plan.intent = "direct", "IDENTIFIER_NOT_FOUND"
            plan.answer = (plan.support or self.support).identifier_not_found(code, scope, codes)
            plan.gate_latency_ms = (time.perf_counter() - t_gate) * 1000
            trace_stage("gate", decision="identifier_not_found", nearest_codes=codes[:10], **gate_trace)
            trace_stage("route", route="identifier_not_found", intent=plan.intent)
            return

        # A question naming an identifier the documents contain is about that item, not about the document.
        about_document = analysis.about_document and not (evidence and evidence.query_identifiers)
        no_evidence = (
            not pool
            or (
                threshold > 0.0
                and plan.top_score < min(threshold, rag_settings.gate_min_rerank_score)
                and best_lexical < rag_settings.gate_min_lexical_coverage
                and not about_document
            )
        )
        if no_evidence and pool and rag_settings.numeric_tables_enabled:
            # A question naming a figure column of the document's tables ("lượt xem/like") is about those
            # figures, even when no single row scores well against it (rankings span many small tables).
            question = f"{request.query} {query}"
            named = [t.columns[i] for t in parse_numeric_tables(document_chunks or pool) for i in t.numeric_columns
                     if column_named(t.columns[i], question)]
            if named:
                no_evidence = False
                gate_trace["named_columns"] = unique_in_order(named)[:5]
        plan.gate_latency_ms = (time.perf_counter() - t_gate) * 1000
        self.obs.record_stage_latency("gatekeeper", plan.gate_latency_ms / 1000, tenant_id=tenant_id)
        if (plan.policy_category and plan.top_score < rag_settings.gate_min_rerank_score
                and best_lexical < rag_settings.out_of_scope_override_min_lexical):
            plan.kind, plan.intent = "direct", "OUT_OF_SCOPE"
            plan.answer = (plan.support or self.support).out_of_scope(plan.policy_category)
            trace_stage("gate", ms=plan.gate_latency_ms, decision="out_of_scope", policy=plan.policy_category,
                        **gate_trace)
            trace_stage("route", route="support", intent=plan.intent)
            return
        trace_stage("gate", ms=plan.gate_latency_ms, decision="no_evidence" if no_evidence else "pass",
                    about_document=about_document, policy=plan.policy_category, **gate_trace)
        if no_evidence:
            logger.info(
                "Evidence gate: no support (rerank %.3f, lexical %.3f); refusing without generation.",
                plan.top_score, best_lexical,
            )
            if analysis.intent == Intent.UNCLEAR and not plan.unverified_feedback:
                plan.kind, plan.intent = "direct", "CLARIFICATION"
                plan.answer = (plan.support or self.support).clarify(plan.titles, plan.outline)
                trace_stage("route", route="gate_clarification", intent=plan.intent)
                return
            await self._make_refusal_plan(plan, request, tenant_id, user_id, session_id, authorization)
            trace_stage("route", route="gate_refusal", intent=plan.intent)
            return

        # 3b. A numbered part ("Điều 7") named by the question that exists in several sub-documents: ask which.
        if rag_settings.reference_clarification_enabled:
            options = ambiguous_reference(plan.standalone_query or request.query, reranked[:20] or pool)
            if options:
                plan.kind, plan.intent = "direct", "CLARIFICATION"
                plan.answer = reference_clarification_text(options)
                trace_stage("route", route="reference_clarification", options=[o.path for o in options])
                return

        # 4. Filtering / counting / listing / summing rows of whole tables: computed in code over the stored
        #    tables of every retrieved document and of the same table in other documents.
        if await self._plan_table_query(plan, request, pool, tenant_id, user_role, authorization):
            trace_stage("route", route="table_query", intent=plan.intent,
                        context=chunk_refs(plan.context_chunks, text_chars=rag_settings.trace_context_text_chars))
            return

        # 4b. Figures over tables (highest, lowest, difference, total…) are computed in code, not estimated.
        if await self._plan_numeric_query(plan, request, document_chunks or pool, authorization):
            trace_stage("route", route="numeric", intent=plan.intent,
                        context=chunk_refs(plan.context_chunks, text_chars=rag_settings.trace_context_text_chars))
            return

        # 5. Listing / comparison over tabular documents: parsed rows + LLM filter + deterministic rendering.
        top_passage = reranked[0] if reranked and plan.top_score >= rag_settings.gate_min_rerank_score else None
        if await self._plan_structured_listing(plan, request, document_chunks, authorization, top_passage):
            trace_stage("route", route="structured", intent=plan.intent,
                        context=chunk_refs(plan.context_chunks, text_chars=rag_settings.trace_context_text_chars))
            return

        # 5. Adaptive context: every passage close to the best one, in document order.
        list_like = analysis.wants_list or analysis.compare
        selection = select_adaptive_context(
            pool,
            blended,
            relative_cutoff=(
                rag_settings.context_list_relative_cutoff if list_like else rag_settings.context_relative_cutoff
            ),
            char_budget=rag_settings.context_char_budget if list_like else rag_settings.context_char_budget_point,
            min_k=max(1, request.top_k or 4),
            max_k=rag_settings.context_max_chunks,
        )
        chosen = list(selection.chunks)
        # The passages where the asked-about subject actually appears are always part of the context.
        focus_hits = [c for c in ranked if focus_terms and focus_present(focus_terms, [c])]
        for c in focus_hits[: max(0, rag_settings.focus_min_passages)]:
            if c not in chosen:
                chosen.append(c)
        if list_like and expanded:
            matched_sections = {candidate_heading(c).strip() for c in chosen if candidate_heading(c)}
            chosen_keys = {candidate_key(c) for c in chosen}
            for doc_chunks in expanded.values():
                for c in doc_chunks:
                    k = candidate_key(c)
                    if k not in chosen_keys:
                        h = (candidate_heading(c) or "").strip()
                        if h and any(m and (m in h or h in m) for m in matched_sections):
                            chosen.append(c)
                            chosen_keys.add(k)
            # Document order inside each document; documents keep the (lost-in-the-middle) order of the selection.
            doc_rank: Dict[str, int] = {}
            for c in chosen:
                doc_rank.setdefault(str(payload_of(c).get("doc_id")), len(doc_rank))
            chosen = sorted(chosen, key=lambda c: (doc_rank[str(payload_of(c).get("doc_id"))], chunk_order_key(c)[1]))
        if about_document or rag_settings.document_card_always:
            card_docs = [d for d in titled_docs if d in {str(payload_of(c).get("doc_id")) for c in chosen}] or titled_docs[:1]
            chosen_keys = {candidate_key(c) for c in chosen}
            for doc_id in card_docs[:2]:
                doc_chunks = expanded.get(doc_id) or [c for c in pool if str(payload_of(c).get("doc_id")) == doc_id]
                opening = min(doc_chunks, key=chunk_order_key) if doc_chunks else None
                if not about_document and (opening is None or candidate_key(opening) in chosen_keys):
                    continue  # the document's opening passage is already in the context
                card = build_document_card(doc_chunks)
                if card:
                    cand = document_card_candidate(card)
                    if not about_document:
                        payload_of(cand)["text"] = payload_of(cand)["text"][: rag_settings.document_card_max_chars]
                    chosen.insert(0, cand)

        plan.kind = "generate"
        plan.context_chunks = chosen
        plan.suggestion_pool = chosen + [
            c for c in sorted(pool, key=lambda c: blended.get(candidate_key(c), 0.0), reverse=True)[:12]
            if c not in chosen
        ]
        user_content = f"Câu hỏi của người dùng: {request.query}"
        if query.strip() != request.query.strip():
            user_content += f"\n(Câu hỏi đầy đủ theo ngữ cảnh hội thoại: {query})"
        if analysis.challenge:
            user_content += (
                "\n(Người dùng đang phản bác hoặc chỉ ra thiếu sót của câu trả lời trước: đối chiếu lại tài liệu. "
                "Chỉ đổi câu trả lời khi tài liệu ủng hộ người dùng; nếu không, giữ nguyên và nêu lại căn cứ.)"
            )
            # The rewritten question drops the user's counter-claim, so state where the documents put
            # the subject: the model then checks the claim against a fact instead of the user's word.
            sections, _ = focus_locations(focus_terms, (), focus_hits[:6]) if focus_hits else ([], False)
            if sections:
                user_content += (
                    f"\n(Sự thật trong tài liệu: «{', '.join(focus_terms)}» được đề cập ở mục "
                    + ", ".join(f"«{s}»" for s in sections[:3])
                    + ". Mục nào không có trong danh sách này thì tài liệu không nói «"
                    + ", ".join(focus_terms) + "» ở đó.)"
                )
        if focus_hits and analysis.scope_terms:
            sections, in_scope = focus_locations(focus_terms, analysis.scope_terms, focus_hits[:6])
            if sections and not in_scope:
                user_content += (
                    f"\n(Kiểm tra tiền đề: «{', '.join(focus_terms)}» được tài liệu đề cập ở mục "
                    + ", ".join(f"«{s}»" for s in sections[:3])
                    + f", không thấy ở «{', '.join(analysis.scope_terms)}». Nói rõ điều đó và nêu nơi tài liệu thực sự đề cập kèm mã/mục.)"
                )
        absent = absent_numeric_details(request.query, pool)
        if absent:
            user_content += (
                "\n(Kiểm tra tiền đề: các chi tiết sau trong câu hỏi KHÔNG xuất hiện trong tài liệu: "
                + "; ".join(f"«{d}»" for d in absent)
                + ". Câu đầu tiên phải nói rõ tài liệu không có/ghi khác chi tiết đó, rồi mới nêu thông tin tài liệu có.)"
            )
        plan.user_content = user_content + "\n(Trả lời bằng tiếng Việt.)"
        await self._build_prompt_within_window(plan, request, query, chosen, blended)
        trace_stage(
            "context", selected=len(chosen), kept=len(plan.context_chunks), list_like=list_like,
            focus_passages=len(focus_hits),
            chunks=chunk_refs(plan.context_chunks, blended, text_chars=rag_settings.trace_context_text_chars),
            system_prompt_chars=len(plan.system_prompt), user_content=plan.user_content,
            max_tokens=plan.max_tokens,
        )
        trace_stage("route", route="generate", intent="QA")
        grounding = None
        if rag_settings.identifier_grounding_enabled or rag_settings.language_guard_enabled:
            grounding = build_grounding(
                plan.context_chunks, document_chunks or plan.context_chunks,
                allow_examples=analysis.about_document,
                language_guard=rag_settings.language_guard_enabled and not is_english_text(request.query),
                question=f"{request.query} {query}",
                check_units=rag_settings.unit_grounding_enabled,
            )
            if not rag_settings.identifier_grounding_enabled:
                grounding.identifiers, grounding.example_identifiers = set(), set()
                grounding.check_numbers = False
        plan.sanitize_ctx = SanitizeContext(
            titles=unique_in_order(str(c.get("title") or "") for c in plan.raw_citations),
            allowed_image_urls=collect_image_urls(c.get("text", "") for c in plan.raw_citations),
            prompt_text=instruction_text(),
            valid_indices={int(c.get("index", 0)) for c in plan.raw_citations},
            grounding=grounding,
            evidence_text="\n".join(candidate_text(c) for c in plan.context_chunks),
            image_url_mapper=self._media_mapper(plan.context_chunks, tenant_id),
        )

    async def _faq_question_score(self, query: str, phrasings: List[str]) -> float:
        """
        How well the question matches one of the ways the pair is asked (question vs question). Scoring the
        whole pair mixes in its answer, which for "it is not in the documents" style answers reads as a
        mismatch even when the user asked exactly the stored question.
        """
        if not phrasings:
            return 0.0
        cands = [{"id": f"faq_q{i}", "score": 0.0, "payload": {"text": p, "doc_id": f"faq_q{i}", "chunk_index": i}}
                 for i, p in enumerate(phrasings)]
        try:
            ranked = await self.reranker_service.arerank(query=query, candidates=cands, top_n=len(cands), min_threshold=0.0)
        except Exception as exc:  # noqa: BLE001 - the pair can still answer through the documents path
            logger.debug("FAQ question rerank failed: %s", exc)
            return 0.0
        return max((float(c.get("score", 0.0) or 0.0) for c in ranked), default=0.0)

    async def _plan_faq_answer(
        self, plan: "_TurnPlan", reranked: List[Dict[str, Any]], rerank_scores: Dict[str, float]
    ) -> bool:
        """The approved answer of the best-ranked Q&A pair, when the cross-encoder is confident it is the question."""
        if not (rag_settings.faq_direct_answer_enabled and reranked) or plan.analysis.challenge:
            return False
        top = next((c for c in reranked[:FAQ_CANDIDATES]
                    if str(payload_of(c).get("file_type") or "") == "faq" and payload_of(c).get("approved_answer")), None)
        if top is None:
            return False
        payload = payload_of(top)
        answer = str(payload.get("approved_answer") or "").strip()
        question = str(payload.get("question") or "").strip()
        variations = [str(v) for v in (payload.get("question_variations") or []) if str(v).strip()]
        phrasings = list(dict.fromkeys(p for p in [question, *variations, *(strip_diacritics(x) for x in [question, *variations])] if p))
        pair_score = float(rerank_scores.get(candidate_key(top), 0.0))
        question_score = await self._faq_question_score(plan.standalone_query, phrasings)
        score = max(pair_score, question_score)
        trace_stage("faq_match", qa_id=payload.get("qa_id") or payload.get("doc_id"), pair_score=round(pair_score, 4),
                    question_score=round(question_score, 4), used=score >= rag_settings.faq_direct_min_score)
        if score < rag_settings.faq_direct_min_score:
            return False
        plan.kind, plan.intent = "direct", "QA_FAQ"
        # The answer is the administrator's own: there is no document to cite, so no source is shown
        # (the trace keeps which pair answered, for review).
        plan.answer = answer
        plan.direct_citations = []
        plan.context_chunks = [top]
        trace_stage("route", route="faq", intent=plan.intent, qa_id=payload.get("qa_id") or payload.get("doc_id"),
                    score=round(score, 4))
        return True

    async def _load_tables(self, pool: List[Dict[str, Any]], tenant_id: str, user_role: str) -> List[TableRecord]:
        """Stored tables of the retrieved documents, then every table of the same kinds in the tenant."""
        doc_ids = unique_in_order(str(payload_of(c).get("doc_id") or "") for c in pool)
        doc_ids = [d for d in doc_ids if d][: rag_settings.table_query_max_docs]
        if not doc_ids:
            return []
        own = [TableRecord.from_dict(d) for d in await self.table_store.list_tables(tenant_id, user_role, doc_ids=doc_ids)]
        if not own:
            return []
        rank = {d: i for i, d in enumerate(doc_ids)}
        own.sort(key=lambda t: (rank.get(t.doc_id, len(rank)), t.index))
        signatures = list(dict.fromkeys(t.signature for t in own))
        family = await self.table_store.list_tables(
            tenant_id, user_role, signatures=signatures, limit=rag_settings.table_query_max_tables
        )
        seen = {(t.doc_id, t.index) for t in own}
        return own + [TableRecord.from_dict(d) for d in family if (d.get("doc_id"), d.get("index")) not in seen]

    async def _plan_table_query(
        self,
        plan: "_TurnPlan",
        request: RagChatRequestDTO,
        pool: List[Dict[str, Any]],
        tenant_id: str,
        user_role: str,
        authorization: Optional[str],
    ) -> bool:
        """
        Questions that filter, count, list or sum table rows, answered from whole stored tables (not from the
        passages retrieval happened to return). The LLM only maps the question to a plan over the table
        schema; rows and figures come from code. False when not applicable (the other routes then answer).
        """
        analysis = plan.analysis
        asks_rows = (analysis.wants_list or analysis.compare or bool(analysis.aggregate) or bool(analysis.count_unit)
                     or analysis.answer_format == "table")
        if not (rag_settings.table_query_enabled and asks_rows and pool):
            return False
        tables = await self._load_tables(pool, tenant_id, user_role)
        if not tables:
            return False
        question = plan.standalone_query or request.query
        raw = ""
        try:
            raw, _, _ = await asyncio.wait_for(
                self.llm_service.generate(
                    messages=table_planner_messages(question, tables),
                    model=request.model, temperature=0.0, max_tokens=300, authorization=authorization,
                ),
                timeout=rag_settings.query_analysis_timeout + 4 + self._llm_wait_allowance(),
            )
        except Exception as exc:  # noqa: BLE001 - the passage routes answer instead
            logger.info("Table planner failed (%s)", exc)
        query = parse_table_plan(raw) if raw else None
        result = run_table_query(tables, query) if query else None
        trace_stage("table_query", tables=len(tables), planner=(raw or "")[:500],
                    applied=bool(result and result.matches), rows=len(result.matches) if result else 0)
        if not result or not result.matches:
            # No plan, or a plan selecting nothing: not taken as "nothing exists" (the planner may have
            # misread a column); the passage routes answer instead.
            return False
        body = render_table_result(result)
        sources = []
        for t in unique_in_order_objects(m.table for m in result.matches)[:10]:
            rows = [m.row for m in result.matches if m.table is t]
            text = "\n".join(["| " + " | ".join(t.columns) + " |", "| " + " | ".join("---" for _ in t.columns) + " |",
                              *("| " + " | ".join(r) + " |" for r in rows)])
            sources.append({"score": 1.0, "payload": {
                "doc_id": t.doc_id, "title": t.title, "page_number": t.page, "chunk_index": t.index,
                "heading": t.caption or t.section, "heading_path": t.section, "text": text,
            }})
        raw_citations, _ = prompt_builder.build_context_and_citations(
            [CandidateWrapper(c) for c in sources], query=question
        )
        cited = _deduplicate_citations(raw_citations)
        plan.kind, plan.intent = "direct", "QA_TABLE"
        plan.answer = body + build_sources_footer(cited)
        plan.direct_citations = cited
        plan.context_chunks = sources
        logger.info("Table query: %s over %d table(s), %d row(s)", result.operation, len(result.tables), len(result.matches))
        return True

    async def _plan_numeric_query(
        self,
        plan: "_TurnPlan",
        request: RagChatRequestDTO,
        chunks: List[Dict[str, Any]],
        authorization: Optional[str],
    ) -> bool:
        """Answers extremum / difference / total questions from parsed numeric tables; False when not applicable."""
        analysis = plan.analysis
        flagged = bool(analysis.aggregate and analysis.aggregate != "count")
        question = f"{request.query} {plan.standalone_query}"
        # The analyzer's aggregate flag is a small model's guess and is often missing ("nhiều bình luận
        # nhất"). Over a document with figure tables, a question naming one of their numeric columns or
        # asking for a list is planned too; the plan is then accepted only on those grounds (below).
        if not (rag_settings.numeric_tables_enabled and chunks) or analysis.aggregate == "count":
            return False
        if not flagged and (extract_identifiers(request.query) or analysis.about_document):
            return False
        tables = parse_numeric_tables(chunks)
        if not tables:
            if flagged:
                logger.info("Numeric query: no numeric table in %d chunks", len(chunks))
            return False
        if not flagged and not analysis.wants_list and not any(
            column_named(t.columns[i], question) for t in tables for i in t.numeric_columns
        ):
            return False
        try:
            raw, _, _ = await asyncio.wait_for(
                self.llm_service.generate(
                    messages=numeric_planner_messages(plan.standalone_query, tables, analysis.aggregate),
                    model=request.model, temperature=0.0, max_tokens=220, authorization=authorization,
                ),
                timeout=rag_settings.query_analysis_timeout + 4 + self._llm_wait_allowance(),
            )
        except Exception as exc:  # noqa: BLE001 - fall back to generation
            logger.info("Numeric planner failed (%s); using generation", exc)
            return False
        nplan = parse_numeric_plan(raw, tables)
        if nplan is None:
            logger.info("Numeric planner not applicable: %s", (raw or "")[:300].replace("\n", " "))
            trace_stage("numeric", applied=False, reason="planner_not_applicable", tables=len(tables), planner=(raw or "")[:500])
            return False
        if not flagged:
            # Unflagged: a computation (ranking, extremum, total) or a list of a column the question names.
            grounded = column_named(nplan.column, question)
            if not (grounded or (analysis.wants_list and nplan.operation != "lookup")):
                trace_stage("numeric", applied=False, reason="not_grounded", operation=nplan.operation,
                            column=nplan.column, planner=(raw or "")[:500])
                return False
        nplan.tables = expand_to_families(nplan.tables, tables, question)
        nplan.tables = [t for t in nplan.tables if t.column_index(nplan.column) is not None]
        # Row labels the question does not name are the planner's recollection, not a filter: "list every
        # source" must not stop at the thirteen it remembered.
        nplan.rows = [r for r in nplan.rows if label_named(r, question)]
        listing = nplan.operation == "lookup" or (analysis.wants_list and nplan.operation in ("sort_desc", "sort_asc"))
        result = compute_numeric_answer(nplan, max_rows=NUMERIC_LIST_MAX_ROWS if listing else NUMERIC_SORT_MAX_ROWS)
        trace_stage("numeric", applied=result is not None, operation=nplan.operation, column=nplan.column,
                    tables=len(nplan.tables), planner=(raw or "")[:500])
        if result is None:
            return False
        body, sources = result
        sources = unique_in_order_objects(sources)
        raw_citations, _ = prompt_builder.build_context_and_citations(
            [CandidateWrapper(c) for c in sources], query=plan.standalone_query
        )
        cited = _deduplicate_citations(raw_citations)
        plan.kind, plan.intent = "direct", "QA_NUMERIC"
        body, img_tail = self._render_answer_images(body, cited, raw_citations, sources, "", plan.section_pool)
        plan.answer = body + img_tail + build_sources_footer(cited)
        plan.direct_citations = cited
        plan.context_chunks = list(sources)
        logger.info("Numeric query: %s %s over %d table(s)", nplan.operation, nplan.column, len(nplan.tables))
        return True

    async def _plan_structured_listing(
        self,
        plan: "_TurnPlan",
        request: RagChatRequestDTO,
        document_chunks: List[Dict[str, Any]],
        authorization: Optional[str],
        top_passage: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Answers a listing/comparison question from parsed table rows; False when not applicable.
        `top_passage`: the clearly best passage of the search, which a listing must not leave out.
        """
        analysis = plan.analysis
        # Counting the items of a table is listing them and stating how many (never estimated by the model).
        counting = bool(analysis.aggregate == "count" or analysis.count_unit)
        explicit = (analysis.wants_list or analysis.compare or counting
                    or analysis.answer_format in ("table", "checklist"))
        # The analyzer's list flag is unreliable on small models: over tabular documents the planner also
        # decides for open questions (no identifier typed, no brevity asked), but then only a real list
        # (several items) is answered this way.
        auto = (rag_settings.structured_listing_auto and not analysis.wants_brief
                and not extract_identifiers(request.query))
        if not (rag_settings.structured_listing_enabled and document_chunks and (explicit or auto)):
            return False
        items = row_items(parse_table_rows(document_chunks))
        schema = build_schema(items)
        if schema is None or len(items) < STRUCTURED_MIN_ITEMS:
            logger.info("Structured listing skipped: %d table items in %d chunks", len(items), len(document_chunks))
            return False
        listing_asked = analysis.wants_list or analysis.compare or analysis.answer_format in ("table", "checklist")
        if counting and not listing_asked:
            # Only a count of what the table enumerates (its items or its groups) is counted here:
            # "how many periods a week" is not answered by counting requirements.
            item_column = items[0].row.columns[items[0].column] if items[0].column < len(items[0].row.columns) else ""
            unit = analysis.count_unit or ""
            if not unit or not any(counts_column(unit, col) for col in (item_column, schema.group_column) if col):
                logger.info("Structured count skipped: unit %r is not what the table lists", unit)
                return False
        first_table = min((it.row.order[0] for it in items), default=0)
        convention = "\n".join(
            strip_breadcrumb(candidate_text(c)) for c in sorted(document_chunks, key=chunk_order_key)
            if int(payload_of(c).get("chunk_index", 0) or 0) < first_table
        )
        question = f"{request.query} {plan.standalone_query}"
        wanted = question_filters(question, items, schema)
        raw = ""
        try:
            raw, _, _ = await asyncio.wait_for(
                self.llm_service.generate(
                    messages=planner_messages(plan.standalone_query, schema, convention),
                    model=request.model, temperature=0.0, max_tokens=260, authorization=authorization,
                ),
                timeout=rag_settings.query_analysis_timeout + 4 + self._llm_wait_allowance(),
            )
        except Exception as exc:  # noqa: BLE001 - fall back to the filters named in the question
            logger.info("Structured listing planner failed (%s)", exc)
        tplan = parse_plan(raw, schema) if raw else None
        if tplan is None or not tplan.applicable:
            if not (explicit and wanted.any):
                logger.info("Structured listing not applicable: %s", (raw or "")[:300].replace("\n", " "))
                return False
            # A list / count question naming a section, group or item kind of the table is a listing
            # whatever the small planner said.
            item_column = items[0].row.columns[items[0].column] if items[0].column < len(items[0].row.columns) else ""
            asks_groups = names_value(schema.group_column, question) and not names_value(item_column, question)
            tplan = TablePlan(applicable=True, sections=[], groups=[], terms=[], identifier_regex=None,
                              group_by="group", level="groups" if asks_groups and not wanted.segment else "items")
        tplan = refine_plan(tplan, question, schema)
        tplan, selected = reconcile_plan(tplan, wanted, items, schema, rag_settings.structured_max_items)
        reject = self._structured_reject_reason(tplan, selected, explicit, top_passage, schema, question)
        trace_stage("structured_listing", items=len(items), selected=len(selected), explicit=explicit,
                    level=tplan.level, planner=(raw or "")[:500], used=not reject, reject=reject)
        if reject:
            logger.info("Structured listing not used (%s): %s", reject, (raw or "")[:300].replace("\n", " "))
            return False
        body = render_items(selected, schema, tplan.group_by, analysis.answer_format, level=tplan.level)
        sources = unique_in_order_objects(it.row.source for it in selected)
        raw_citations, _ = prompt_builder.build_context_and_citations([CandidateWrapper(c) for c in sources], query=plan.standalone_query)
        cited = _deduplicate_citations(raw_citations)
        title = selected[0].row.title
        # A count is stated only for whole sections / groups: items found by a term are not "all of" anything.
        summary_line = "" if (tplan.terms and not counting) else listing_summary(
            selected, schema, tplan.level, truncated=len(selected) >= rag_settings.structured_max_items)
        intro = " ".join(p for p in (f"Theo tài liệu «{title}»:" if title else "", summary_line) if p)
        if analysis.compare:
            summary = await self._compare_summary(plan, request, body, document_chunks, authorization)
            intro = summary or intro
        plan.kind, plan.intent = "direct", "QA_STRUCTURED"
        body, img_tail = self._render_answer_images(body, cited, raw_citations, sources, "", plan.section_pool)
        plan.answer = ((f"{intro}\n\n" if intro else "") + body
                       + img_tail + build_sources_footer(cited))
        plan.direct_citations = cited
        plan.context_chunks = list(sources)
        logger.info("Structured listing: %d items (%s level) from %d rows", len(selected), tplan.level, len(items))
        return True

    @staticmethod
    def _structured_reject_reason(
        tplan: Any, selected: List[Any], explicit: bool, top_passage: Optional[Dict[str, Any]],
        schema: Any = None, question: str = "",
    ) -> str:
        """Why a planned listing must not answer the question ('' when it may)."""
        if not selected:
            return "nothing selected"
        if not tplan.has_filter and tplan.level != "groups":
            # Every item of the document is not an answer; it is a planner that found no filter.
            return "no filter"
        if (tplan.level == "groups" and not tplan.has_filter and schema is not None and schema.group_column
                and not names_value(schema.group_column, question)):
            # The names of every group of the document answer "which <groups> are there", which the
            # question would say; a question about something else ("the steps to write a prompt") is not
            # answered by the document's table of contents.
            return "groups not asked"
        if not explicit and len(selected) < STRUCTURED_AUTO_MIN_SELECTED:
            return f"{len(selected)} item(s) for an open question"
        if tplan.terms and not (tplan.sections or tplan.groups) and len(selected) < STRUCTURED_AUTO_MIN_SELECTED:
            # A term found in one or two items is a lookup of those items, which generation answers better.
            return "term lookup"
        if top_passage is not None:
            top_ids = {i.upper() for i in extract_identifiers(candidate_text(top_passage))}
            if top_ids and not top_ids & {it.identifier.upper() for it in selected}:
                # The best passage of the search is not in the listing: the planner picked other groups.
                return "disagrees with the best passage"
        return ""

    async def _compare_summary(
        self, plan: "_TurnPlan", request: RagChatRequestDTO, body: str, document_chunks: List[Dict[str, Any]],
        authorization: Optional[str],
    ) -> str:
        """Two or three sentences comparing the listed sections, verified against the passages."""
        messages = [
            {"role": "system", "content": (
                "Dựa DUY NHẤT vào danh sách mục dưới đây, viết 2–3 câu tiếng Việt nêu điểm khác nhau / sự phát triển giữa "
                "các phần theo câu hỏi. Không thêm thông tin ngoài danh sách, không liệt kê lại toàn bộ."
            )},
            {"role": "user", "content": f"CÂU HỎI: {plan.standalone_query}\n\nDANH SÁCH:\n{body[:6000]}"},
        ]
        try:
            raw, _, _ = await self.llm_service.generate(
                messages=messages, model=request.model, temperature=0.0, max_tokens=220, authorization=authorization
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Comparison summary failed: %s", exc)
            return ""
        ctx = SanitizeContext(grounding=build_grounding(document_chunks, document_chunks, False, True))
        text, _, refused = sanitize_answer(raw, ctx)
        return "" if refused else text.strip()

    async def _build_prompt_within_window(
        self,
        plan: "_TurnPlan",
        request: RagChatRequestDTO,
        query: str,
        chosen: List[Dict[str, Any]],
        scores: Dict[str, float],
    ) -> None:
        """
        Builds the stuff prompt so that prompt + completion fit the runtime's context window: the
        lowest-scoring passages are dropped first (document cards and the best passage are kept) and
        the completion budget is capped to what the prompt leaves.
        """
        try:
            window = await self.llm_service.context_window(request.model)
        except Exception as exc:  # noqa: BLE001 - sizing is best effort
            logger.debug("Context window lookup failed: %s", exc)
            window = None
        cpt = max(rag_settings.llm_chars_per_token, 1.0)
        history_text = "\n".join(m.get("content") or "" for m in plan.generation_history)
        wanted = request.max_tokens or 1024
        floor = min(wanted, rag_settings.llm_min_completion_tokens)
        chosen, selected = list(chosen), len(chosen)
        count_tokens = getattr(self.llm_service, "count_tokens", None)
        while True:
            plan.wrapped = [CandidateWrapper(c) for c in chosen]
            plan.raw_citations, plan.system_prompt = prompt_builder.build_context_and_citations(plan.wrapped, query=query)
            if not window:
                break
            full = f"{plan.system_prompt}\n{history_text}\n{plan.user_content}"
            exact = None
            if count_tokens is not None:
                try:
                    exact = await count_tokens(full, request.model)
                except Exception as exc:  # noqa: BLE001 - sizing is best effort
                    logger.debug("Token count failed: %s", exc)
            # Chat template markup adds a few tokens per message on top of the contents.
            prompt_tokens = (exact + PROMPT_TEMPLATE_TOKENS * (2 + len(plan.generation_history))
                             if isinstance(exact, int) else int(len(full) / cpt))
            if prompt_tokens + floor + rag_settings.llm_prompt_safety_tokens <= window or len(chosen) <= 1:
                break
            droppable = [i for i, c in enumerate(chosen) if candidate_key(c) in scores]
            if len(droppable) <= 1:
                break
            chosen.pop(min(droppable, key=lambda i: scores[candidate_key(chosen[i])]))
        plan.context_chunks = chosen
        plan.max_tokens = wanted
        if window:
            left = window - prompt_tokens - rag_settings.llm_prompt_safety_tokens
            plan.max_tokens = max(128, min(wanted, left))
            if len(chosen) < selected or plan.max_tokens < wanted:
                logger.info(
                    "Prompt fitted to %d-token window: %d/%d passages, ~%d prompt tokens, completion %d tokens",
                    window, len(chosen), selected, prompt_tokens, plan.max_tokens,
                )

    async def _make_refusal_plan(
        self,
        plan: "_TurnPlan",
        request: RagChatRequestDTO,
        tenant_id: str,
        user_id: str,
        session_id: str,
        authorization: Optional[str] = None,
    ) -> None:
        """No answer from the documents: record feedback, decline by policy, or escalate with a ticket."""
        support = plan.support or await self._support_for_tenant(tenant_id)
        if plan.unverified_feedback:
            ticket_id, plan.escalation = await self._record_ticket(
                session_id, tenant_id, user_id, request.query, reason="user_feedback"
            )
            plan.kind, plan.intent, plan.status, plan.is_refusal = "direct", "FEEDBACK", "success", False
            plan.answer = support.feedback(ticket_id, plan.titles, plan.outline)
            return
        if rag_settings.policy_check_on_refusal:
            category = await self.query_analyzer.policy_category(request.query, self.llm_service, request.model, authorization)
            if category:
                plan.kind, plan.intent, plan.status = "direct", "OUT_OF_SCOPE", "success"
                plan.is_refusal, plan.escalation = False, None
                plan.answer = support.out_of_scope(category)
                return
        ticket_id, escalation = await self._record_ticket(
            session_id, tenant_id, user_id, request.query,
            reason="out_of_domain_or_insufficient_evidence", top1_score=plan.top_score,
        )
        plan.kind, plan.intent, plan.status = "direct", "REFUSAL", "escalation_required"
        plan.is_refusal, plan.escalation = True, escalation
        plan.answer = support.not_found(ticket_id, plan.titles, plan.outline)

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

    @staticmethod
    def _answer_temperature(request: RagChatRequestDTO) -> float:
        t = float(request.temperature if request.temperature is not None else 0.0)
        return min(t, rag_settings.generation_temperature_max) if rag_settings.generation_temperature_max >= 0 else t

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
            messages=init_msgs, model=request.model, temperature=self._answer_temperature(request),
            max_tokens=request.max_tokens, authorization=authorization,
        )
        last = len(plan.wrapped) if include_last else len(plan.wrapped) - 1
        for idx in range(1, last):
            step_msgs = prompt_builder.build_refine_step_prompt(
                existing_answer=current, next_chunk=plan.wrapped[idx], query=plan.standalone_query, chunk_index=idx + 1
            )
            refined, p, c = await self.llm_service.generate(
                messages=step_msgs, model=request.model, temperature=self._answer_temperature(request),
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
                    messages=msgs, model=request.model, temperature=self._answer_temperature(request),
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
            messages=self._stuff_messages(plan), model=request.model, temperature=self._answer_temperature(request),
            max_tokens=plan.max_tokens or request.max_tokens, authorization=authorization,
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
        max_tokens = request.max_tokens
        if messages is None:
            messages = self._stuff_messages(plan)
            max_tokens = plan.max_tokens or request.max_tokens
        async for token in self.llm_service.stream_generate(
            messages=messages, model=request.model, temperature=self._answer_temperature(request),
            max_tokens=max_tokens, authorization=authorization,
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
        authorization: Optional[str] = None,
    ) -> Tuple[str, List[Dict[str, Any]], str]:
        """
        Returns (text still to deliver, cited sources, intent). A model refusal over passages that contain
        the asked-about terms is regenerated extractively; otherwise it becomes a support reply and
        plan.answer_replaced is set. Items as relevant as the cited ones but missing are appended.
        """
        undelivered = ""
        if plan.sanitize_ctx is not None and plan.sanitize_ctx.leaked:
            # The model was talked into reproducing its instructions: withhold the answer entirely.
            # Not a missing-information refusal, so no regeneration and no support ticket.
            plan.kind, plan.intent, plan.status, plan.is_refusal = "direct", "OUT_OF_SCOPE", "success", False
            plan.answer = (plan.support or self.support).out_of_scope("cấu hình nội bộ của hệ thống")
            plan.answer_replaced = True
            trace_stage("route", route="prompt_disclosure_blocked", intent=plan.intent)
            return plan.answer, [], plan.intent
        # Verification can cut every sentence that said something, leaving only a no-information opening
        # or a bare citation marker: that is a refusal (support reply, ticket), not an answer.
        if refused or not has_substantive_content(clean_text):
            recovered = await self._recover_refusal(plan, request, authorization)
            if recovered is None:
                await self._make_refusal_plan(plan, request, tenant_id, user_id, session_id, authorization)
                plan.answer_replaced = True
                trace_stage("route", route="generation_refusal", intent=plan.intent)
                return plan.answer, [], plan.intent
            clean_text, marker_map = recovered
            undelivered = clean_text  # nothing of a refused stream has reached the client
        if plan.strategy in SYNTHESIS_STRATEGIES:
            # Multi-pass synthesis keeps the original markers; every passage it read is a source.
            cited = _deduplicate_citations(plan.raw_citations)
        elif marker_map:
            cited = remap_citations(plan.raw_citations, marker_map)
        else:
            cited = _filter_attributed_citations(_deduplicate_citations(plan.raw_citations), clean_text, strategy=plan.strategy)
        tail = undelivered
        if rag_settings.completeness_enabled and plan.context_chunks:
            grounding = plan.sanitize_ctx.grounding if plan.sanitize_ctx is not None else None
            extra = missing_items(
                plan.standalone_query, plan.analysis.focus_terms, clean_text, plan.context_chunks,
                rag_settings.completeness_relative_score, rag_settings.completeness_max_items,
                require_anchor=not plan.analysis.wants_location,
                exclude=grounding.example_identifiers if grounding is not None and not grounding.allow_examples else (),
            )
            tail += format_missing(extra)
        # Images go under the steps they illustrate; only those the answer gives no place follow it in a block.
        body, img_tail = self._render_answer_images(
            clean_text, cited, cited, plan.context_chunks, tenant_id, plan.section_pool
        )
        if body != clean_text:
            if undelivered:
                tail = body + tail[len(undelivered):]  # nothing was streamed yet: the placed text is sent
            else:
                plan.inline_body = body  # already streamed: the client re-renders it (reset), the tail follows
        tail += img_tail
        tail += build_sources_footer(cited)
        if rag_settings.suggestions_enabled and not plan.analysis.wants_brief:
            tail += build_suggestions(clean_text, plan.suggestion_pool)
        return tail, cited, f"QA_{plan.strategy.upper()}"

    @staticmethod
    def _media_mapper(passages: Sequence[Dict[str, Any]], tenant_id: str) -> Optional[Any]:
        """Image URL of a passage -> signed URL the browser can load (None when images are disabled)."""
        if not rag_settings.media_enabled:
            return None
        return media_assets.url_mapper(
            passages, media_secret(), rag_settings.media_path_prefix, rag_settings.media_url_ttl_seconds,
            default_tenant=normalize_tenant_id(tenant_id) if tenant_id else "",
        )

    def _render_answer_images(
        self,
        body: str,
        cited: List[Dict[str, Any]],
        image_sources: Sequence[Dict[str, Any]],
        passages: Sequence[Dict[str, Any]],
        tenant_id: str,
        section_pool: Sequence[Dict[str, Any]] = (),
        interleave: bool = True,
    ) -> Tuple[str, str]:
        """
        (body with the images of its sources placed under the steps they illustrate, block of the images left).
        Cited passages also get their own (signed) image URLs. A figure belongs to its section: a cited passage
        brings the images of the other passages of the same section of its document.
        """
        mapper = self._media_mapper(list(passages) + list(image_sources) + list(section_pool), tenant_id)
        if mapper is None:
            return body, ""
        prefix = rag_settings.media_path_prefix

        def section_mates(c: Dict[str, Any]) -> List[Dict[str, Any]]:
            heading = str(c.get("heading") or "").strip()
            doc_id = str(c.get("doc_id") or "")
            if not heading:
                return [c]
            def names_of(p: Dict[str, Any]) -> set:
                pl = payload_of(p)
                return {str(pl.get("heading") or "").strip(), str(pl.get("heading_path") or "").strip(),
                        (candidate_heading(p) or "").strip()} - {""}

            mates = [p for p in section_pool if str(payload_of(p).get("doc_id") or "") == doc_id
                     and heading in names_of(p)]
            return [c] + mates

        for c in cited:
            c["images"] = [mapper(media_assets.media_path(prefix, i.doc_id, i.filename))
                           for i in media_assets.passage_images(section_mates(c), prefix)][:CITATION_MAX_IMAGES]

        shown = media_assets.shown_files(body, prefix)
        picked: List[Any] = []
        source_of: Dict[str, int] = {}
        index_of_doc = {str(c.get("doc_id")): int(c.get("index", 0) or 0) for c in cited}
        all_pool = list(image_sources) + list(passages) + list(section_pool)
        for src in image_sources:
            for img in media_assets.passage_images(section_mates(src), prefix):
                if img.filename in shown or img.filename in source_of:
                    continue
                source_of[img.filename] = int(src.get("index", 0) or 0) or index_of_doc.get(img.doc_id, 0)
                picked.append(img)
        picked = picked[: rag_settings.media_max_images_per_answer]

        if not interleave:
            return body, media_assets.images_section(picked, mapper, prefix, {k: v for k, v in source_of.items() if v})
        augmented_body, unplaced = media_assets.interleave_inline_images(
            body, picked, all_pool, mapper, prefix, source_of
        )
        tail = media_assets.images_section(unplaced, mapper, prefix, {k: v for k, v in source_of.items() if v})
        return augmented_body, tail

    def _attach_images(
        self,
        cited: List[Dict[str, Any]],
        image_sources: Sequence[Dict[str, Any]],
        passages: Sequence[Dict[str, Any]],
        tenant_id: str,
        shown_text: str,
        section_pool: Sequence[Dict[str, Any]] = (),
    ) -> str:
        """The block of images after an answer whose text is final (none of them is placed in that text)."""
        _body, tail = self._render_answer_images(
            shown_text, cited, image_sources, passages, tenant_id, section_pool, interleave=False
        )
        return tail

    def _correction_hints(self, plan: "_TurnPlan") -> List[str]:
        ctx = plan.sanitize_ctx
        if ctx is None or ctx.grounding is None:
            return []
        return unique_in_order(ctx.grounding.hint(problem) for problem, _ in ctx.dropped)

    async def _corrected_answer(
        self, plan: "_TurnPlan", request: RagChatRequestDTO, authorization: Optional[str]
    ) -> Optional[Tuple[str, Dict[int, int]]]:
        """
        Verification removed sentences (unsupported figures, wrong counting unit, unknown identifiers):
        regenerate once, telling the model exactly what was wrong and what the document says instead.
        """
        hints = self._correction_hints(plan)
        if not hints or plan.kind != "generate":
            return None
        messages = self._stuff_messages(plan)
        messages[-1] = {"role": "user", "content": messages[-1]["content"] + (
            "\n(KIỂM TRA LẠI – câu trả lời trước có chi tiết sai so với tài liệu:\n- " + "\n- ".join(hints)
            + "\nViết lại câu trả lời: chép đúng con số kèm đúng đơn vị như câu tài liệu gốc, không ước lượng, "
            "không dùng số không có trong tài liệu.)"
        )}
        plan.sanitize_ctx.dropped.clear()
        t0 = time.perf_counter()
        try:
            raw, _, _ = await self.llm_service.generate(
                messages=messages, model=request.model, temperature=0.0,
                max_tokens=plan.max_tokens or request.max_tokens, authorization=authorization,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Corrective regeneration failed: %s", exc)
            trace_stage("correction", ms=(time.perf_counter() - t0) * 1000, hints=hints, accepted=False,
                        error=type(exc).__name__)
            return None
        text, marker_map, refused = sanitize_answer(raw, plan.sanitize_ctx)
        # A rewrite that verification still has to cut is not a correction: the model is guessing
        # (told a code is wrong, it invents a neighbouring one).
        accepted = bool(text.strip()) and not refused and not plan.sanitize_ctx.dropped
        trace_stage("correction", ms=(time.perf_counter() - t0) * 1000, hints=hints, accepted=accepted,
                    raw_answer=raw, dropped=dropped_sentences(plan.sanitize_ctx.dropped))
        if accepted:
            logger.info("Answer corrected after verification (%d hint(s))", len(hints))
            return text, marker_map
        return None

    async def _recover_refusal(
        self, plan: "_TurnPlan", request: RagChatRequestDTO, authorization: Optional[str]
    ) -> Optional[Tuple[str, Dict[int, int]]]:
        """Self-RAG style check of a refusal: the passages contain the asked-about terms, so answer from them."""
        corrected = await self._corrected_answer(plan, request, authorization)
        if corrected is not None:
            return corrected
        # Only a specific asked-about term found in the passages suggests the refusal is wrong; every
        # specific term must be there (a question about "certificates for teachers" is not answered by
        # passages that only mention teachers).
        focus = specific_focus_terms(plan.analysis.focus_terms, plan.analysis.scope_terms, plan.titles,
                                     plan.context_chunks)
        if not (rag_settings.refusal_verify_enabled and plan.kind == "generate" and focus
                and all(focus_present([t], plan.context_chunks) for t in focus)):
            trace_stage("refusal_recovery", method="not_applicable", focus=list(focus),
                        asked=list(plan.analysis.focus_terms))
            return None
        shown = ", ".join(f"«{t}»" for t in focus)
        messages = self._stuff_messages(plan)
        messages[-1] = {"role": "user", "content": messages[-1]["content"] + (
            f"\n(Các đoạn tài liệu CÓ nhắc tới {shown}. Trước hết chép nguyên văn dòng chứa nội dung đó kèm mã và mục, "
            "sau đó trả lời câu hỏi trong 1–2 câu. Không dùng câu từ chối.)"
        )}
        try:
            raw, _, _ = await self.llm_service.generate(
                messages=messages, model=request.model, temperature=0.0,
                max_tokens=plan.max_tokens or request.max_tokens, authorization=authorization,
            )
            text, marker_map, refused = sanitize_answer(raw, plan.sanitize_ctx)
            if text.strip() and not refused:
                logger.info("Refusal recovered by extractive regeneration")
                trace_stage("refusal_recovery", method="extractive_regeneration", raw_answer=raw)
                return text, marker_map
        except Exception as exc:  # noqa: BLE001 - fall back to the deterministic extract
            logger.warning("Extractive regeneration failed: %s", exc)
        extract = extractive_answer(focus, plan.context_chunks)
        if extract:
            logger.info("Refusal replaced by deterministic extract")
            trace_stage("refusal_recovery", method="deterministic_extract")
            return extract, {}
        trace_stage("refusal_recovery", method="none")
        return None

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Turn tracing (stage inputs/outputs persisted per turn)
    # ------------------------------------------------------------------

    @staticmethod
    def _config_snapshot() -> Dict[str, Any]:
        """Settings that change answers, stored with each trace so runs are comparable."""
        keys = (
            "gate_min_rerank_score", "gate_min_lexical_coverage", "context_max_chunks", "context_char_budget",
            "context_char_budget_point", "context_relative_cutoff", "context_list_relative_cutoff",
            "numeric_tables_enabled", "structured_listing_enabled", "identifier_grounding_enabled",
            "unit_grounding_enabled", "generation_history_mode", "multi_query_on_weak_evidence",
            "hyde_auto_enabled", "generation_temperature_max",
        )
        return {k: getattr(rag_settings, k, None) for k in keys}

    def _begin_trace(
        self, request: RagChatRequestDTO, tenant_id: str, user_id: str, trace_id: Optional[str], endpoint: str
    ) -> TurnTrace:
        return begin_turn(
            tenant_id=normalize_tenant_id(tenant_id), session_id=request.conversation_id or "", user_id=user_id,
            query=request.query, trace_id=trace_id, endpoint=endpoint, model=request.model,
            sample_rate=rag_settings.trace_sample_rate, config=self._config_snapshot(),
        )

    def _finish_trace(self, trace: TurnTrace) -> None:
        """Records quality metrics from the trace and persists it in the background (never fails the turn)."""
        end_turn()
        routes = [s for s in trace.stages if s["stage"] == "route"]
        route = routes[-1]["route"] if routes else ("cache" if trace.stage("cache") else "unknown")
        trace.outcome.setdefault("route", route)
        self.obs.record_answer_outcome(
            route, str(trace.outcome.get("intent") or ""), bool(trace.outcome.get("is_refusal")), tenant_id=trace.tenant_id
        )
        problems = [d["problem"] for s in trace.stages if s["stage"] in ("verification", "correction")
                    for d in s.get("dropped") or []]
        corrections = [s for s in trace.stages if s["stage"] == "correction"]
        if problems or corrections:
            self.obs.record_verification(
                problems, corrections[-1].get("accepted") if corrections else None, tenant_id=trace.tenant_id
            )
        if not (rag_settings.trace_enabled and trace.should_keep()):
            return
        record = trace.to_record(redact=rag_settings.trace_redact_pii)
        task = asyncio.ensure_future(self._save_trace(record))
        self._trace_tasks.add(task)
        task.add_done_callback(self._trace_tasks.discard)

    async def _save_trace(self, record: Dict[str, Any]) -> None:
        try:
            await self.trace_store.save(record)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Saving trace %s failed: %s", record.get("trace_id"), exc)

    async def flush_traces(self) -> None:
        """Waits for pending trace writes (tests, graceful shutdown)."""
        if self._trace_tasks:
            await asyncio.gather(*list(self._trace_tasks), return_exceptions=True)

    @staticmethod
    def _response_outcome(resp: RagChatResponseDTO) -> Dict[str, Any]:
        return {
            "answer": resp.answer,
            "intent": resp.intent,
            "status": resp.status,
            "is_refusal": bool(resp.is_refusal),
            "escalated": bool(resp.escalation),
            "citations": [
                {"index": c.index, "doc_id": c.doc_id, "title": c.title, "section": c.section, "score": c.score}
                for c in resp.citations or []
            ],
            "latency_ms": resp.latency_ms,
            "prompt_tokens": resp.prompt_tokens,
            "completion_tokens": resp.completion_tokens,
        }

    async def execute(
        self,
        request: RagChatRequestDTO,
        tenant_id: str = DEFAULT_TENANT_ID,
        user_id: str = "default_user",
        user_role: str = "user",
        authorization: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> RagChatResponseDTO:
        trace = self._begin_trace(request, tenant_id, user_id, trace_id, endpoint="chat")
        try:
            async with self.admission.turn():
                resp = await self._execute_impl(request, tenant_id, user_id, user_role, authorization)
        except Exception as exc:
            trace.outcome = {"error": type(exc).__name__, "message": str(exc)[:300]}
            self._finish_trace(trace)
            raise
        resp.telemetry = dict(resp.telemetry or {}, trace_id=trace.trace_id)
        trace.session_id = resp.session_id or trace.session_id
        trace.outcome = self._response_outcome(resp)
        self._finish_trace(trace)
        return resp

    async def _execute_impl(
        self,
        request: RagChatRequestDTO,
        tenant_id: str,
        user_id: str,
        user_role: str,
        authorization: Optional[str],
    ) -> RagChatResponseDTO:
        start_t = time.time()
        tenant_id = normalize_tenant_id(tenant_id)
        session_id = request.conversation_id or new_session_id()
        self._truncate_query(request)

        history = await self._resolve_history(session_id, user_id, tenant_id, request.history)
        if not history:
            cached_res = await self._cache_lookup(request, request.query, tenant_id, user_role, session_id, start_t)
            if cached_res:
                trace_stage("cache", hit=True, key="query")
                trace_stage("route", route="cache", intent=cached_res.intent)
                return cached_res

        if request.adhoc_context and request.adhoc_context.strip():
            trace_stage("route", route="adhoc", intent="ADHOC_QA")
            return await self._execute_adhoc(request, history, session_id, tenant_id, user_id, authorization, start_t)

        plan = await self._plan_turn(request, history, tenant_id, user_id, user_role, session_id, authorization)
        rewrite_decision = plan.rewrite
        if history and plan.kind == "generate":
            cached_res = await self._cache_lookup(request, plan.standalone_query, tenant_id, user_role, session_id, start_t)
            if cached_res:
                trace_stage("cache", hit=True, key="standalone_query")
                trace_stage("route", route="cache", intent=cached_res.intent)
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
                answer=plan.answer, citations=plan.direct_citations, model=request.model, intent=plan.intent,
                latency_ms=latency_ms, standalone_query=plan.standalone_query, plan=plan,
            )
            return RagChatResponseDTO(
                answer=plan.answer,
                model=request.model,
                citations=[_build_citation_dto(c) for c in plan.direct_citations],
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
        trace_stage("generation", ms=(time.perf_counter() - t_gen_0) * 1000, strategy=plan.strategy,
                    prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, raw_answer=raw_answer)

        plan.sanitize_ctx.dropped.clear()
        clean_text, marker_map, refused = sanitize_answer(raw_answer, plan.sanitize_ctx)
        trace_stage("verification", refused=refused, dropped=dropped_sentences(plan.sanitize_ctx.dropped))
        if not refused and clean_text.strip() and any(
            p.startswith(("unit:", "number:", "identifier:")) for p, _ in plan.sanitize_ctx.dropped
        ):
            corrected = await self._corrected_answer(plan, request, authorization)
            if corrected is not None:
                clean_text, marker_map = corrected
        tail, cited, intent = await self._finalize_answer(
            plan, request, clean_text, marker_map, refused, tenant_id, user_id, session_id, authorization
        )
        body = plan.inline_body if plan.inline_body is not None else clean_text
        answer = plan.answer if plan.answer_replaced else body + tail
        citation_dtos = [_build_citation_dto(c) for c in cited]
        if citation_dtos and plan.context_chunks:
            self.obs.record_groundedness(min(1.0, len(citation_dtos) / len(plan.context_chunks)), tenant_id=tenant_id)

        latency_ms = (time.time() - start_t) * 1000
        await self._save_session_turn(
            session_id=session_id, user_id=user_id, tenant_id=tenant_id, query=request.query, answer=answer,
            citations=cited, model=request.model, intent=intent, prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens, latency_ms=latency_ms, standalone_query=plan.standalone_query,
            plan=plan,
        )
        resp_dto = RagChatResponseDTO(
            answer=answer,
            model=request.model,
            citations=citation_dtos,
            latency_ms=round(latency_ms, 2),
            intent=intent,
            combine_strategy=plan.strategy,
            session_id=session_id,
            status=plan.status if plan.answer_replaced else "success",
            escalation=plan.escalation if plan.answer_replaced else None,
            is_refusal=plan.is_refusal if plan.answer_replaced else False,
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
            "trace_id": current_trace_id(),
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
        trace_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """SSE variant of execute(). Infrastructure failures end the stream with an explicit error event."""
        session_id = request.conversation_id or new_session_id()
        request.conversation_id = session_id
        trace = self._begin_trace(request, tenant_id, user_id, trace_id, endpoint="stream")
        answer_parts: List[str] = []
        done: Dict[str, Any] = {}
        ttft_ms: Optional[float] = None
        try:
            async with self.admission.turn():
                async for event in self._stream_execute_impl(request, tenant_id, user_id, user_role, authorization):
                    payload = self._sse_payload(event)
                    if "token" in payload:
                        if ttft_ms is None:
                            ttft_ms = round((time.perf_counter() - trace.started) * 1000, 1)
                        answer_parts.append(str(payload["token"]))
                    elif payload.get("done"):
                        done = payload
                    yield event
        except INFRASTRUCTURE_ERRORS as exc:
            message, retry_after, busy = unavailable_reply(exc)
            (logger.warning if busy else logger.error)("RAG stream not served (%s): %s", "busy" if busy else "outage", exc)
            status_value = "busy" if busy else "service_unavailable"
            done = {"status": status_value, "error": type(exc).__name__}
            error_payload = {"error": type(exc).__name__, "message": message, "retry_after": retry_after,
                             "session_id": session_id}
            yield f"event: error\ndata: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
            yield (f"data: {json.dumps({'done': True, 'session_id': session_id, 'status': status_value, 'retry_after': retry_after, 'trace_id': trace.trace_id})}\n\n")
        except BaseException as exc:
            done = done or {"status": "aborted", "error": type(exc).__name__}
            raise
        finally:
            trace.session_id = session_id
            trace.outcome = {
                "answer": "".join(answer_parts),
                "intent": done.get("intent"),
                "status": done.get("status"),
                "is_refusal": bool(done.get("is_refusal")),
                "escalated": bool(done.get("escalation")),
                "citations": [
                    {k: c.get(k) for k in ("index", "doc_id", "title", "section", "score")}
                    for c in done.get("citations") or [] if isinstance(c, dict)
                ],
                "latency_ms": done.get("total_latency_ms"),
                "ttft_ms": ttft_ms,
                **({"error": done["error"]} if done.get("error") else {}),
            }
            self._finish_trace(trace)

    @staticmethod
    def _sse_payload(event: str) -> Dict[str, Any]:
        for line in event.splitlines():
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                except ValueError:
                    return {}
                return data if isinstance(data, dict) else {}
        return {}

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
        session_id = request.conversation_id or new_session_id()
        self._truncate_query(request)

        history = await self._resolve_history(session_id, user_id, tenant_id, request.history)

        if request.adhoc_context and request.adhoc_context.strip():
            trace_stage("route", route="adhoc", intent="ADHOC_QA")
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
            yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'status': 'clarification_needed', 'intent': 'AMBIGUOUS_SYMPTOM', 'clarification': clarification_payload, 'citations': [], 'total_latency_ms': round(latency_ms, 2), 'trace_id': current_trace_id()})}\n\n"
            return

        if plan.kind == "direct":
            latency_ms = (time.time() - start_t) * 1000
            yield self._sse_token(plan.answer, session_id)
            await self._save_session_turn(
                session_id=session_id, user_id=user_id, tenant_id=tenant_id, query=request.query,
                answer=plan.answer, citations=plan.direct_citations, model=request.model, intent=plan.intent,
                latency_ms=latency_ms, standalone_query=plan.standalone_query, plan=plan,
            )
            done = {
                "done": True, "session_id": session_id, "status": plan.status, "intent": plan.intent,
                "escalation": plan.escalation,
                "citations": [_build_citation_dto(c).model_dump() for c in plan.direct_citations],
                "circuit_breaker_triggered": plan.is_refusal,
                "is_refusal": plan.is_refusal, "pre_retrieval_tier": rewrite_decision.tier,
                "ttft_ms": round(latency_ms, 2), "total_latency_ms": round(latency_ms, 2),
                "trace_id": current_trace_id(),
                "hyde_active": plan.hyde.is_active if plan.hyde else False,
                "rerank_top1_score": round(plan.top_score, 4),
                "standalone_query": plan.standalone_query,
            }
            yield f"data: {json.dumps(done, ensure_ascii=False)}\n\n"
            return

        plan.strategy = self._resolve_combine_strategy(getattr(request, "combine_strategy", None), plan.standalone_query, plan.wrapped)
        plan.sanitize_ctx.renumber = plan.strategy not in SYNTHESIS_STRATEGIES
        first_token_time: Optional[float] = None
        t_gen_0 = time.perf_counter()
        restarts = 0
        while True:
            stream_filter = AnswerStreamFilter(plan.sanitize_ctx)
            raw_tokens: List[str] = []
            token_stream = self._generate_stream(plan, request, authorization)
            try:
                async for token in token_stream:
                    raw_tokens.append(token)
                    for piece in stream_filter.feed(token):
                        if first_token_time is None:
                            first_token_time = time.time()
                        yield self._sse_token(piece, session_id)
                    if stream_filter.refused:
                        break  # the model declined: stop generating and escalate instead
            except LLMStreamInterruptedError as exc:
                # The runtime cut the answer off for lack of room under load (busy, not broken): it is
                # generated again, and the runtime guard now lets one call through at a time so the new
                # attempt runs alone. Text already shown is withdrawn with a reset event first.
                if restarts >= STREAM_RESTARTS:
                    raise
                restarts += 1
                logger.warning("Answer stream cut off (%s); generating again%s", exc,
                               " after withdrawing the partial text" if first_token_time else "")
                if first_token_time is not None:
                    yield f"data: {json.dumps({'reset': True, 'session_id': session_id})}\n\n"
                plan.sanitize_ctx.dropped.clear()
                plan.sanitize_ctx.leaked = False
                continue
            finally:
                await token_stream.aclose()
            break
        for piece in stream_filter.finish():
            if first_token_time is None:
                first_token_time = time.time()
            yield self._sse_token(piece, session_id)
        trace_stage("generation", ms=(time.perf_counter() - t_gen_0) * 1000, strategy=plan.strategy,
                    raw_answer="".join(raw_tokens), streamed=True)
        trace_stage("verification", refused=stream_filter.refused,
                    dropped=dropped_sentences(plan.sanitize_ctx.dropped))

        tail, cited, intent = await self._finalize_answer(
            plan, request, stream_filter.text, dict(stream_filter.marker_map), stream_filter.refused,
            tenant_id, user_id, session_id,
        )
        if plan.answer_replaced and plan.answer:
            yield f"data: {json.dumps({'reset': True, 'session_id': session_id})}\n\n"
            yield self._sse_token(plan.answer, session_id)
        elif plan.inline_body is not None:
            # Images placed under their steps: the streamed text is shown again with them, then the tail.
            yield f"data: {json.dumps({'reset': True, 'session_id': session_id})}\n\n"
            yield self._sse_token(plan.inline_body + tail, session_id)
        elif tail:
            if first_token_time is None:
                first_token_time = time.time()
            yield self._sse_token(tail, session_id)
        body = plan.inline_body if plan.inline_body is not None else stream_filter.text
        answer = plan.answer if plan.answer_replaced else body + tail
        latency_ms = (time.time() - start_t) * 1000
        await self._save_session_turn(
            session_id=session_id, user_id=user_id, tenant_id=tenant_id, query=request.query, answer=answer,
            citations=cited, model=request.model, intent=intent, latency_ms=latency_ms,
            standalone_query=plan.standalone_query, plan=plan,
        )
        ttft_ms = round((first_token_time - start_t) * 1000, 2) if first_token_time else None
        done = {
            "done": True,
            "session_id": session_id,
            "status": plan.status if plan.answer_replaced else "success",
            "intent": intent,
            "escalation": plan.escalation if plan.answer_replaced else None,
            "citations": [_build_citation_dto(c).model_dump() for c in cited],
            "combine_strategy": plan.strategy,
            "is_refusal": plan.is_refusal if plan.answer_replaced else False,
            "circuit_breaker_triggered": False,
            "pre_retrieval_tier": rewrite_decision.tier,
            "pre_retrieval_latency_ms": round(plan.analysis.latency_ms, 2),
            "ttft_ms": ttft_ms,
            "total_latency_ms": round(latency_ms, 2),
            "trace_id": current_trace_id(),
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
    def _extract_relevant_adhoc_context(query: str, text: str, max_chars: int) -> str:
        """
        Intelligently extracts the most relevant passages from a large ad-hoc document
        if its size exceeds max_chars, ensuring no section of a multi-page document is lost.
        """
        if len(text) <= max_chars:
            return text

        blocks = [b.strip() for b in re.split(r"\n{2,}|(?=### (?:Trang|Bảng tính|Phần))", text) if b.strip()]
        if len(blocks) <= 1:
            blocks = [p.strip() for p in text.split("\n\n") if p.strip()]

        if not blocks:
            return text[:max_chars]

        query_terms = set(re.findall(r"\w+", query.lower()))
        scored_blocks = []
        for idx, block in enumerate(blocks):
            block_terms = set(re.findall(r"\w+", block.lower()))
            overlap = len(query_terms & block_terms) if query_terms else 1
            scored_blocks.append((overlap, idx, block))

        scored_blocks.sort(key=lambda x: (x[0], -x[1]), reverse=True)

        selected_blocks = []
        cur_chars = 0
        for score, idx, block in scored_blocks:
            if cur_chars + len(block) > max_chars and selected_blocks:
                break
            selected_blocks.append((idx, block))
            cur_chars += len(block)

        selected_blocks.sort(key=lambda x: x[0])
        extracted = "\n\n---\n\n".join(b[1] for b in selected_blocks)

        header_notice = (
            f"[Hệ thống: Tài liệu đính kèm gồm {len(text):,} ký tự. "
            f"Đã tự động trích lọc các phần liên quan nhất ({len(extracted):,} ký tự) tới câu hỏi]:\n\n"
        )
        return header_notice + extracted

    @staticmethod
    def _adhoc_messages(request: RagChatRequestDTO, history: List[Dict[str, str]]) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
        adhoc_title = getattr(request, "adhoc_filename", None) or "Tài liệu đính kèm tạm thời"
        strategy = getattr(request, "adhoc_strategy", None) or ""
        max_chars = getattr(rag_settings, "adhoc_max_context_chars", 64000)

        context_text = RagChatUseCase._extract_relevant_adhoc_context(request.query, request.adhoc_context, max_chars)
        adhoc_excerpt = request.adhoc_context[:350].strip() + "..." if len(request.adhoc_context) > 350 else request.adhoc_context.strip()

        is_table = strategy == "structured_table" or any(adhoc_title.lower().endswith(ext) for ext in (".xlsx", ".xls", ".csv"))
        is_large = strategy == "large_document" or len(request.adhoc_context) > getattr(rag_settings, "adhoc_large_doc_threshold_chars", 40000)

        if is_table:
            system_prompt = (
                f"Bạn là Chuyên gia Phân tích Dữ liệu Bảng tính của AIP Platform. Người dùng đã đính kèm bảng dữ liệu '{adhoc_title}'.\n"
                "Nhiệm vụ của bạn là phân tích chính xác từng dòng, từng cột trong bảng dữ liệu dưới đây để trả lời câu hỏi của người dùng.\n"
                "- Khi thực hiện phép tính (tổng, trung bình, đếm, so sánh, lọc), hãy liệt kê rõ số liệu nguồn từ bảng và tính toán cẩn thận, không được suy đoán hoặc bịa số.\n"
                "- Trình bày kết quả rõ ràng, sử dụng bảng Markdown hoặc danh sách có cấu trúc.\n\n"
                f"=== DỮ LIỆU BẢNG TÍNH ({adhoc_title}) ===\n"
                f"{context_text}\n"
                "=========================================="
            )
        elif is_large:
            system_prompt = (
                f"Bạn là Trợ lý AI Chuyên nghiệp của AIP Platform. Người dùng đã đính kèm tài liệu dài '{adhoc_title}'.\n"
                "Hệ thống đã tự động trích lọc các đoạn thông tin liên quan nhất từ toàn bộ tài liệu để bạn xử lý.\n"
                "Nhiệm vụ của bạn là đọc kỹ các trích đoạn bên dưới và trả lời câu hỏi của người dùng một cách chính xác, trung thực, có cấu trúc rõ ràng.\n"
                "Nếu thông tin không có trong các đoạn trích, hãy thành thật nêu rõ không có trong tài liệu.\n\n"
                f"=== TRÍCH ĐOẠN TÀI LIỆU LIÊN QUAN ({adhoc_title}) ===\n"
                f"{context_text}\n"
                "=================================================="
            )
        else:
            system_prompt = (
                f"Bạn là Trợ lý AI Chuyên nghiệp của AIP Platform. Người dùng đã đính kèm tài liệu cá nhân '{adhoc_title}'.\n"
                "Nhiệm vụ của bạn là đọc kỹ tài liệu đính kèm bên dưới và trả lời câu hỏi của người dùng một cách chính xác, trung thực, có cấu trúc rõ ràng (bảng biểu, gạch đầu dòng nếu phù hợp).\n"
                "Nếu thông tin không có trong tài liệu, hãy thành thật nêu rõ không có trong tài liệu.\n\n"
                f"=== NỘI DUNG TÀI LIỆU ĐÍNH KÈM ({adhoc_title}) ===\n"
                f"{context_text}\n"
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
            messages=messages, model=request.model, temperature=self._answer_temperature(request),
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
            messages=messages, model=request.model, temperature=self._answer_temperature(request),
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
        plan: Optional["_TurnPlan"] = None,
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
            if plan is not None:
                user_msg.update(_turn_memory_user(plan))
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
                **_turn_memory_assistant(answer, intent),
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
