"""
LLM Query Analysis: conversational query rewriting + intent detection in a single call.

One small JSON-producing LLM call per turn replaces keyword lists for both problems:
- multi-turn rewriting (pronouns, ellipsis, "the first question I asked", corrections, topic
  switches, interruptions) produces a self-contained retrieval query;
- intent detection routes support requests, feedback, contact details, ticket-status questions,
  greetings and out-of-scope requests away from document QA. The out-of-scope categories come from
  tenant configuration, so no domain vocabulary lives in code.

If the model is unavailable, times out or returns malformed JSON, the turn is treated as a document
question and the previous user turn is concatenated to short follow-ups (the classic
"concatenate previous turns" strategy), so the pipeline degrades gracefully instead of refusing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from .lexical_evidence import extract_identifiers

logger = logging.getLogger("aip-rag.query-analyzer")

ANALYZER_MARKER = "[QUERY_ANALYZER]"


class Intent(str, Enum):
    DOCUMENT_QUESTION = "document_question"
    SUPPORT_REQUEST = "support_request"
    FEEDBACK = "feedback"
    CONTACT_INFO = "contact_info"
    DECLINE_CONTACT = "decline_contact"
    TICKET_STATUS = "ticket_status"
    GREETING = "greeting"
    OUT_OF_SCOPE = "out_of_scope"
    UNCLEAR = "unclear"


@dataclass
class QueryAnalysis:
    intent: Intent
    standalone_query: str
    original_query: str
    new_topic: bool = False
    challenge: bool = False
    about_document: bool = False
    wants_list: bool = False
    wants_brief: bool = False
    out_of_scope_category: str = ""
    phone: str = ""
    focus_terms: List[str] = field(default_factory=list)  # the thing asked about, in the user's words
    scope_terms: List[str] = field(default_factory=list)  # conditions narrowing it (section, level, period…)
    wants_location: bool = False  # asks where something is (which section / level / code)
    answer_format: str = ""  # "list" | "table" | "checklist" | "" (free text)
    compare: bool = False  # compares or traces something across several sections
    aggregate: str = ""  # computation over figures: max | min | diff | sum | avg | sort | count
    count_unit: str = ""  # what is being counted / measured, in the user's words
    source: str = "llm"  # "llm" | "fallback"
    latency_ms: float = 0.0
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_document_question(self) -> bool:
        return self.intent == Intent.DOCUMENT_QUESTION


HISTORY_HEAD_CHARS = 220
HISTORY_TAIL_CHARS = 180
ANSWER_FORMATS = ("list", "table", "checklist")
AGGREGATES = ("max", "min", "diff", "sum", "avg", "sort", "count")

PHONE_RE = re.compile(r"(?<![\d])((?:\+?\d{1,3}[\s.\-]?)?(?:\d[\s.\-]?){8,11}\d)(?![\d])")


def _system_prompt(out_of_scope_policy: str) -> str:
    return (
        f"{ANALYZER_MARKER} Bạn là bộ phân tích tin nhắn cho trợ lý tra cứu tài liệu nội bộ của doanh nghiệp.\n"
        "Đọc lịch sử hội thoại và TIN NHẮN MỚI NHẤT, trả về DUY NHẤT một đối tượng JSON, không giải thích:\n"
        '{"intent": "...", "standalone_query": "...", "focus": [], "scope": [], "new_topic": false, "challenge": false, '
        '"about_document": false, "wants_list": false, "wants_brief": false, "wants_location": false, '
        '"format": "", "compare": false, "aggregate": "", "count_unit": "", "out_of_scope_category": "", "phone": ""}\n'
        "Viết JSON gọn: luôn có intent và standalone_query; các trường khác CHỈ ghi khi khác mặc định "
        "(true, danh sách hoặc chuỗi không rỗng), bỏ hẳn các trường false/rỗng.\n\n"
        "intent là một trong:\n"
        "- document_question: hỏi nội dung có thể có trong tài liệu, kể cả câu hỏi nối tiếp, câu phản bác hoặc đính chính câu trả lời trước.\n"
        "- support_request: muốn gặp/nói chuyện với người hỗ trợ, kỹ thuật viên, hỏi hotline hoặc cách liên hệ.\n"
        "- feedback: báo lỗi, phàn nàn, nói câu trả lời trước chưa đúng ý mà không kèm câu hỏi mới.\n"
        "- contact_info: tin nhắn cung cấp số điện thoại hoặc thông tin liên hệ của chính người dùng.\n"
        "- decline_contact: từ chối để lại thông tin liên hệ.\n"
        "- ticket_status: hỏi câu hỏi/yêu cầu trước đó đã được ghi nhận hoặc chuyển người phụ trách chưa.\n"
        "- greeting: chỉ chào hỏi, cảm ơn, tạm biệt.\n"
        f"- out_of_scope: thuộc các nhóm bị từ chối theo chính sách: {out_of_scope_policy}.\n"
        "- unclear: quá chung chung, chưa xác định được cần tra cứu nội dung gì.\n\n"
        "standalone_query (chỉ khi intent là document_question): viết lại tin nhắn mới nhất thành một câu hỏi tra cứu "
        "đầy đủ, tự đứng được, cùng ngôn ngữ người dùng:\n"
        "- thay đại từ và từ chỉ trỏ bằng đối tượng cụ thể trong lịch sử; bổ sung chủ thể còn thiếu từ câu hỏi trước;\n"
        "- nếu người dùng nhắc tới một câu hỏi trước đó (ví dụ câu đầu tiên), thay bằng nội dung câu đó;\n"
        "- nếu là câu phản bác/đính chính, viết thành câu hỏi kiểm tra lại thông tin đang tranh luận;\n"
        "- bỏ qua các lượt chen ngang không liên quan; nếu chuyển sang chủ đề mới thì KHÔNG mang ngữ cảnh cũ;\n"
        "- câu nối tiếp không nêu đối tượng riêng thì kế thừa đối tượng và phạm vi của lượt liên quan gần nhất trong "
        "TRẠNG THÁI HỘI THOẠI; câu có đối tượng mới thì KHÔNG kế thừa phạm vi cũ; tham chiếu tương đối (trước, sau, "
        "trên, dưới) giải theo thứ tự các mục trong lịch sử;\n"
        "- giữ nguyên mã, số hiệu, tên riêng, thuật ngữ; khôi phục dấu tiếng Việt và sửa lỗi gõ rõ ràng; không trả lời câu hỏi.\n"
        "focus: danh sách đối tượng chính được hỏi, giữ nguyên chữ người dùng (thuật ngữ, tên, mã), không gồm từ chỉ phạm vi.\n"
        "scope: danh sách điều kiện giới hạn phạm vi người dùng nêu (mục, chương, cấp, lớp, thời gian, loại), rỗng nếu không có.\n"
        "wants_location: true nếu hỏi vị trí (ở đâu, mục/chương/cấp nào, mã nào).\n"
        "format: 'table' | 'checklist' | 'list' nếu người dùng yêu cầu dạng trình bày đó, ngược lại để rỗng.\n"
        "compare: true nếu so sánh hoặc hỏi sự thay đổi qua nhiều mục/cấp.\n"
        "aggregate: phép tính trên số liệu mà câu hỏi cần: 'max' (cao nhất/nhiều nhất/lớn nhất), 'min' (thấp nhất/ít nhất/"
        "nhỏ nhất), 'diff' (chênh lệch), 'sum' (tổng cộng), 'avg' (trung bình), 'sort' (xếp hạng), 'count' (đếm số mục); "
        "rỗng nếu không cần tính. Câu nối tiếp chỉ đổi phép tính (ví dụ hỏi chiều ngược lại) thì giữ nguyên đối tượng, "
        "phạm vi và chỉ số của lượt trước, chỉ đổi aggregate.\n"
        "count_unit: khi hỏi số lượng hoặc số liệu, ghi đúng đơn vị/chỉ số được hỏi theo chữ người dùng; rỗng nếu không.\n"
        "new_topic: true nếu tin nhắn mới không phụ thuộc lịch sử. challenge: true nếu người dùng phản bác hoặc chỉ ra thiếu sót.\n"
        "about_document: true nếu hỏi về chính văn bản (tên, số hiệu, ngày, cơ quan ban hành, hiệu lực, phạm vi áp dụng, cấu trúc, quy ước đánh mã, ký hiệu).\n"
        "wants_list: true nếu câu trả lời là một danh sách nhiều mục: hỏi 'những/các … nào', 'gồm những gì', 'có những gì', liệt kê, tổng quan, so sánh hoặc tổng hợp nhiều mục.\n"
        "wants_brief: true nếu người dùng yêu cầu trả lời ngắn (một câu, chỉ kể tên, số dòng giới hạn).\n"
        "phone: số điện thoại người dùng cung cấp trong tin nhắn mới nhất, nếu có."
    )


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    s = text.strip()
    if "```" in s:
        parts = s.split("```")
        s = next((p[4:] if p.startswith("json") else p for p in parts if "{" in p), s)
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(s[start:end + 1])
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes", "có")


def _choice(value: Any, allowed: Sequence[str]) -> str:
    v = str(value or "").strip().lower()
    return v if v in allowed else ""


def _as_terms(value: Any, limit: int = 4) -> List[str]:
    if isinstance(value, str):
        value = [v for v in re.split(r"[;,]", value)]
    if not isinstance(value, list):
        return []
    terms = [str(v).strip() for v in value if str(v).strip()]
    return list(dict.fromkeys(t for t in terms if len(t) <= 80))[:limit]


def _policy_prompt(policy: str) -> str:
    return (
        f"{ANALYZER_MARKER} Bạn kiểm tra chính sách cho trợ lý tra cứu tài liệu nội bộ. Các nhóm yêu cầu bị từ chối: {policy}.\n"
        'Trả về DUY NHẤT JSON {"in_policy": true|false, "category": "<tên nhóm>"}: in_policy=true khi tin nhắn thuộc một '
        "trong các nhóm trên, category là tên nhóm đó."
    )


class QueryAnalyzer:
    def __init__(
        self,
        out_of_scope_policy: str = "",
        timeout: float = 4.0,
        history_messages: int = 6,
        enabled: bool = True,
    ) -> None:
        self.out_of_scope_policy = out_of_scope_policy or "không có"
        self.timeout = timeout
        self.history_messages = history_messages
        self.enabled = enabled

    @staticmethod
    def _previous_user_turns(history: Sequence[Dict[str, Any]]) -> List[str]:
        return [
            (m.get("standalone") or m.get("content") or "").strip()
            for m in history or []
            if m.get("role") == "user" and (m.get("content") or "").strip()
        ]

    def fallback(self, query: str, history: Sequence[Dict[str, Any]], latency_ms: float = 0.0) -> QueryAnalysis:
        """Concatenate the previous user turn to short follow-ups; long messages stand alone."""
        q = (query or "").strip()
        previous = self._previous_user_turns(history)
        standalone = q
        if previous and len(q.split()) <= 8:
            standalone = f"{previous[-1].rstrip(' ?.!')} — {q}"
        phone = PHONE_RE.search(q)
        intent = Intent.CONTACT_INFO if phone and len(q.split()) <= 12 else Intent.DOCUMENT_QUESTION
        return QueryAnalysis(
            intent=intent,
            standalone_query=standalone,
            original_query=q,
            new_topic=not previous,
            phone=re.sub(r"[\s.\-]", "", phone.group(1)) if phone else "",
            source="fallback",
            latency_ms=latency_ms,
        )

    @staticmethod
    def _clip(text: str, head: int = HISTORY_HEAD_CHARS, tail: int = HISTORY_TAIL_CHARS) -> str:
        """Head and tail of a message: replies often end with what was asked of the user (a phone number…)."""
        return text if len(text) <= head + tail + 1 else f"{text[:head]} … {text[-tail:]}"

    @staticmethod
    def _state_line(m: Dict[str, Any]) -> str:
        parts = []
        if m.get("focus"):
            parts.append("đối tượng=" + ", ".join(m["focus"]))
        if m.get("scope"):
            parts.append("phạm vi=" + ", ".join(m["scope"]))
        if m.get("identifiers"):
            parts.append("mã đã nêu=" + ", ".join(m["identifiers"][:12]))
        if m.get("intent"):
            parts.append(f"loại={m['intent']}")
        if m.get("asked_contact"):
            parts.append("trợ lý đã mời để lại số điện thoại")
        return "; ".join(parts)

    def build_messages(self, query: str, history: Sequence[Dict[str, Any]]) -> List[Dict[str, str]]:
        transcript, state = [], []
        for m in list(history or [])[-self.history_messages:]:
            role = "Người dùng" if m.get("role") == "user" else "Trợ lý"
            content = (m.get("content") or "").strip().replace("\n", " ")
            transcript.append(f"{role}: {self._clip(content)}")
            line = self._state_line(m)
            if line:
                state.append(f"- {role}: {line}")
        history_block = "\n".join(transcript) if transcript else "(không có)"
        state_block = "\n".join(state) if state else "(không có)"
        user = (
            f"LỊCH SỬ HỘI THOẠI:\n{history_block}\n\nTRẠNG THÁI HỘI THOẠI:\n{state_block}\n\n"
            f"TIN NHẮN MỚI NHẤT: {query.strip()}\n\nJSON:"
        )
        return [
            {"role": "system", "content": _system_prompt(self.out_of_scope_policy)},
            {"role": "user", "content": user},
        ]

    def parse(self, raw_text: str, query: str, history: Sequence[Dict[str, Any]], latency_ms: float) -> QueryAnalysis:
        data = _extract_json(raw_text)
        if data is None:
            return self.fallback(query, history, latency_ms)
        try:
            intent = Intent(str(data.get("intent", "document_question")).strip().lower())
        except ValueError:
            intent = Intent.DOCUMENT_QUESTION
        standalone = str(data.get("standalone_query") or "").strip() or query.strip()
        if not set(extract_identifiers(query)) <= set(extract_identifiers(standalone)):
            # The rewrite dropped a code/number the user typed: it changed the question, keep the original.
            standalone = self.fallback(query, history, latency_ms).standalone_query
        phone = str(data.get("phone") or "").strip()
        if phone and not PHONE_RE.search(phone):
            phone = ""
        typed_phone = PHONE_RE.search(query)
        if intent == Intent.CONTACT_INFO and not phone:
            phone = re.sub(r"[\s.\-]", "", typed_phone.group(1)) if typed_phone else ""
        if typed_phone and len(query.split()) <= 12 and intent in (Intent.SUPPORT_REQUEST, Intent.UNCLEAR):
            # A short message carrying a phone number is the user leaving their contact, whatever the label.
            intent, phone = Intent.CONTACT_INFO, re.sub(r"[\s.\-]", "", typed_phone.group(1))
        return QueryAnalysis(
            intent=intent,
            standalone_query=standalone,
            original_query=query.strip(),
            new_topic=_as_bool(data.get("new_topic", False)),
            challenge=_as_bool(data.get("challenge", False)),
            about_document=_as_bool(data.get("about_document", False)),
            wants_list=_as_bool(data.get("wants_list", False)),
            wants_brief=_as_bool(data.get("wants_brief", False)),
            out_of_scope_category=str(data.get("out_of_scope_category") or "").strip(),
            phone=re.sub(r"[\s.\-]", "", phone),
            focus_terms=_as_terms(data.get("focus")),
            scope_terms=_as_terms(data.get("scope")),
            wants_location=_as_bool(data.get("wants_location", False)),
            answer_format=str(data.get("format") or "").strip().lower() if str(data.get("format") or "").strip().lower() in ANSWER_FORMATS else "",
            compare=_as_bool(data.get("compare", False)),
            aggregate=_choice(data.get("aggregate"), AGGREGATES),
            count_unit=str(data.get("count_unit") or "").strip()[:60],
            source="llm",
            latency_ms=latency_ms,
            raw=data,
        )

    async def analyze(
        self,
        query: str,
        history: Sequence[Dict[str, Any]],
        llm_port: Any,
        model: str,
        authorization: Optional[str] = None,
    ) -> QueryAnalysis:
        t0 = time.perf_counter()
        if not self.enabled or llm_port is None:
            return self.fallback(query, history)
        # Waiting for a free runtime slot under load is not the model being slow: that wait is allowed on
        # top of the analysis budget, so a busy hour does not silently degrade routing to the fallback.
        allowance = getattr(llm_port, "queue_allowance", None)
        timeout = self.timeout + (float(allowance()) if callable(allowance) else 0.0)
        try:
            coro = llm_port.generate(
                messages=self.build_messages(query, history),
                model=model,
                temperature=0.0,
                max_tokens=400,
                authorization=authorization,
            )
            content, _, _ = await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Query analysis timed out after %.1fs; using fallback", timeout)
            return self.fallback(query, history, (time.perf_counter() - t0) * 1000)
        except Exception as exc:  # noqa: BLE001 - the analyzer must never break the chat
            logger.warning("Query analysis failed (%s); using fallback", exc)
            return self.fallback(query, history, (time.perf_counter() - t0) * 1000)
        return self.parse(content, query, history, (time.perf_counter() - t0) * 1000)

    async def policy_category(
        self, query: str, llm_port: Any, model: str, authorization: Optional[str] = None
    ) -> str:
        """Category of the tenant's out-of-scope policy the message falls into ('' if none or unknown)."""
        if not self.enabled or llm_port is None or self.out_of_scope_policy in ("", "không có"):
            return ""
        try:
            content, _, _ = await asyncio.wait_for(
                llm_port.generate(
                    messages=[
                        {"role": "system", "content": _policy_prompt(self.out_of_scope_policy)},
                        {"role": "user", "content": f"TIN NHẮN: {query.strip()}\n\nJSON:"},
                    ],
                    model=model, temperature=0.0, max_tokens=60, authorization=authorization,
                ),
                timeout=self.timeout,
            )
        except Exception as exc:  # noqa: BLE001 - best effort
            logger.debug("Policy check failed: %s", exc)
            return ""
        data = _extract_json(content) or {}
        return str(data.get("category") or "").strip() if _as_bool(data.get("in_policy", False)) else ""
