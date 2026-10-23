"""
Enterprise Acronym & Glossary Harvester for AIP RAG.
Production-grade multi-stage extraction, derivation, enrichment, and query expansion.

Stages:
  0. DETECT   : Token scanning, candidate filtering, code/Roman exclusions, heading isolation.
  1. EXPLICIT : Section/table parsing ("Điều 2. Giải thích từ ngữ") + Inline definitions ("Full (ABBR)").
  2. DERIVE   : Window-matching dynamic programming for undefined-but-written-out acronyms (with digraphs & connectors).
  3. DICT     : Global Vietnamese Enterprise Glossary (from vietnamese_resources) + Tenant override dictionary.
  4. LLM      : 1-shot batched fallback for unresolved candidates with contextual snippets (optional).
  5. REPORT   : Detailed coverage metrics & unresolved inventory.

Index & Query Time Integration:
  - enrich_chunk_for_embedding : Eliminates Cross-Chunk Disconnection by prepending definitions to search text.
  - expand_query               : Bi-directional expansion (ABBR -> Full, Full -> ABBR) for Hybrid Dense + BM25 search.
  - glossary_for_prompt        : Contextual token-saving glossary injection for LLM generation.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import unicodedata

from .vietnamese_resources import (
    ENTERPRISE_ACRONYMS,
)

logger = logging.getLogger("aip-rag.acronym_harvester")

# --------------------------------------------------------------------------- #
# Regex patterns & basic normalization
# --------------------------------------------------------------------------- #

_TOK = re.compile(r"[^\s,;:()\[\]{}“”\"'!?<>|•]+")
_ROMAN = re.compile(r"^(?=[IVXLCDM]+$)M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")
_IGNORE = {
    "VND", "USD", "EUR", "PDF", "DOCX", "XLSX", "HTTP", "HTTPS", "URL", "KG", "KM", "OK", "STT", "NO", "FAX", "TEL"
}

_ABBR_PATTERN = r"[A-ZĐ][A-Za-zĐđ0-9_\-\.]{1,14}"
_WORD_PATTERN = r"[A-Za-zÀ-ỹĐđ]+"
_CONN_WORDS = {"cua", "va", "ve", "cho", "tai", "trong", "de", "la", "voi", "tu"}
_WORD_RE = re.compile(r"[^\W\d_]+")
_GAP_OK = re.compile(r"^(?:[ \t]*\n?[ \t]*|[ \t]*[-–/][ \t]*)$")

# Common Vietnamese digraphs for acronym resolution (Tr, Th, Ph, Ch, Nh, Kh, Gh, Ng)
_VI_DIGRAPHS = {"tr", "th", "ph", "ch", "nh", "kh", "gh", "ng"}


def strip_accents(s: str) -> str:
    """Strips Vietnamese diacritics/accents to ASCII lowercase equivalent."""
    if not s:
        return ""
    res = s.replace("Đ", "D").replace("đ", "d")
    nfd = unicodedata.normalize("NFD", res)
    unaccented = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return unicodedata.normalize("NFC", unaccented).lower().strip()


def _is_upper_token(t: str) -> bool:
    letters = [c for c in t if c.isalpha()]
    return len(letters) >= 2 and all(c.isupper() for c in letters)


def _is_mixed_token(t: str) -> bool:
    """TTr, TPHCM, BQLDA ... : >=2 leading uppercase then 1-2 lowercase, letters only."""
    if not t.isalpha() or len(t) < 3:
        return False
    i = 0
    while i < len(t) and t[i].isupper():
        i += 1
    return i >= 2 and 1 <= len(t) - i <= 2 and t[i:].islower()


def _is_heading_line(line: str) -> bool:
    toks = re.findall(r"[^\W\d_]+", line)
    if len(toks) < 3:
        return False
    up = sum(1 for t in toks if t.isupper())
    return (up / len(toks)) >= 0.8


def _normalize_abbr(a: str) -> str:
    return re.sub(r"\s+", "", a.strip().strip(".,;:\"'“”‘’"))


def _clean_full(f: str) -> str:
    return re.sub(r"\s+", " ", f.strip().strip(".,;:\"'“”‘’-–— "))


def _abbr_letters(abbr: str) -> str:
    return "".join(c for c in strip_accents(abbr) if c.isalpha())


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #

@dataclass
class Candidate:
    abbr: str
    count: int
    is_code: bool  # True if contains digits / separators (QT-NS-05, 123/NĐ-CP)
    first_pos: int
    positions: List[int]


@dataclass
class Entry:
    full: str
    source: str  # "section" | "inline" | "derived" | "dict" | "llm"
    confidence: float


@dataclass
class Report:
    unique_total: int
    unique_resolved: int
    mention_total: int
    mention_resolved: int
    codes_skipped: int
    by_source: Dict[str, int]
    unresolved: List[Tuple[str, int]]

    @property
    def unique_coverage(self) -> float:
        return self.unique_resolved / self.unique_total if self.unique_total else 1.0

    @property
    def mention_coverage(self) -> float:
        return self.mention_resolved / self.mention_total if self.mention_total else 1.0


@dataclass
class PipelineResult:
    entries: Dict[str, Entry]
    report: Report

    @property
    def glossary(self) -> Dict[str, str]:
        return {k: v.full for k, v in self.entries.items()}


@dataclass
class _WordSpan:
    raw: str
    norm: str
    start: int
    end: int


# --------------------------------------------------------------------------- #
# Stage 0: Detection
# --------------------------------------------------------------------------- #

def detect_candidates(text: str) -> Dict[str, Candidate]:
    """Scans full document text to discover all acronym-like candidates."""
    cands: Dict[str, Candidate] = {}
    offset = 0
    for line in text.splitlines(keepends=True):
        heading = _is_heading_line(line)
        for m in _TOK.finditer(line):
            raw = m.group(0).strip(".-/–—")
            if not raw or (any(c.isdigit() for c in raw) and not any(c.isalpha() for c in raw)):
                continue
            if _ROMAN.match(raw) or raw.upper() in _IGNORE:
                continue
            ok = _is_upper_token(raw) or _is_mixed_token(raw)
            if not ok:
                continue
            has_digit = any(c.isdigit() for c in raw)
            has_sep = any(c in raw for c in ".-/")
            if heading and not has_digit and not has_sep:
                continue  # Skip all-caps heading words (CỘNG HÒA XÃ HỘI ...)

            pos = offset + m.start()
            c = cands.get(raw)
            if c is None:
                cands[raw] = Candidate(raw, 1, has_digit or has_sep, pos, [pos])
            else:
                c.count += 1
                c.positions.append(pos)
        offset += len(line)
    return cands


# --------------------------------------------------------------------------- #
# Stage 1: Explicit Harvesting (Sections & Inline)
# --------------------------------------------------------------------------- #

# Inline regexes
_RE_PAREN = re.compile(
    rf"((?:{_WORD_PATTERN}[ \t]+){{1,9}}{_WORD_PATTERN})[ \t]*\(\s*({_ABBR_PATTERN})\s*\)"
)

_RE_GOI_TAT = re.compile(
    rf"((?:{_WORD_PATTERN}[ \t]+){{0,11}}{_WORD_PATTERN})[ \t]*,?[ \t]*\(\s*"
    rf"(?:sau đây|dưới đây|sau này)?\s*(?:gọi tắt là|gọi là|viết tắt là|viết tắt:|viết tắt)\s*"
    rf"[\"“‘']?\s*({_ABBR_PATTERN}(?:\s{_ABBR_PATTERN})?)\s*[\"”’']?\s*\)",
    re.IGNORECASE,
)

_RE_REVERSE = re.compile(
    rf"\b({_ABBR_PATTERN})[ \t]*\(\s*((?:{_WORD_PATTERN}[ \t]+){{1,9}}{_WORD_PATTERN})\s*\)"
)

# Section regexes
_RE_SECTION_HEAD = re.compile(
    r"^\s*(?:(?:Điều|Mục|Phần|Chương)\s+[\dIVXLC]+[\.\:]?\s*)?"
    r"(?:giải thích từ ngữ|giải thích thuật ngữ|quy ước viết tắt|danh mục từ viết tắt|"
    r"từ viết tắt|các từ viết tắt|ký hiệu viết tắt|thuật ngữ và từ viết tắt|định nghĩa và từ viết tắt)"
    r"[^\n]{0,60}$",
    re.IGNORECASE | re.MULTILINE,
)
_RE_ANY_HEAD = re.compile(
    r"^\s*(?:Điều|Chương|Phần|Mục)\s+[\dIVXLC]+[\.\:]", re.IGNORECASE | re.MULTILINE
)

_RE_KV_LINE = re.compile(
    rf"^\s*(?:[-•*+]\s*|\d+[\.\)]\s*|[a-z][\.\)]\s*)?({_ABBR_PATTERN})\s*(?::|=|–|—|-|→)\s*(.{{3,150}}?)\s*[;\.]?\s*$",
    re.MULTILINE,
)
_RE_TABLE_ROW = re.compile(
    rf"^\s*\|?\s*(?:\d+\s*\|\s*)?({_ABBR_PATTERN})\s*[\|\t]\s*([^\|\t\n]{{3,150}}?)\s*\|?\s*$",
    re.MULTILINE,
)
_RE_LA = re.compile(
    rf"^\s*(?:[a-z\d][\.\)]\s*)?({_ABBR_PATTERN})\s+là\s+(.{{3,150}}?)\s*[;\.]?\s*$",
    re.MULTILINE,
)


def _initials_match(abbr: str, words: List[str]) -> bool:
    """Checks if abbreviation letters match word initials, allowing connector skipping & digraphs."""
    letters = [c for c in strip_accents(abbr) if c.isalpha()]
    if len(letters) < 2:
        return False

    clean_words = [strip_accents(w) for w in words if w]
    ini_all = [w[0] for w in clean_words if w]
    ini_noskip = [w[0] for w in clean_words if w and w not in _CONN_WORDS]

    if letters == ini_all or letters == ini_noskip:
        return True

    # Check for Vietnamese digraphs (e.g. Tr -> TTr, Kh -> BKH)
    p = 0
    w_idx = 0
    while p < len(letters) and w_idx < len(clean_words):
        w = clean_words[w_idx]
        if w in _CONN_WORDS and letters[p] != w[0]:
            w_idx += 1
            continue
        if p + 1 < len(letters) and len(w) >= 2 and w[:2] == "".join(letters[p : p + 2]):
            p += 2
            w_idx += 1
        elif letters[p] == w[0]:
            p += 1
            w_idx += 1
        else:
            return False
    return p == len(letters)


def _extract_glossary_blocks(text: str, max_block_chars: int = 8000) -> List[str]:
    blocks: List[str] = []
    for m in _RE_SECTION_HEAD.finditer(text):
        start = m.end()
        nxt = _RE_ANY_HEAD.search(text, start)
        end = min(nxt.start() if nxt else len(text), start + max_block_chars)
        blocks.append(text[start:end])
    return blocks


def harvest_explicit(text: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Harvests explicit glossary from dedicated sections and inline definitions."""
    glossary: Dict[str, str] = {}
    sources: Dict[str, str] = {}

    # 1. Dedicated glossary section (highest priority)
    for block in _extract_glossary_blocks(text):
        for rx in (_RE_KV_LINE, _RE_TABLE_ROW, _RE_LA):
            for m in rx.finditer(block):
                abbr, full = _normalize_abbr(m.group(1)), _clean_full(m.group(2))
                if len(abbr) >= 2 and full and abbr.lower() != full.lower():
                    glossary[abbr] = full
                    sources[abbr] = "section"

    # 2. Inline 'gọi tắt là'
    for m in _RE_GOI_TAT.finditer(text):
        full, abbr = _clean_full(m.group(1)), _normalize_abbr(m.group(2))
        if abbr not in glossary:
            glossary[abbr] = full
            sources[abbr] = "inline"

    # 3. Inline 'Full (ABBR)'
    for m in _RE_PAREN.finditer(text):
        words_str, abbr = m.group(1), _normalize_abbr(m.group(2))
        words = words_str.split()
        letters = [c for c in strip_accents(abbr) if c.isalpha()]
        n = len(letters)
        if n < 2:
            continue
        for k in range(min(len(words), n + 3), 1, -1):
            cand = words[-k:]
            if _initials_match(abbr, cand):
                if abbr not in glossary:
                    glossary[abbr] = _clean_full(" ".join(cand))
                    sources[abbr] = "inline"
                break

    # 4. Inline reverse 'ABBR (Full)'
    for m in _RE_REVERSE.finditer(text):
        abbr, full = _normalize_abbr(m.group(1)), _clean_full(m.group(2))
        if _initials_match(abbr, full.split()):
            if abbr not in glossary:
                glossary[abbr] = full
                sources[abbr] = "inline"

    return glossary, sources


# --------------------------------------------------------------------------- #
# Stage 2: Derive Acronyms from Text Windows (Dynamic Programming)
# --------------------------------------------------------------------------- #

def _tokenize_words(text: str, skip_upper: Set[str]) -> List[_WordSpan]:
    out: List[_WordSpan] = []
    for m in _WORD_RE.finditer(text):
        raw = m.group(0)
        if len(raw) >= 2 and raw.isupper() and raw in skip_upper:
            continue
        out.append(_WordSpan(raw, strip_accents(raw), m.start(), m.end()))
    return out


def _window_matches(letters: str, words: List[str]) -> bool:
    """Dynamic programming recursive search for acronym expansion."""
    n = len(words)

    @lru_cache(maxsize=1024)
    def rec(p: int, j: int) -> bool:
        if j == n:
            return p == len(letters)
        w = words[j]
        # Match single initial
        if p < len(letters) and w[0] == letters[p] and rec(p + 1, j + 1):
            return True
        # Match digraph (e.g. Tr -> TTr, Kh -> BKH)
        if p + 1 < len(letters) and len(w) >= 2 and w[:2] == letters[p : p + 2] and rec(p + 2, j + 1):
            return True
        # Skip connector word
        if w in _CONN_WORDS and rec(p, j + 1):
            return True
        return False

    return rec(0, 0)


def derive_from_text(
    text: str,
    unresolved: Dict[str, Candidate],
    all_abbrs: Set[str],
) -> Dict[str, Tuple[str, float]]:
    """Derives full forms for unresolved acronyms using document-wide context."""
    if not unresolved:
        return {}

    words = _tokenize_words(text, all_abbrs)
    by_first: Dict[str, List[int]] = defaultdict(list)
    for i, w in enumerate(words):
        if w.norm and w.norm[0] not in _CONN_WORDS:
            by_first[w.norm[0]].append(i)

    results: Dict[str, Tuple[str, float]] = {}
    for abbr, cand in unresolved.items():
        if cand.is_code:
            continue
        letters = _abbr_letters(abbr)
        n = len(letters)
        if n < 2 or n > 10:
            continue
        max_words = n + 3
        occ = cand.positions
        windows: Dict[str, Dict[str, Any]] = {}

        for i in by_first.get(letters[0], []):
            for j in range(i + 1, min(len(words), i + max_words)):
                if not _GAP_OK.match(text[words[j - 1].end : words[j].start]):
                    break
                if words[j].norm in _CONN_WORDS:
                    continue
                seg = words[i : j + 1]
                if len(seg) < 2:
                    continue
                if not _window_matches(letters, [w.norm for w in seg]):
                    continue

                s, e = seg[0].start, seg[-1].end
                key = " ".join(w.norm for w in seg)
                d = windows.setdefault(
                    key,
                    {
                        "raw": re.sub(r"\s+", " ", text[s:e]),
                        "freq": 0,
                        "dist": 10**9,
                        "caps": 0,
                        "spans": [],
                    },
                )
                d["freq"] += 1
                d["spans"].append((s, e))
                dist = min(
                    (min(abs(o - e), abs(s - (o + len(abbr)))) for o in occ),
                    default=10**9,
                )
                d["dist"] = min(d["dist"], dist)
                d["caps"] = max(d["caps"], sum(1 for w in seg if w.raw[0].isupper()))

        best_key, best_score = None, 0.0
        for key, d in windows.items():
            nwords = len(key.split())
            adj = 3 if d["dist"] <= 8 else 2 if d["dist"] <= 150 else 0
            cap = 1 if d["caps"] * 2 >= nwords else 0
            score = d["freq"] + adj + cap
            if n == 2 and adj < 3:
                continue
            if n >= 3 and score < 3:
                continue
            if score > best_score:
                best_key, best_score = key, score

        if best_key:
            d = windows[best_key]
            conf = min(0.95, 0.5 + 0.1 * best_score)
            results[abbr] = (d["raw"], round(conf, 2))

    return results


# --------------------------------------------------------------------------- #
# Stage 4: LLM 1-shot batched fallback
# --------------------------------------------------------------------------- #

LLM_PROMPT = """Bạn là chuyên gia bóc tách thuật ngữ và từ viết tắt trong tài liệu doanh nghiệp và pháp lý tiếng Việt.
Với mỗi từ viết tắt dưới đây, dựa CHỈ VÀO các đoạn ngữ cảnh đi kèm trích xuất từ tài liệu, hãy xác định dạng đầy đủ (nghĩa mở rộng).
QUY TẮC BẮT BUỘC:
1. Nếu ngữ cảnh không có căn cứ rõ ràng, hãy trả về null. TUYỆT ĐỐI KHÔNG đoán mò.
2. CHỈ TRẢ VỀ DUY NHẤT một JSON object định dạng {{"TỪ_VIẾT_TẮT": "Dạng đầy đủ hoặc null"}}, không giải thích thêm.

{items}
"""


def build_llm_items(
    text: str, unresolved: Dict[str, Candidate], max_items: int = 40, ctx: int = 140
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for abbr, c in sorted(unresolved.items(), key=lambda kv: -kv[1].count)[:max_items]:
        ctxs: List[str] = []
        for p in (c.positions[0], c.positions[-1]):
            snippet = text[max(0, p - ctx) : p + len(abbr) + ctx].replace("\n", " ")
            if snippet not in ctxs:
                ctxs.append(snippet)
        items.append({"abbr": abbr, "contexts": ctxs})
    return items


def render_llm_prompt(items: List[Dict[str, Any]]) -> str:
    body = "\n".join(
        f"### {it['abbr']}\n" + "\n".join(f"- ...{c}..." for c in it["contexts"]) for it in items
    )
    return LLM_PROMPT.format(items=body)


def parse_llm_json(s: str) -> Dict[str, str]:
    cleaned = re.sub(r"^```(?:json)?|```$", "", s.strip(), flags=re.M).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        k: v.strip()
        for k, v in data.items()
        if isinstance(v, str) and v.strip() and v.lower() != "null"
    }


# --------------------------------------------------------------------------- #
# Acronym Harvester Orchestrator & Public API
# --------------------------------------------------------------------------- #

class AcronymHarvester:
    """Production Enterprise Acronym & Glossary Harvester."""

    def __init__(self, global_dict: Optional[Dict[str, str]] = None) -> None:
        # Defaults to ENTERPRISE_ACRONYMS from vietnamese_resources
        self.global_dict = dict(ENTERPRISE_ACRONYMS)
        if global_dict:
            self.global_dict.update(global_dict)

    def harvest(
        self,
        text: str,
        tenant_dict: Optional[Dict[str, str]] = None,
        llm_resolver: Optional[Callable[[str], str]] = None,
        use_global_dict: bool = True,
    ) -> PipelineResult:
        """
        Runs full 5-stage harvesting pipeline on document text.
        Returns PipelineResult with glossary and execution report.
        """
        cands = detect_candidates(text)
        entries: Dict[str, Entry] = {}

        # 1. Explicit sections and inline
        exp_glossary, exp_sources = harvest_explicit(text)
        for k, v in exp_glossary.items():
            conf = 0.98 if exp_sources[k] == "section" else 0.90
            entries[k] = Entry(v, exp_sources[k], conf)

        def unresolved_candidates() -> Dict[str, Candidate]:
            return {a: c for a, c in cands.items() if a not in entries and not c.is_code}

        # 2. Derive from document text windows
        der = derive_from_text(text, unresolved_candidates(), set(cands))
        for k, (v, conf) in der.items():
            entries[k] = Entry(v, "derived", conf)

        # 3. Global & Tenant Dictionary fallback
        active_dicts: Dict[str, str] = {}
        if use_global_dict:
            active_dicts.update(self.global_dict)
        if tenant_dict:
            active_dicts.update(tenant_dict)

        for a in list(unresolved_candidates()):
            if a in active_dicts:
                entries[a] = Entry(active_dicts[a], "dict", 0.85)

        # 4. LLM 1-shot batched fallback (optional)
        if llm_resolver:
            remaining = unresolved_candidates()
            if remaining:
                items = build_llm_items(text, remaining)
                try:
                    raw_llm = llm_resolver(render_llm_prompt(items))
                    got = parse_llm_json(raw_llm)
                except Exception as exc:
                    logger.debug("LLM acronym resolution skipped (%s)", exc)
                    got = {}
                for k, v in got.items():
                    if k in remaining:
                        entries[k] = Entry(v, "llm", 0.60)

        # 5. Build report
        non_code = {a: c for a, c in cands.items() if not c.is_code}
        resolved_u = [a for a in non_code if a in entries]
        report = Report(
            unique_total=len(non_code),
            unique_resolved=len(resolved_u),
            mention_total=sum(c.count for c in non_code.values()),
            mention_resolved=sum(non_code[a].count for a in resolved_u),
            codes_skipped=sum(1 for c in cands.values() if c.is_code),
            by_source=dict(Counter(e.source for e in entries.values())),
            unresolved=sorted(
                ((a, c.count) for a, c in non_code.items() if a not in entries),
                key=lambda x: -x[1],
            ),
        )

        return PipelineResult(entries=entries, report=report)

    @staticmethod
    def enrich_chunk_for_embedding(
        chunk_text: str, glossary: Dict[str, str], max_items: int = 5
    ) -> str:
        """
        Enriches text for embedding & BM25 sparse indexing by prepending definitions
        of acronyms present in the chunk.
        Solves Cross-Chunk Disconnection at index time (RET-RAG-01).
        """
        if not chunk_text or not glossary:
            return chunk_text

        hits: List[Tuple[str, str]] = []
        for abbr, full in glossary.items():
            if re.search(rf"(?<![\w\-]){re.escape(abbr)}(?![\w\-])", chunk_text):
                hits.append((abbr, full))

        if not hits:
            return chunk_text

        prefix = "; ".join(f"{a}: {f}" for a, f in hits[:max_items])
        return f"[{prefix}]\n{chunk_text}"

    @staticmethod
    def expand_query(query: str, glossary: Dict[str, str], max_expansions: int = 6) -> str:
        """
        Bi-directional query expansion (RET-RAG-01):
        - Abbreviation in query: 'BBBG' -> 'BBBG (Biên bản bàn giao)' (improves dense vector)
        - Full term in query: 'Ban Quản lý' -> 'Ban Quản lý (BQL)' (improves BM25 on acronym-only chunks)
        """
        if not query or not glossary:
            return query

        out = query
        count = 0

        # 1. ABBR -> Full expansion
        for abbr in sorted(glossary, key=len, reverse=True):
            if count >= max_expansions:
                break
            pat = re.compile(rf"(?<![\w\-]){re.escape(abbr)}(?![\w\-])(?!\s*\()", re.IGNORECASE)
            if pat.search(out):
                out = pat.sub(f"{abbr} ({glossary[abbr]})", out, count=1)
                count += 1

        # 2. Full -> ABBR expansion
        lowered = out.lower()
        matched_fulls: List[str] = []
        for abbr, full in sorted(glossary.items(), key=lambda kv: len(kv[1]), reverse=True):
            if count >= max_expansions:
                break
            f = full.lower()
            if any(f in m for m in matched_fulls):
                continue
            if f in lowered and f"({abbr.lower()})" not in lowered and abbr.lower() not in lowered:
                matched_fulls.append(f)
                idx = lowered.index(f)
                out = out[: idx + len(f)] + f" ({abbr})" + out[idx + len(f) :]
                lowered = out.lower()
                count += 1

        return out

    @staticmethod
    def glossary_for_prompt(
        glossary: Dict[str, str],
        query: str = "",
        chunks_text: str = "",
        max_items: int = 15,
    ) -> str:
        """
        Extracts only acronym definitions relevant to current query or retrieved chunks.
        Saves tokens and prevents prompt bloat.
        """
        if not glossary:
            return ""

        hay = f"{query}\n{chunks_text}"
        used = [
            (a, f)
            for a, f in glossary.items()
            if re.search(rf"(?<![\w\-]){re.escape(a)}(?![\w\-])", hay)
        ]
        if not used:
            return ""

        lines = [f"- {a} = {f}" for a, f in used[:max_items]]
        return "--- QUY ƯỚC TỪ VIẾT TẮT TRONG TÀI LIỆU ---\n" + "\n".join(lines) + "\n-----------------------------------------"


# Global singleton instance
acronym_harvester = AcronymHarvester()
harvest_glossary = acronym_harvester.harvest
enrich_chunk_for_embedding = acronym_harvester.enrich_chunk_for_embedding
expand_query = acronym_harvester.expand_query
glossary_for_prompt = acronym_harvester.glossary_for_prompt
