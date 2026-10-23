"""
Level 4 Production AI Intent & Adaptive Routing Engine.
Uses fast neural LLM inference with Few-Shot Grounding and Deterministic Guardrails
to classify intent, detect domain, estimate query complexity, and determine adaptive retrieval parameters.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from ...domain.entities import QueryIntent

logger = logging.getLogger("aip-rag.intent_classifier")


@dataclass
class RoutingDecision:
    intent: QueryIntent
    domain: Optional[str] = "GENERAL"
    complexity: str = "FACTUAL"
    adaptive_top_k: int = 4
    confidence: float = 0.95
    raw_response: Dict[str, Any] = field(default_factory=dict)


INTENT_SYSTEM_PROMPT_L4 = (
    "Bạn là bộ phân loại ý định (Intent Router) cho hệ thống RAG doanh nghiệp.\n"
    "Nhiệm vụ: Phân loại câu hỏi của người dùng và trả về đúng 1 JSON block duy nhất với cấu trúc:\n"
    '{"intent": "FACTUAL_QA" | "HOWTO_TROUBLESHOOTING" | "COMPARATIVE" | "MULTI_TURN_FOLLOWUP" | "OUT_OF_DOMAIN" | "CHITCHAT", '
    '"domain": "LEGAL" | "HR" | "FINANCE" | "TECH" | "GENERAL", '
    '"complexity": "FACTUAL" | "ANALYTICAL", '
    '"adaptive_top_k": 3 | 4 | 6}\n\n'
    "QUY TẮC PHÂN LOẠI (FEAT-ENG-02 — 5 nhóm + Chitchat):\n"
    "1. FACTUAL_QA: Hỏi thông số, số hiệu văn bản, định nghĩa, sự kiện, con người, chức danh, "
    "số liệu, chính sách, quy định. Có từ hỏi: nào, gì, ai, đâu, khi nào, bao nhiêu.\n"
    "2. HOWTO_TROUBLESHOOTING: Hỏi cách làm, hướng dẫn cài đặt, quy trình thao tác, xử lý lỗi kỹ thuật. "
    "Có từ khóa: hướng dẫn, cách, làm sao, thế nào, xử lý, sửa, cài đặt, thiết lập, bước.\n"
    "3. COMPARATIVE: So sánh giữa các phương án, quy định, phiên bản. "
    "Có từ khóa: so sánh, khác nhau, giống nhau, hơn, thua, nên chọn, hay là.\n"
    "4. MULTI_TURN_FOLLOWUP: Câu hỏi nối tiếp trong hội thoại, chứa đại từ tham chiếu lượt trước "
    "(nó, cái đó, bước trên, thế còn, vậy thì, tiếp theo).\n"
    "5. OUT_OF_DOMAIN: Câu hỏi hoàn toàn ngoài phạm vi nghiệp vụ (lương, bí mật kinh doanh, "
    "thông tin cá nhân, chủ đề giải trí, chính trị, tôn giáo).\n"
    "6. CHITCHAT: CHỈ khi hoàn toàn chào hỏi, cảm ơn, trò chuyện phiếm "
    "(ví dụ: 'chào bạn', 'hello', 'cảm ơn nhé').\n\n"
    "Chỉ trả về JSON duy nhất, không giải thích."
)

# Standard domain-agnostic conversational greetings
CHITCHAT_GREETINGS = {
    "chào", "chào bạn", "hello", "hi", "cảm ơn", "cảm ơn bạn", "thank you", "thanks", "tạm biệt", "bye", "goodbye"
}


class AiIntentClassifierService:
    """Production AI Intent Classifier & Adaptive Retrieval Router."""

    @staticmethod
    def is_pure_chitchat_greeting(query: str) -> bool:
        """Fast-track check for pure trivial greetings without informational intent."""
        lower_q = query.strip().lower()
        words = lower_q.split()
        if len(words) <= 3 and any(lower_q == g or lower_q.startswith(g + " ") for g in CHITCHAT_GREETINGS):
            return True
        return False

    AMBIGUOUS_SYMPTOMS = [
        "lỗi không xuất được", "không xuất được", "lỗi không ký được", "không ký được",
        "bị lỗi", "không mở được", "bị treo", "không kết nối được", "lỗi kết nối",
        "không in được", "bị mất", "không hiển thị", "không đăng nhập được", "bị đơ",
        "không tải được", "lỗi phần mềm", "phần mềm bị lỗi", "ký số không lên"
    ]
    CONCRETE_ENTITIES = [
        "hóa đơn", "hoá đơn", "hddt", "hđđt", "báo cáo", "bc26", "tờ khai",
        "usb", "token", "smartca", "thuế", "mã cqt", "mã tra cứu", "plugin",
        "chrome", "firefox", "bảng kê", "chi nhánh", "mẫu số", "ký hiệu", "mst"
    ]

    @classmethod
    def is_ambiguous_symptom(cls, query: str) -> bool:
        """
        Detects ambiguous error symptoms lacking concrete business entities (FR-RET-05 / BRD Pain Point 5).
        Triggers Interactive Clarification instead of premature OOD refusal or escalation.
        """
        lower_q = query.strip().lower()
        has_symptom = any(s in lower_q for s in cls.AMBIGUOUS_SYMPTOMS)
        if not has_symptom:
            return False
        has_concrete_entity = any(e in lower_q for e in cls.CONCRETE_ENTITIES)
        return not has_concrete_entity

    async def classify_advanced(
        self,
        query: str,
        llm_port: Optional[Any] = None,
        model: str = "chat-general-standard",
    ) -> RoutingDecision:
        """Adaptive Routing extracting user intent, domain category, and adaptive top_k."""
        lower_q = query.strip().lower()

        # 1. Fast-Track for short, trivial greetings (0ms - avoids unnecessary LLM calls)
        if self.is_pure_chitchat_greeting(query):
            return RoutingDecision(intent=QueryIntent.CHITCHAT, adaptive_top_k=1)

        # 2. Fast-Track for ambiguous symptom queries (FR-RET-05: Clarification Engine)
        if self.is_ambiguous_symptom(query):
            logger.info("Query '%s' classified as AMBIGUOUS_SYMPTOM. Routing to Clarification Engine.", query)
            return RoutingDecision(
                intent=QueryIntent.AMBIGUOUS_SYMPTOM,
                domain="TECH",
                complexity="SYMPTOM",
                adaptive_top_k=2,
            )

        # Fast-track for How-to / Troubleshooting queries (FEAT-ENG-02 category 2)
        words = lower_q.split()
        howto_match = re.search(
            r"\b(?:hướng dẫn|cách|làm sao|thế nào|như thế nào|xử lý|sửa|cài đặt|thiết lập|cấu hình|khắc phục|bước)\b",
            lower_q,
        )
        if howto_match and len(words) >= 4:
            return RoutingDecision(intent=QueryIntent.HOWTO_TROUBLESHOOTING, domain="TECH", complexity="ANALYTICAL", adaptive_top_k=6)

        # Fast-track for Comparative queries (FEAT-ENG-02 category 3)
        comparative_match = re.search(
            r"\b(?:so sánh|khác nhau|giống nhau|khác gì|hơn|nên chọn|hay là|khác biệt)\b",
            lower_q,
        )
        if comparative_match and len(words) >= 5:
            return RoutingDecision(intent=QueryIntent.COMPARATIVE, domain="GENERAL", complexity="ANALYTICAL", adaptive_top_k=6)

        # Fast-track for clear Factual Q&A queries (genuine 5W1H interrogatives)
        interrogative_match = re.search(
            r"\b(?:khi nào|bao nhiêu|tại sao|vì sao|là gì|cho hỏi|ở đâu|được không|có được không|phải không|ai|đâu|liệu)\b",
            lower_q,
        )
        is_clear_question = (
            ("?" in query and len(words) >= 3)
            or (bool(interrogative_match) and len(words) >= 5)
        )
        if is_clear_question:
            return RoutingDecision(intent=QueryIntent.QA, domain="GENERAL", complexity="FACTUAL", adaptive_top_k=4)

        # 2. If LLM port is available, execute genuine neural intent classification & adaptive routing
        if llm_port:
            try:
                raw_content, _, _ = await llm_port.generate(
                    messages=[
                        {"role": "system", "content": INTENT_SYSTEM_PROMPT_L4},
                        {"role": "user", "content": query.strip()},
                    ],
                    model=model,
                    temperature=0.0,
                    max_tokens=60,
                )
                if "```" in raw_content:
                    clean_block = raw_content.split("```")[1]
                    if clean_block.startswith("json"):
                        clean_block = clean_block[4:]
                    raw_content = clean_block.strip()

                parsed = json.loads(raw_content)
                intent_str = str(parsed.get("intent", "FACTUAL_QA")).upper()
                _INTENT_MAP = {
                    "FACTUAL_QA": QueryIntent.QA,
                    "KNOWLEDGE_QUERY": QueryIntent.QA,
                    "HOWTO_TROUBLESHOOTING": QueryIntent.HOWTO_TROUBLESHOOTING,
                    "COMPARATIVE": QueryIntent.COMPARATIVE,
                    "MULTI_TURN_FOLLOWUP": QueryIntent.MULTI_TURN_FOLLOWUP,
                    "OUT_OF_DOMAIN": QueryIntent.OUT_OF_DOMAIN,
                    "CHITCHAT": QueryIntent.CHITCHAT,
                }
                intent = _INTENT_MAP.get(intent_str, QueryIntent.QA)

                domain = parsed.get("domain", "GENERAL")
                complexity = parsed.get("complexity", "FACTUAL")
                adaptive_top_k = int(parsed.get("adaptive_top_k", 4))

                return RoutingDecision(
                    intent=intent,
                    domain=domain,
                    complexity=complexity,
                    adaptive_top_k=adaptive_top_k,
                    raw_response=parsed,
                )
            except Exception as exc:
                logger.warning("LLM intent routing encountered error (%s); applying fallback", exc)

        # 3. Fallback when LLM is offline or query classification fails
        return RoutingDecision(intent=QueryIntent.QA, domain="GENERAL", complexity="FACTUAL", adaptive_top_k=4)


intent_classifier = AiIntentClassifierService()

