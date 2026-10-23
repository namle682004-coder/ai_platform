"""
Enterprise Conversational Query Reformulator for AIP RAG (Slide 134–137, 139).
Two-Tier Pre-Retrieval Latency Optimization Engine:
- Tier 1: Deterministic Heuristic Fast-Track (< 1ms, 0 Token Cost)
  * Single-turn bypass (< 0.01ms)
  * Standalone query & domain keyword detection (< 0.05ms)
  * Deterministic Coreference & Ellipsis Stitching (< 0.2ms)
- Tier 2: Async Speculative LLM Fallback (when query is ambiguous / low heuristic confidence)
  * Strict speculative timeout guardrail (default 800ms) with automatic heuristic fallback
  * Low-token, low-latency generation (TTFT < 1.2s guaranteed)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import re
import time
import unicodedata
from typing import Any, Dict, List, Optional, Set, Tuple

from .vietnamese_resources import (
    ENTERPRISE_ACRONYMS,
    ACRONYM_CASING_MAP,
    CHAT_SHORTHAND_MAP,
    DIACRITICS_PHRASE_MAP,
    DIACRITICS_WORD_MAP,
    VIETNAMESE_LEVEL_TONE_WORDS,
    strip_accents,
)

logger = logging.getLogger("aip-rag.query-rewriter")

# Vietnamese vowel clusters for diacritic-tolerant regex pattern generation
VOWEL_ACCENTS: Dict[str, str] = {
    "a": "[aàáảãạăằắẳẵặâầấẩẫậ]",
    "e": "[eèéẻẽẹêềếểễệ]",
    "i": "[iìíỉĩị]",
    "o": "[oòóỏõọôồốổỗộơờớởỡợ]",
    "u": "[uùúủũụưừứửữự]",
    "y": "[yỳýỷỹỵ]",
    "d": "[dđ]",
}


def make_diacritic_tolerant_regex(phrase: str) -> re.Pattern:
    """
    Constructs a regex pattern that matches the phrase regardless of whether
    individual letters already have accents or not (e.g. 'huong dan lam' will match
    'huong dan lam', 'hướng dẫn lam', 'hướng dẫn làm').
    """
    pattern_parts = []
    for char in phrase:
        low = char.lower()
        if low in VOWEL_ACCENTS:
            pattern_parts.append(VOWEL_ACCENTS[low])
        elif char == " ":
            pattern_parts.append(r"\s+")
        else:
            pattern_parts.append(re.escape(char))
    return re.compile(r"\b" + "".join(pattern_parts) + r"\b", re.IGNORECASE)


@dataclass
class RewrittenQuery:
    """Structured decision output of the Two-Tier Pre-Retrieval Engine."""

    text: str
    original_query: str
    tier: str  # "TIER_1_HEURISTIC" | "TIER_2_SPECULATIVE_LLM" | "TIER_2_TIMEOUT_FALLBACK" | "TIER_2_ERROR_FALLBACK"
    reason: str  # Specific rule or trigger identifier
    latency_ms: float
    is_reformulated: bool
    is_standalone_shield_activated: bool = False
    speculative_query: Optional[str] = None
    expanded_query: Optional[str] = None
    unaccented_variant: Optional[str] = None
    sparse_query: Optional[str] = None


class RagQueryRewriter:
    """
    Two-Tier Pre-Retrieval Optimization Engine for Enterprise RAG.
    Compliant with TS. Lương Văn Thiện curriculum (Slide 134–137, 139) and RET-RAG-01.
    """

    # Domain-agnostic conversational pronouns & anaphora markers
    PRONOUNS = {
        "nó", "họ", "người đó", "ông đó", "bà đó", "anh đó", "chị đó",
        "chế độ đó", "chính sách đó", "quy định đó", "tài liệu đó", "hợp đồng đó", "văn bản đó",
        "trường hợp này", "trường hợp đó", "việc này", "việc đó", "điều này", "điều đó",
        "vấn đề này", "vấn đề đó", "như vậy", "thế này", "thế đó", "như thế",
    }

    # Transition & ellipsis conversational prefixes
    TRANSITION_PREFIXES = {
        "còn", "thế còn", "vậy còn", "thế thì", "vậy thì", "đối với",
        "còn đối với", "thế", "còn về", "về phần",
    }

    # English pronouns & transition prefixes for bilingual/enterprise documents
    EN_PRONOUNS = {
        "it", "they", "them", "he", "she", "that", "this", "those", "these",
    }
    EN_TRANSITIONS = {
        "what about", "how about", "and about",
    }

    _PRONOUNS_PATTERN: re.Pattern = re.compile(
        r"\b(" + "|".join(re.escape(p) for p in sorted(PRONOUNS.union(EN_PRONOUNS), key=len, reverse=True)) + r")\b",
        re.IGNORECASE,
    )
    _TRANSITIONS_TUPLE: Tuple[str, ...] = tuple(
        p + " " for p in sorted(TRANSITION_PREFIXES.union(EN_TRANSITIONS), key=len, reverse=True)
    )
    _EXACT_TRANSITIONS_SET: Set[str] = set(TRANSITION_PREFIXES.union(EN_TRANSITIONS))

    # Technical markers (uppercase acronyms, version numbers, codes)
    TECHNICAL_MARKER_REGEX = re.compile(
        r'\b(?:[A-Z0-9_\-\.]{3,}|v\d+(?:\.\d+)*|SOP-\d+|ISO-\d+|API|S3|MINIO|QDRANT|VLLM)\b'
    )

    # Enterprise Vietnamese Acronym & Diacritics Lexicons (decoupled into vietnamese_resources.py)
    ENTERPRISE_ACRONYMS: Dict[str, str] = ENTERPRISE_ACRONYMS
    ACRONYM_CASING_MAP: Dict[str, str] = ACRONYM_CASING_MAP
    CHAT_SHORTHAND_MAP: Dict[str, str] = CHAT_SHORTHAND_MAP
    DIACRITICS_PHRASE_MAP: Dict[str, str] = DIACRITICS_PHRASE_MAP
    DIACRITICS_WORD_MAP: Dict[str, str] = DIACRITICS_WORD_MAP

    _COMPILED_ACRONYMS_PATTERN: Optional[re.Pattern] = None
    _COMPILED_CHAT_SHORTHAND_PATTERN: Optional[re.Pattern] = None
    _COMPILED_WORDS_PATTERN: Optional[re.Pattern] = None
    _COMPILED_PHRASES: List[Tuple[str, re.Pattern, str]] = []
    _COMPILED_EXPANSION_PATTERN: Optional[re.Pattern] = None

    # Common English / technical terms to ignore during unaccented check
    COMMON_ENGLISH_OR_TECH_WORDS = {
        "api", "app", "auth", "admin", "user", "post", "get", "put", "delete",
        "chat", "rag", "json", "pdf", "docx", "url", "http", "https", "token",
        "vector", "dense", "sparse", "rerank", "bm25", "qdrant", "redis", "minio",
        "vllm", "llm", "cpu", "gpu", "ram", "id", "status", "active", "draft",
        "expired", "all", "top", "score", "limit", "filter", "key", "data", "file",
        "true", "false", "null", "none", "ok", "error", "warning", "info", "debug",
    }

    @classmethod
    def _ensure_compiled_lexicons(cls) -> None:
        if not cls._COMPILED_PHRASES:
            acr_keys = sorted(cls.ACRONYM_CASING_MAP.keys(), key=lambda x: (len(x), x), reverse=True)
            if acr_keys:
                cls._COMPILED_ACRONYMS_PATTERN = re.compile(
                    r"\b(" + "|".join(re.escape(k) for k in acr_keys) + r")\b",
                    re.IGNORECASE,
                )

            shorthand_keys = sorted(cls.CHAT_SHORTHAND_MAP.keys(), key=lambda x: (len(x), x), reverse=True)
            if shorthand_keys:
                cls._COMPILED_CHAT_SHORTHAND_PATTERN = re.compile(
                    r"\b(" + "|".join(re.escape(k) for k in shorthand_keys) + r")\b",
                    re.IGNORECASE,
                )

            cls._COMPILED_PHRASES = [
                (k, make_diacritic_tolerant_regex(k), v)
                for k, v in sorted(cls.DIACRITICS_PHRASE_MAP.items(), key=lambda x: len(x[0]), reverse=True)
            ]

            word_keys = sorted(cls.DIACRITICS_WORD_MAP.keys(), key=lambda x: (len(x), x), reverse=True)
            if word_keys:
                cls._COMPILED_WORDS_PATTERN = re.compile(
                    r"\b(" + "|".join(re.escape(k) for k in word_keys) + r")\b",
                    re.IGNORECASE,
                )

            exp_keys = sorted(cls.ENTERPRISE_ACRONYMS.keys(), key=lambda x: (len(x), x), reverse=True)
            if exp_keys:
                cls._COMPILED_EXPANSION_PATTERN = re.compile(
                    r"\b(" + "|".join(re.escape(k) for k in exp_keys) + r")\b",
                    re.IGNORECASE,
                )

    @classmethod
    def normalize_chat_shorthand(cls, text: str) -> str:
        """
        Normalizes conversational shorthand & chat slang (Group A).
        E.g. 'ko' -> 'không', 'dc'/'đc' -> 'được', 'ntn' -> 'như thế nào', 'vs' -> 'với'.
        Strict boundary regex matches only isolated conversational tokens in a single fast pass.
        """
        if not text:
            return ""
        cls._ensure_compiled_lexicons()
        if cls._COMPILED_CHAT_SHORTHAND_PATTERN is None:
            return text

        def _replace_shorthand(m: re.Match) -> str:
            token = m.group(0)
            token_low = token.lower()
            val = cls.CHAT_SHORTHAND_MAP.get(token_low, cls.CHAT_SHORTHAND_MAP.get(strip_accents(token_low), token))
            if token.isupper():
                return val.upper()
            if token.istitle() or token[0].isupper():
                return val.capitalize()
            return val

        return cls._COMPILED_CHAT_SHORTHAND_PATTERN.sub(_replace_shorthand, text)

    VIETNAMESE_ACCENTED_CHARS = set("àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ")

    @classmethod
    def is_unaccented_query(cls, text: str) -> bool:
        """Determines if the input query is largely or fully unaccented."""
        if not text:
            return False
        accented_count = sum(1 for c in text if c in cls.VIETNAMESE_ACCENTED_CHARS)
        words = [w for w in text.split() if w.isalpha() and not w.isupper()]
        if not words:
            return False
        return accented_count == 0 or (len(words) >= 3 and accented_count <= 1)

    @classmethod
    def has_unaccented_words(cls, text: str) -> bool:
        """
        Check if text still contains unaccented Vietnamese words that require model normalization.
        """
        if not text or not cls.is_unaccented_query(text):
            return False
        cleaned = text
        for acr in cls.ACRONYM_CASING_MAP.values():
            cleaned = re.sub(rf"\b{re.escape(acr)}\b", "", cleaned)
        words = re.findall(r"\b[a-zA-Z]{2,}\b", cleaned)
        for w in words:
            low = w.lower()
            if low not in cls.COMMON_ENGLISH_OR_TECH_WORDS and low not in VIETNAMESE_LEVEL_TONE_WORDS and not w.isupper():
                return True
        return False

    @classmethod
    async def normalize_diacritics_with_model(
        cls,
        text: str,
        llm_port: Optional[Any] = None,
        model: str = "chat-general-standard",
        timeout: float = 0.8,
    ) -> str:
        """
        Tier 3: Model-Based Vietnamese Diacritics Normalization (NLP Stage).
        Invoked when deterministic lexicon leaves ambiguous or open-vocabulary
        unaccented words. Uses low-latency prompt with strict timeout guardrail.
        """
        if not text or not llm_port or not cls.has_unaccented_words(text):
            return text

        prompt_messages = [
            {
                "role": "system",
                "content": (
                    "Bạn là chuyên gia NLP tiếng Việt. Hãy khôi phục đầy đủ dấu tiếng Việt cho câu truy vấn sau.\n"
                    "QUY TẮC:\n"
                    "1. Giữ nguyên tất cả các từ viết tắt chuyên ngành (HĐĐT, MST, BHXH, CCCD, SOP, KPI, v.v.) và thuật ngữ kỹ thuật (API, S3, MinIO).\n"
                    "2. Chỉ thêm dấu cho các từ tiếng Việt đang viết không dấu hoặc thiếu dấu.\n"
                    "3. CHỈ TRẢ VỀ CÂU ĐÃ THÊM DẤU, tuyệt đối không giải thích, không thêm ngoặc kép."
                ),
            },
            {"role": "user", "content": text.strip()},
        ]

        try:
            coro = llm_port.generate(
                messages=prompt_messages,
                model=model,
                temperature=0.0,
                max_tokens=64,
            )
            content, _, _ = await asyncio.wait_for(coro, timeout=timeout)
            cleaned = content.strip().strip('"').strip("'").split("\n")[0].strip()
            if cleaned and len(cleaned) >= len(text) * 0.7:
                logger.info("Tier 3 Model Diacritics Normalization: '%s' -> '%s'", text, cleaned)
                return cleaned
        except Exception as exc:
            logger.debug("Tier 3 Model Diacritics Normalization skipped (%s); retaining heuristic result", exc)

        return text

    @classmethod
    def restore_vietnamese_diacritics(cls, text: str) -> str:
        """
        Enterprise Vietnamese Diacritics Restoration (BRD-RAG-06 / FEAT-ENG-01 / UAT-03).
        Restores accents on unaccented enterprise & legal queries (e.g. 'huong dan lam hddt dieu chinh do sai mst'
        -> 'hướng dẫn làm HĐĐT điều chỉnh do sai MST') in < 0.1ms without LLM latency.
        Supports both fully unaccented and mixed/partially unaccented inputs.
        """
        if not text:
            return ""

        cls._ensure_compiled_lexicons()
        result = text

        # 0. Normalize conversational chat shorthands (Group A: ko -> không, ntn -> như thế nào, dc -> được, vs -> với)
        result = cls.normalize_chat_shorthand(result)

        # 1. Normalize acronyms casing regardless of accents (Single pass)
        if cls._COMPILED_ACRONYMS_PATTERN is not None:
            def _replace_acronym(m: re.Match) -> str:
                t = m.group(0)
                tl = t.lower()
                return cls.ACRONYM_CASING_MAP.get(tl, cls.ACRONYM_CASING_MAP.get(strip_accents(tl), t))
            result = cls._COMPILED_ACRONYMS_PATTERN.sub(_replace_acronym, result)

        # 2. Match multi-word compound phrases (longest first, case-preserving with pre-filter)
        norm_result = strip_accents(result)
        for k, pattern, target in cls._COMPILED_PHRASES:
            if k in norm_result:
                def replace_preserve_case(m: re.Match, rep: str = target) -> str:
                    matched_str = m.group(0)
                    if matched_str.isupper():
                        return rep.upper()
                    if matched_str.istitle():
                        return rep.title()
                    if matched_str.islower():
                        words = rep.split()
                        if any(w.isupper() and len(w) >= 2 for w in words):
                            return " ".join(w if (w.isupper() and len(w) >= 2) else w.lower() for w in words)
                        return rep.lower()
                    if matched_str[0].isupper():
                        return rep[0].upper() + rep[1:].lower()
                    return rep

                result = pattern.sub(replace_preserve_case, result)
                norm_result = strip_accents(result)

        # 3. Match high-confidence single functional/legal words (Single pass)
        if cls._COMPILED_WORDS_PATTERN is not None:
            def replace_word_case(m: re.Match) -> str:
                t = m.group(0)
                tl = t.lower()
                rep = cls.DIACRITICS_WORD_MAP.get(tl, t)
                if t.isupper():
                    return rep.upper()
                if t.istitle():
                    return rep.title()
                if t[0].isupper():
                    return rep[0].upper() + rep[1:].lower()
                return rep.lower()

            result = cls._COMPILED_WORDS_PATTERN.sub(replace_word_case, result)

        return result

    @staticmethod
    def strip_vietnamese_diacritics(text: str) -> str:
        """
        Removes Vietnamese diacritics / accents using standard Unicode NFD decomposition.
        Correctly handles đ/Đ -> d/D.
        Example: 'hướng dẫn làm HĐĐT' -> 'huong dan lam HDDT' (FR-RET-01)
        """
        if not text:
            return ""
        res = text.replace("đ", "d").replace("Đ", "D")
        nfd = unicodedata.normalize('NFD', res)
        unaccented = ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')
        return unicodedata.normalize('NFC', unaccented)

    @classmethod
    def expand_acronyms(
        cls,
        text: str,
        custom_glossary: Optional[Dict[str, str]] = None,
        max_expansions: int = 6,
    ) -> str:
        """
        Enterprise Acronym Pre-Retrieval Expansion (RET-RAG-01).
        Fast single-pass acronym expansion with optional custom/tenant glossary support.
        """
        if not text:
            return text

        cls._ensure_compiled_lexicons()

        # Fast path with single-pass precompiled regex for standard enterprise acronyms (< 0.03ms)
        if cls._COMPILED_EXPANSION_PATTERN is not None:
            def _sub_acronym(m: re.Match) -> str:
                acr = m.group(0)
                full = cls.ENTERPRISE_ACRONYMS.get(acr.upper(), cls.ENTERPRISE_ACRONYMS.get(acr))
                if full and full.lower() not in text.lower():
                    return f"{acr} ({full})"
                return acr

            out = cls._COMPILED_EXPANSION_PATTERN.sub(_sub_acronym, text)
        else:
            out = text

        # If custom glossary provided, apply bidirectional expansion
        if custom_glossary:
            from .acronym_harvester import expand_query
            out = expand_query(out, custom_glossary, max_expansions=max_expansions)

        return out

    @classmethod
    def build_dual_token_sparse_query(cls, text: str) -> str:
        """
        Builds dual-token BM25 search query (FR-RET-01 / RET-RAG-01).
        Combines expanded query with unaccented token variants so that
        sparse keyword search achieves >= 95% recall even on unaccented queries.
        """
        expanded = cls.expand_acronyms(text)
        unaccented = cls.strip_vietnamese_diacritics(expanded)
        if unaccented.lower() != expanded.lower():
            return f"{expanded} {unaccented}"
        return expanded

    def _build_rewritten_result(
        self,
        text: str,
        original_query: str,
        tier: str,
        reason: str,
        start_time: float,
        is_reformulated: bool,
        is_standalone_shield_activated: bool = False,
        speculative_query: Optional[str] = None,
    ) -> RewrittenQuery:
        latency = (time.perf_counter() - start_time) * 1000
        restored = self.restore_vietnamese_diacritics(text)
        expanded = self.expand_acronyms(restored)
        unaccented = self.strip_vietnamese_diacritics(expanded)
        sparse_q = f"{expanded} {unaccented}" if unaccented.lower() != expanded.lower() else expanded
        return RewrittenQuery(
            text=restored,
            original_query=original_query,
            tier=tier,
            reason=reason,
            latency_ms=latency,
            is_reformulated=is_reformulated or (restored != text),
            is_standalone_shield_activated=is_standalone_shield_activated,
            speculative_query=speculative_query or restored,
            expanded_query=expanded,
            unaccented_variant=unaccented,
            sparse_query=sparse_q,
        )

    @staticmethod
    def _clean_text(text: str) -> str:
        """Strip trailing punctuation, extra spaces, and normalizes characters."""
        return re.sub(r'[\?\.\!\s]+$', '', text.strip()).strip()

    def _extract_last_user_turn(self, history: Optional[List[Dict[str, str]]]) -> Optional[str]:
        """Extract the most recent user turn from conversational history."""
        if not history:
            return None
        user_turns = [
            m.get("content", "").strip()
            for m in history
            if m.get("role") == "user" and m.get("content") and m.get("content").strip()
        ]
        return user_turns[-1] if user_turns else None

    def _stitch_ellipsis(self, last_topic: str, target: str) -> str:
        """
        Deterministic topic stitching for ellipsis follow-ups.
        Example:
          last_topic: 'Quy định về thời gian thử việc của nhân viên chính thức'
          target: 'nhân viên thử việc'
          -> 'Quy định về thời gian thử việc của nhân viên thử việc'
        """
        clean_last = self._clean_text(last_topic)
        clean_target = self._clean_text(target)

        # Look for trailing entity prepositional phrase: "của ...", "cho ...", "đối với ..."
        prep_match = re.search(r'\s+(của|cho|đối với)\s+([^,]+)$', clean_last, flags=re.IGNORECASE)
        if prep_match:
            prefix = clean_last[:prep_match.start()].strip()
            prep = prep_match.group(1)
            return f"{prefix} {prep} {clean_target}"

        # If no preposition match, append target with contextual preposition
        return f"{clean_last} đối với {clean_target}"

    def _try_tier_1_fast_track(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]],
        start_time: float,
    ) -> Optional[RewrittenQuery]:
        """
        Tier 1: Heuristic Fast-Track Engine (< 1ms, 0 Token Cost).
        Resolves or bypasses queries deterministically without LLM calls.
        """
        clean_q = query.strip()
        last_user_turn = self._extract_last_user_turn(history)

        # 1A. Single-turn Bypass: No history or no valid previous user turns (< 0.01ms)
        if not history or not last_user_turn:
            return self._build_rewritten_result(text=clean_q, original_query=query, tier="TIER_1_HEURISTIC", reason="empty_history", start_time=start_time, is_reformulated=False, is_standalone_shield_activated=True)

        lower_q = clean_q.lower()
        words = clean_q.split()

        # Check for conversational pronouns and transition markers (< 0.005ms)
        has_pronoun = bool(self._PRONOUNS_PATTERN.search(lower_q))
        has_transition = lower_q.startswith(self._TRANSITIONS_TUPLE) or (lower_q in self._EXACT_TRANSITIONS_SET)

        # 1B. Standalone Query Detection (Bypass LLM)
        # If query has no pronouns and no transitions:
        if not has_pronoun and not has_transition:
            # Complete standalone query with >= 4 words or quotes or technical identifiers
            has_quotes = ('"' in clean_q) or ("'" in clean_q)
            has_technical = bool(self.TECHNICAL_MARKER_REGEX.search(clean_q))
            if len(words) >= 4 or has_quotes or has_technical:
                return self._build_rewritten_result(text=clean_q, original_query=query, tier="TIER_1_HEURISTIC", reason="standalone_query", start_time=start_time, is_reformulated=False, is_standalone_shield_activated=True)

        # 1C. Deterministic Ellipsis Stitching ('Thế còn [X]?', 'Còn về [X] thì sao?', 'Về phần [X]?')
        ellipsis_match = re.match(
            r'^(?:thế\s+còn|vậy\s+còn|còn|thế\s+về|vậy\s+về|còn\s+về|về\s+phần)\s+(.+?)(?:\s+thì\s+sao)?[\?\.\!\s]*$',
            clean_q,
            re.IGNORECASE,
        )
        if ellipsis_match:
            target = ellipsis_match.group(1).strip()
            stitched = self._stitch_ellipsis(last_user_turn, target)
            return self._build_rewritten_result(text=stitched, original_query=query, tier="TIER_1_HEURISTIC", reason="heuristic_ellipsis", start_time=start_time, is_reformulated=True, is_standalone_shield_activated=False, speculative_query=stitched)

        # 1D. Deterministic Leading Pronoun Replacement ('Nó/Họ/Chính sách đó có hiệu lực từ khi nào?')
        pronoun_match = re.match(
            r'^(nó|chúng|họ|người\s+đó|ông\s+đó|bà\s+đó|anh\s+đó|chị\s+đó|chế\s+độ\s+đó|chính\s+sách\s+đó|quy\s+định\s+đó|tài\s+liệu\s+đó|hợp\s+đồng\s+đó|văn\s+bản\s+đó)\s+(.+)$',
            clean_q,
            re.IGNORECASE,
        )
        if pronoun_match:
            rest = pronoun_match.group(2).strip()
            clean_last = self._clean_text(last_user_turn)
            rewritten_text = f"{clean_last} {rest}"
            return self._build_rewritten_result(text=rewritten_text, original_query=query, tier="TIER_1_HEURISTIC", reason="heuristic_pronoun_replacement", start_time=start_time, is_reformulated=True, is_standalone_shield_activated=False, speculative_query=rewritten_text)

        # 1E. Deterministic Explanation Follow-up ('Tại sao?', 'Vì sao?')
        if re.match(r'^(tại\s+sao|vì\s+sao|lý\s+do\s+gì)[\?\.\!\s]*$', clean_q, re.IGNORECASE):
            clean_last = self._clean_text(last_user_turn)
            rewritten_text = f"{clean_last} - {clean_q}"
            return self._build_rewritten_result(text=rewritten_text, original_query=query, tier="TIER_1_HEURISTIC", reason="heuristic_explanation", start_time=start_time, is_reformulated=True, is_standalone_shield_activated=False, speculative_query=rewritten_text)

        # 1F. Deterministic Condition Follow-up ('Có được không?', 'Được không?')
        if re.match(r'^(có\s+được\s+không|được\s+không)[\?\.\!\s]*$', clean_q, re.IGNORECASE):
            clean_last = self._clean_text(last_user_turn)
            rewritten_text = f"{clean_last} {clean_q}"
            return self._build_rewritten_result(text=rewritten_text, original_query=query, tier="TIER_1_HEURISTIC", reason="heuristic_condition", start_time=start_time, is_reformulated=True, is_standalone_shield_activated=False, speculative_query=rewritten_text)

        # If query contains complex pronouns, transitions, or is an ambiguous follow-up,
        # defer directly to Tier 2 LLM Reformulation for genuine contextual resolution.
        return None

    async def rewrite_advanced(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
        llm_port: Optional[Any] = None,
        model: str = "chat-general-standard",
        speculative_timeout: float = 0.8,
    ) -> RewrittenQuery:
        """
        Two-Tier Pre-Retrieval Orchestrator.
        1. Executes Tier 1 Heuristic Fast-Track (< 1ms, 0 Token Cost).
        2. If ambiguous, triggers Tier 2 Async Speculative LLM Fallback (bounded by speculative_timeout).
        """
        start_time = time.perf_counter()

        # Execute Tier 1 Fast-Track
        fast_track_result = self._try_tier_1_fast_track(query, history, start_time)
        if fast_track_result is not None:
            # Tier 3 NLP Hook: If input query was unaccented, still contains unaccented words after dictionary, and llm_port is available
            if llm_port and self.is_unaccented_query(query) and self.has_unaccented_words(fast_track_result.text):
                normalized = await self.normalize_diacritics_with_model(
                    fast_track_result.text,
                    llm_port=llm_port,
                    model=model,
                    timeout=min(speculative_timeout, 0.8),
                )
                if normalized != fast_track_result.text:
                    fast_track_result = self._build_rewritten_result(
                        text=normalized,
                        original_query=query,
                        tier="TIER_1_HEURISTIC_PLUS_MODEL_NLP",
                        reason=f"{fast_track_result.reason}+model_diacritics",
                        start_time=start_time,
                        is_reformulated=True,
                        is_standalone_shield_activated=fast_track_result.is_standalone_shield_activated,
                    )
            logger.debug(
                "Pre-Retrieval Tier 1 Fast-Track: '%s' -> '%s' (reason: %s, %.2f ms)",
                query,
                fast_track_result.text,
                fast_track_result.reason,
                fast_track_result.latency_ms,
            )
            return fast_track_result

        # Prepare heuristic speculative candidate before invoking Tier 2
        last_user_turn = self._extract_last_user_turn(history) or ""
        last_topic = self._clean_text(last_user_turn)
        speculative_candidate = f"{last_topic} {query.strip()}".strip()

        # If LLM port is absent, fall back immediately to heuristic candidate
        if not llm_port:
            return self._build_rewritten_result(text=speculative_candidate, original_query=query, tier="TIER_1_HEURISTIC", reason="heuristic_stitching_fallback", start_time=start_time, is_reformulated=True, is_standalone_shield_activated=False, speculative_query=speculative_candidate)

        # Tier 2: Async Speculative LLM Fallback
        rewrite_messages = [
            {
                "role": "system",
                "content": (
                    "Bạn là bộ tiền xử lý câu hỏi tra cứu (Search Query Reformulator) chuẩn hóa RAG doanh nghiệp.\n"
                    "Dựa vào lịch sử hội thoại trước đó, hãy viết lại câu hỏi cuối cùng của người dùng thành MỘT CÂU HỎI ĐỘC LẬP "
                    "đầy đủ ngữ cảnh và chủ ngữ rõ ràng để tra cứu tài liệu.\n"
                    "CHỈ TRẢ VỀ CÂU HỎI ĐÃ ĐƯỢC VIẾT LẠI, không thêm lời giải thích hay ngoặc kép."
                ),
            },
            *(history[-4:] if history else []),
            {"role": "user", "content": f"Viết lại câu hỏi sau thành câu độc lập: {query.strip()}"},
        ]

        try:
            coro = llm_port.generate(
                messages=rewrite_messages,
                model=model,
                temperature=0.0,
                max_tokens=48,
            )
            content, _, _ = await asyncio.wait_for(coro, timeout=speculative_timeout)
            rewritten = content.strip().strip('"').strip("'")
            if "\n" in rewritten:
                rewritten = rewritten.split("\n")[0].strip()

            if rewritten and len(rewritten) >= 3:
                latency = (time.perf_counter() - start_time) * 1000
                logger.info(
                    "Pre-Retrieval Tier 2 LLM Reformulation: '%s' -> '%s' (%.2f ms)",
                    query,
                    rewritten,
                    latency,
                )
                return self._build_rewritten_result(text=rewritten, original_query=query, tier="TIER_2_SPECULATIVE_LLM", reason="llm_reformulated", start_time=start_time, is_reformulated=True, is_standalone_shield_activated=False, speculative_query=speculative_candidate)
        except asyncio.TimeoutError:
            latency = (time.perf_counter() - start_time) * 1000
            logger.warning(
                "Pre-Retrieval Tier 2 LLM timed out after %.2fs. Bypassing to heuristic speculative query: '%s'",
                speculative_timeout,
                speculative_candidate,
            )
            return self._build_rewritten_result(text=speculative_candidate, original_query=query, tier="TIER_2_TIMEOUT_FALLBACK", reason="llm_timeout_fallback", start_time=start_time, is_reformulated=True, is_standalone_shield_activated=False, speculative_query=speculative_candidate)
        except Exception as exc:
            latency = (time.perf_counter() - start_time) * 1000
            logger.warning(
                "Pre-Retrieval Tier 2 LLM error: %s. Falling back to heuristic candidate: '%s'",
                exc,
                speculative_candidate,
            )
            return self._build_rewritten_result(text=speculative_candidate, original_query=query, tier="TIER_2_ERROR_FALLBACK", reason="llm_error_fallback", start_time=start_time, is_reformulated=True, is_standalone_shield_activated=False, speculative_query=speculative_candidate)

        # Fallback if LLM output was invalid
        return self._build_rewritten_result(text=speculative_candidate, original_query=query, tier="TIER_2_SPECULATIVE_LLM", reason="llm_empty_fallback", start_time=start_time, is_reformulated=True, is_standalone_shield_activated=False, speculative_query=speculative_candidate)

    async def rewrite(
        self,
        query: str,
        history: Optional[List[Dict[str, str]]] = None,
        llm_port: Optional[Any] = None,
        model: str = "chat-general-standard",
        speculative_timeout: float = 0.8,
    ) -> str:
        """
        Backward-compatible facade returning standalone string.
        """
        decision = await self.rewrite_advanced(
            query=query,
            history=history,
            llm_port=llm_port,
            model=model,
            speculative_timeout=speculative_timeout,
        )
        return decision.text


query_rewriter = RagQueryRewriter()
RagQueryRewriter._ensure_compiled_lexicons()
restore_vietnamese_diacritics = RagQueryRewriter.restore_vietnamese_diacritics
expand_acronyms = RagQueryRewriter.expand_acronyms
strip_vietnamese_diacritics = RagQueryRewriter.strip_vietnamese_diacritics
build_dual_token_sparse_query = RagQueryRewriter.build_dual_token_sparse_query
normalize_diacritics_with_model = RagQueryRewriter.normalize_diacritics_with_model
normalize_chat_shorthand = RagQueryRewriter.normalize_chat_shorthand
