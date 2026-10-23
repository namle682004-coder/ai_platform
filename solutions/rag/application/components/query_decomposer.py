"""
Query Decomposition & Multi-Hop Reasoning Engine for AIP Enterprise RAG (Slide 94–103).

Decomposes complex, comparative, and multi-step questions into ordered sub-queries
with dependency linkage, bridging context across sequential retrieval hops.
Strictly domain-agnostic and format-agnostic with ZERO hardcoded legal keywords.
"""

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from ...domain.ports import LLMPort

logger = logging.getLogger("aip-rag.query_decomposer")


class DecomposedQuery(BaseModel):
    """Structured representation of a decomposed query."""
    is_multi_hop: bool = False
    sub_queries: List[str] = Field(default_factory=list)
    strategy: str = "SINGLE_HOP"  # COMPARATIVE | SEQUENTIAL | BRIDGING | LLM_DECOMPOSED | SINGLE_HOP
    latency_ms: float = 0.0


class QueryDecomposer:
    """
    Multi-Hop Query Decomposer for Enterprise RAG (Slide 94–103).

    Tier 1: Ultra-fast heuristic decomposition (< 1ms, 0 tokens)
            - Comparative patterns ("so sánh A và B", "sự khác biệt giữa A và B", "A vs B")
            - Sequential conjunctions ("A và đồng thời B", "A đồng thời cho biết B", "A sau đó B")
            - Dual question clauses ("Ai là ... và ... ở đâu")
    Tier 2: Speculative async LLM decomposition fallback (timeout 0.8s)
    """

    def __init__(self) -> None:
        # Heuristic Regex Pattern for Comparative Queries with explicit Aspect:
        # "So sánh [yêu cầu kinh nghiệm] giữa [Hiệu trưởng] và [Trưởng phòng]"
        self._comparative_aspect_pattern = re.compile(
            r"^(?:so\s+sánh|(?:sự\s+|điểm\s+)?khác\s+(?:biệt|nhau))\s+(?:về\s+)?(.+?)\s+giữa\s+(.+?)\s+(?:và|với)\s+(.+?)(?:\s*\?|\.|\s*$)",
            re.IGNORECASE,
        )

        # Heuristic Regex Patterns for Comparative Queries
        self._comparative_patterns = [
            # So sánh [giữa] X và/với Y
            re.compile(r"^so\s+sánh\s+(?:giữa\s+)?(.+?)\s+(?:với|và)\s+(.+?)(?:\s*\?|\.|\s*$)", re.IGNORECASE),
            # [sự/điểm] khác biệt/nhau giữa X và Y
            re.compile(r"^(?:sự\s+|điểm\s+)?khác\s+(?:biệt|nhau)\s+giữa\s+(.+?)\s+và\s+(.+?)(?:\s*\?|\.|\s*$)", re.IGNORECASE),
            # điểm giống và khác giữa X và Y
            re.compile(r"^(?:điểm\s+)?giống\s+và\s+khác\s+(?:nhau\s+)?giữa\s+(.+?)\s+và\s+(.+?)(?:\s*\?|\.|\s*$)", re.IGNORECASE),
            # English: compare X and/with/to Y
            re.compile(r"^compare\s+(.+?)\s+(?:and|with|to)\s+(.+?)(?:\s*\?|\.|\s*$)", re.IGNORECASE),
            # English: difference between X and Y
            re.compile(r"^(?:the\s+)?difference\s+between\s+(.+?)\s+and\s+(.+?)(?:\s*\?|\.|\s*$)", re.IGNORECASE),
            # X vs/versus Y
            re.compile(r"^(.+?)\s+(?:vs\.?|versus)\s+(.+?)(?:\s*\?|\.|\s*$)", re.IGNORECASE),
        ]

        # Heuristic Regex Patterns for Sequential / Conjunction Queries
        self._sequential_patterns = [
            # X và đồng thời Y
            re.compile(r"^(.+?)\s+và\s+đồng\s+thời\s+(.+?)(?:\s*\?|\.|\s*$)", re.IGNORECASE),
            # X đồng thời cho biết Y
            re.compile(r"^(.+?)\s+đồng\s+thời\s+cho\s+biết\s+(.+?)(?:\s*\?|\.|\s*$)", re.IGNORECASE),
            # X và sau đó Y / X sau đó Y
            re.compile(r"^(.+?)\s+(?:và\s+sau\s+đó|sau\s+đó)\s+(.+?)(?:\s*\?|\.|\s*$)", re.IGNORECASE),
            # Dual question clauses: Clause 1 (với từ để hỏi) và Clause 2 (với từ để hỏi)
            re.compile(
                r"^(.+?\b(?:ai\s+là|ở\s+đâu|khi\s+nào|thế\s+nào|bao\s+nhiêu|như\s+thế\s+nào)\b.+?)\s+và\s+((?:ai\s+là|ở\s+đâu|khi\s+nào|thế\s+nào|bao\s+nhiêu|như\s+thế\s+nào|thời\s+hạn|quy\s+trình).+?)(?:\s*\?|\.|\s*$)",
                re.IGNORECASE,
            ),
        ]

        # General multi-hop detection keywords
        self._multi_hop_indicator_regex = re.compile(
            r"\b(?:so\s+sánh|khác\s+(?:biệt|nhau)\s+giữa|giống\s+và\s+khác|compare|difference\s+between|versus|vs\.?|và\s+đồng\s+thời|đồng\s+thời\s+cho\s+biết|và\s+sau\s+đó)\b",
            re.IGNORECASE,
        )

        # Anaphoric pronouns indicating bridging dependency between Hop 1 and Hop 2
        self._anaphora_regex = re.compile(
            r"\b(người\s+đó|nhân\s+sự\s+này|ông\s+ấy|bà\s+ấy|đơn\s+vị\s+này|phòng\s+ban\s+này|công\s+ty\s+này|dự\s+án\s+này|hệ\s+thống\s+này|tài\s+liệu\s+này)\b",
            re.IGNORECASE,
        )

    def should_decompose(self, query: str) -> bool:
        """
        Determines whether a query requires multi-hop decomposition (Slide 94-96).
        Fast check (< 0.2ms) without LLM calls.
        """
        q_clean = query.strip()
        words = q_clean.split()
        if len(words) < 4:
            return False

        if self._multi_hop_indicator_regex.search(q_clean):
            return True

        for p in self._sequential_patterns:
            if p.search(q_clean):
                return True

        return False

    def decompose_heuristic(self, query: str) -> Optional[DecomposedQuery]:
        """
        Tier 1: Heuristic decomposition (< 1ms).
        Returns DecomposedQuery if high-confidence rule matched, else None.
        """
        start_t = time.time()
        q_clean = query.strip()

        # 1. Check comparative pattern with explicit aspect ("So sánh [kinh nghiệm] giữa [A] và [B]")
        aspect_match = self._comparative_aspect_pattern.search(q_clean)
        if aspect_match:
            aspect = aspect_match.group(1).strip()
            item1 = aspect_match.group(2).strip()
            item2 = aspect_match.group(3).strip()
            if len(item1.split()) >= 1 and len(item2.split()) >= 1:
                sub_q1 = f"{aspect} của {item1}"
                sub_q2 = f"{aspect} của {item2}"
                latency = (time.time() - start_t) * 1000
                return DecomposedQuery(
                    is_multi_hop=True,
                    sub_queries=[sub_q1, sub_q2],
                    strategy="COMPARATIVE",
                    latency_ms=round(latency, 2),
                )

        # 2. Check general comparative patterns ("So sánh A và B")
        for pattern in self._comparative_patterns:
            match = pattern.search(q_clean)
            if match:
                item1 = match.group(1).strip()
                item2 = match.group(2).strip()
                if len(item1.split()) >= 1 and len(item2.split()) >= 1:
                    sub_q1 = f"Thông tin và đặc điểm về {item1}"
                    sub_q2 = f"Thông tin và đặc điểm về {item2}"
                    latency = (time.time() - start_t) * 1000
                    return DecomposedQuery(
                        is_multi_hop=True,
                        sub_queries=[sub_q1, sub_q2],
                        strategy="COMPARATIVE",
                        latency_ms=round(latency, 2),
                    )

        # Check sequential / conjunction patterns
        for pattern in self._sequential_patterns:
            match = pattern.search(q_clean)
            if match:
                part1 = match.group(1).strip()
                part2 = match.group(2).strip()
                if len(part1.split()) >= 3 and len(part2.split()) >= 3:
                    latency = (time.time() - start_t) * 1000
                    return DecomposedQuery(
                        is_multi_hop=True,
                        sub_queries=[part1, part2],
                        strategy="SEQUENTIAL",
                        latency_ms=round(latency, 2),
                    )

        return None

    async def decompose_speculative(
        self,
        query: str,
        llm_port: Optional[LLMPort] = None,
        model: str = "chat-general-standard",
        timeout: float = 0.8,
    ) -> DecomposedQuery:
        """
        Tier 2: Speculative Async LLM Decomposition fallback with strict timeout guardrail.
        """
        start_t = time.time()
        if not llm_port:
            latency = (time.time() - start_t) * 1000
            return DecomposedQuery(
                is_multi_hop=False,
                sub_queries=[query.strip()],
                strategy="SINGLE_HOP",
                latency_ms=round(latency, 2),
            )

        system_prompt = (
            "Bạn là bộ phân rã câu hỏi (Query Decomposer) của hệ thống RAG doanh nghiệp.\n"
            "Nhiệm vụ: Phân tích câu hỏi phức hợp của người dùng và tách thành tối đa 2 câu hỏi con (Sub-queries) độc lập hoặc nối tiếp để tìm kiếm tài liệu.\n"
            "Nếu câu hỏi đơn giản không cần tách, trả về chính câu hỏi đó.\n"
            "ĐỊNH DẠNG BẮT BUỘC (chỉ trả về JSON thuần túy, không kèm giải thích):\n"
            '{"is_multi_hop": true, "sub_queries": ["câu 1", "câu 2"]}\n'
            'hoặc\n'
            '{"is_multi_hop": false, "sub_queries": ["câu hỏi gốc"]}'
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Câu hỏi: {query.strip()}"},
        ]

        try:
            raw_response, _, _ = await asyncio.wait_for(
                llm_port.generate(
                    messages=messages,
                    model=model,
                    temperature=0.1,
                    max_tokens=150,
                ),
                timeout=timeout,
            )

            # Extract JSON block
            raw_clean = raw_response.strip()
            json_match = re.search(r"\{.*?\}", raw_clean, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(0))
                is_multi = bool(parsed.get("is_multi_hop", False))
                subs = parsed.get("sub_queries", [])
                if is_multi and isinstance(subs, list) and len(subs) >= 2:
                    valid_subs = [s.strip() for s in subs[:2] if isinstance(s, str) and s.strip()]
                    if len(valid_subs) >= 2:
                        latency = (time.time() - start_t) * 1000
                        return DecomposedQuery(
                            is_multi_hop=True,
                            sub_queries=valid_subs,
                            strategy="LLM_DECOMPOSED",
                            latency_ms=round(latency, 2),
                        )

        except asyncio.TimeoutError:
            logger.warning(f"Speculative LLM query decomposition timed out after {timeout}s, falling back to single-hop.")
        except Exception as e:
            logger.warning(f"Speculative LLM query decomposition failed: {e}")

        latency = (time.time() - start_t) * 1000
        return DecomposedQuery(
            is_multi_hop=False,
            sub_queries=[query.strip()],
            strategy="SINGLE_HOP",
            latency_ms=round(latency, 2),
        )

    async def decompose(
        self,
        query: str,
        llm_port: Optional[LLMPort] = None,
        model: str = "chat-general-standard",
        timeout: float = 0.8,
    ) -> DecomposedQuery:
        """
        Unified query decomposition entrypoint:
        1. Quick check if query requires multi-hop decomposition.
        2. Fast-track heuristic decomposition (< 1ms).
        3. Speculative LLM decomposition fallback when heuristics do not match.
        """
        words = query.strip().split()
        if len(words) < 4:
            return DecomposedQuery(
                is_multi_hop=False,
                sub_queries=[query.strip()],
                strategy="SINGLE_HOP",
                latency_ms=0.0,
            )

        heuristic_res = self.decompose_heuristic(query)
        if heuristic_res and heuristic_res.is_multi_hop:
            return heuristic_res

        if llm_port:
            return await self.decompose_speculative(
                query=query,
                llm_port=llm_port,
                model=model,
                timeout=timeout,
            )

        return DecomposedQuery(
            is_multi_hop=False,
            sub_queries=[query.strip()],
            strategy="SINGLE_HOP",
            latency_ms=0.0,
        )

    def bridge_query(self, sub_query: str, hop1_candidates: List[Dict[str, Any]]) -> str:
        """
        Iterative Bridging Step (Slide 98-101):
        If sub_query contains anaphoric pronouns ("người đó", "dự án này", "công ty này"),
        substitutes or augments them with factual entities/titles extracted from Hop 1 chunks.
        """
        if not hop1_candidates:
            return sub_query

        top_cand = hop1_candidates[0]
        payload = top_cand.get("payload", {})
        title = payload.get("title", top_cand.get("title", "")).strip()

        # Check for explicit anaphora
        match = self._anaphora_regex.search(sub_query)
        if match and title:
            bridged = self._anaphora_regex.sub(f"{match.group(1)} (liên quan đến: {title})", sub_query)
            return bridged

        return sub_query


# Global singleton instance
query_decomposer = QueryDecomposer()
