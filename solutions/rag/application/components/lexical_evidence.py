"""
Lexical Evidence Scoring for the RAG confidence gate.

The cross-encoder alone is a poor refusal signal for Vietnamese: it scores short questions against
long table chunks very low even when the chunk contains the asked keyword verbatim. This module
measures how much of the query's *salient* vocabulary is literally present in each retrieved
candidate, accent- and i/y-insensitively, with IDF weights computed over the candidate set itself,
so words present in every passage count for little and rare words count for a lot. Nothing here
depends on a particular document: all statistics come from the retrieved passages.

It also extracts identifiers (any token mixing letters and digits joined by '.', '/' or '-') so the
gate can say "that identifier is not in the documents" instead of letting the LLM invent content,
and restores diacritics of unaccented queries from the vocabulary of the retrieved passages.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

_WORD_RE = re.compile(r"\w+", re.UNICODE)

# Generic identifiers: segments of letters/digits joined by '.', '/' or '-', containing at least one
# letter and one digit (document numbers, codes, versions). Pure numbers ("2.1.3") and plain hyphenated
# words are not identifiers.
IDENTIFIER_RE = re.compile(
    r"(?<![\w./\-])((?=[\w./\-]*\d)(?=[\w./\-]*[^\W\d_])[^\W_]+(?:[./\-][^\W_]+)+)(?![\w])"
)
_ID_SEPARATORS_RE = re.compile(r"[./\-]")

# Vietnamese function words and question scaffolding, matched on the accented lowercase token so
# that "văn bản" / "mã" are not mistaken for "vẫn" / "bạn" / "mà" once accents are stripped.
STOPWORDS_ACCENTED: Set[str] = {
    "là", "và", "các", "của", "trong", "có", "được", "đã", "những", "cho", "về", "này", "đó", "với",
    "khi", "để", "một", "thì", "sẽ", "ở", "tại", "ra", "lại", "theo", "nào", "gì", "từ", "làm", "thế",
    "cần", "sau", "như", "rằng", "bởi", "nhiều", "mỗi", "không", "chưa", "hay", "hoặc", "mà", "nếu",
    "vậy", "sao", "đâu", "bao", "mấy", "tôi", "mình", "bạn", "em", "anh", "chị", "ạ", "à", "nhé",
    "nha", "giúp", "xin", "hỏi", "biết", "kể", "liệt", "tên", "đúng", "phải", "khác", "nhau", "thuộc",
    "cái", "kia", "ấy", "đây", "dưới", "trên", "còn", "thực", "sự", "hiện", "gồm", "tất", "cả", "toàn",
    "bộ", "đều", "vào", "lên", "xuống", "rất", "quá", "hơn", "nhất", "cũng", "vẫn", "chỉ", "mới", "lúc",
    "bằng", "đến", "nên", "vì", "nhưng", "thôi", "thật", "hãy", "nêu", "ghi", "rõ", "đủ",
    "of", "the", "and", "is", "in", "to", "for", "with", "an", "on", "at", "what", "which", "how",
}
# Unaccented forms that are unambiguous function words when the user types without diacritics.
STOPWORDS_UNACCENTED: Set[str] = {
    "la", "va", "cac", "cua", "trong", "co", "duoc", "da", "nhung", "cho", "ve", "nay", "do", "voi",
    "khi", "de", "mot", "thi", "se", "o", "tai", "ra", "lai", "theo", "nao", "gi", "tu", "lam", "can",
    "sau", "nhu", "rang", "boi", "nhieu", "moi", "khong", "chua", "hay", "hoac", "neu", "vay", "sao",
    "dau", "bao", "may", "toi", "minh", "em", "nhe", "nha", "giup", "xin", "hoi", "biet", "ke", "liet",
    "cai", "kia", "ay", "day", "gom", "deu", "vao", "rat", "qua", "hon", "nhat", "cung", "hai",
}
# Kept for callers that only have accent-stripped tokens.
STOPWORDS: Set[str] = STOPWORDS_UNACCENTED

_Y_TO_I_RE = re.compile(r"(?<=[bcdghklmnpqrstvx])y\b")


def strip_diacritics(text: str) -> str:
    if not text:
        return ""
    res = text.replace("đ", "d").replace("Đ", "D")
    nfd = unicodedata.normalize("NFD", res)
    return unicodedata.normalize("NFC", "".join(c for c in nfd if unicodedata.category(c) != "Mn"))


def normalize_for_match(text: str) -> str:
    """Lowercase, accent-free, i/y-unified ("kỹ" == "kĩ"), punctuation collapsed to spaces."""
    if not text:
        return ""
    base = strip_diacritics(text.lower())
    base = _Y_TO_I_RE.sub("i", base)
    # Keep hyphenated compounds matchable both joined and split ("nơ-ron" ~ "no ron").
    return " ".join(_WORD_RE.findall(base.replace("-", " ")))


def has_vietnamese_diacritics(text: str) -> bool:
    return strip_diacritics(text) != text


def extract_identifiers(text: str) -> List[str]:
    """Identifiers in `text`, upper-cased and de-duplicated in order."""
    seen: Dict[str, None] = {}
    for m in IDENTIFIER_RE.findall(text or ""):
        seen.setdefault(m.upper().rstrip(".-/"), None)
    return list(seen.keys())


def identifier_matches(query_id: str, doc_ids: Iterable[str]) -> List[str]:
    """
    Document identifiers equal to `query_id` or ending with it after a separator, so a user who types
    only the trailing segments of an identifier still matches every identifier it could refer to.
    """
    q = query_id.upper()
    out = []
    for d in doc_ids:
        if d == q or (d.endswith(q) and _ID_SEPARATORS_RE.match(d[-len(q) - 1])):
            out.append(d)
    return out


def query_terms(query: str) -> Tuple[List[str], List[str]]:
    """Returns (unigrams, bigrams) of the normalized query without stopwords."""
    raw = _WORD_RE.findall((query or "").lower().replace("-", " "))
    tokens: List[Tuple[str, bool]] = []
    for tok in raw:
        norm = normalize_for_match(tok)
        if not norm:
            continue
        is_stop = tok in STOPWORDS_ACCENTED or (not has_vietnamese_diacritics(tok) and norm in STOPWORDS_UNACCENTED)
        tokens.append((norm, is_stop))
    unigrams = [t for t, stop in tokens if not stop and (len(t) >= 2 or t.isdigit())]
    bigrams = []
    for (a, a_stop), (b, b_stop) in zip(tokens, tokens[1:], strict=False):
        # Phrases are built from adjacent content words only; "được học", "ở đâu" carry no topic.
        if a_stop or b_stop or (a.isdigit() and b.isdigit()):
            continue
        bigrams.append(f"{a} {b}")
    return list(dict.fromkeys(unigrams)), list(dict.fromkeys(bigrams))


def candidate_text(c: Any) -> str:
    if isinstance(c, dict):
        payload = c.get("payload") or {}
        return str(payload.get("text") or c.get("text") or "")
    return str(getattr(c, "text", "") or "")


def candidate_heading(c: Any) -> str:
    if isinstance(c, dict):
        payload = c.get("payload") or {}
        return str(payload.get("heading_path") or payload.get("heading") or "")
    meta = getattr(c, "metadata", {}) or {}
    return str(meta.get("heading_path") or meta.get("heading") or "")


@dataclass
class CandidateEvidence:
    index: int
    coverage: float  # IDF-weighted share of salient query terms present in this candidate
    matched_terms: List[str] = field(default_factory=list)
    identifier_hits: List[str] = field(default_factory=list)


@dataclass
class EvidenceReport:
    per_candidate: List[CandidateEvidence]
    best_coverage: float
    union_coverage: float
    query_identifiers: List[str]
    missing_identifiers: List[str]
    found_identifiers: List[str]
    salient_terms: List[str]

    def coverage_of(self, idx: int) -> float:
        if 0 <= idx < len(self.per_candidate):
            return self.per_candidate[idx].coverage
        return 0.0


def _padded(text: str) -> str:
    return f" {text} "


def score_evidence(query: str, candidates: Sequence[Any]) -> EvidenceReport:
    """
    IDF-weighted lexical coverage of the query by each candidate.

    Bigrams are matched as contiguous phrases, unigrams as whole tokens. A term absent from every
    candidate keeps the maximum IDF, so a query whose distinctive words are missing from the
    retrieved passages scores low even when generic words match everywhere.
    """
    unigrams, bigrams = query_terms(query)
    norm_texts = [_padded(normalize_for_match(candidate_text(c) + " " + candidate_heading(c))) for c in candidates]
    cand_ids = [extract_identifiers(candidate_text(c)) for c in candidates]
    n = max(1, len(candidates))

    terms = [(t, False) for t in unigrams] + [(b, True) for b in bigrams]
    df: Dict[str, int] = {}
    for term, _ in terms:
        needle = _padded(term)
        df[term] = sum(1 for t in norm_texts if needle in t)

    def idf(term: str) -> float:
        # Smoothed IDF; generic terms present in (almost) every candidate tend to ~0.
        return max(0.0, math.log((n + 1.0) / (df[term] + 0.5)))

    weights = {term: idf(term) * (1.25 if is_bigram else 1.0) for term, is_bigram in terms}
    total = sum(weights.values())

    q_ids = extract_identifiers(query)

    per: List[CandidateEvidence] = []
    union_hits: Set[str] = set()
    found_ids: Set[str] = set()
    for i, nt in enumerate(norm_texts):
        hits = [term for term, _ in terms if _padded(term) in nt]
        union_hits.update(hits)
        cov = (sum(weights[h] for h in hits) / total) if total > 0 else 0.0
        id_hits = [qid for qid in q_ids if identifier_matches(qid, cand_ids[i])]
        found_ids.update(id_hits)
        if id_hits:
            cov = max(cov, 0.9)
        per.append(CandidateEvidence(index=i, coverage=round(cov, 4), matched_terms=hits, identifier_hits=id_hits))

    union_cov = (sum(weights[h] for h in union_hits) / total) if total > 0 else 0.0
    best = max((p.coverage for p in per), default=0.0)
    salient = [t for t, _ in sorted(weights.items(), key=lambda kv: kv[1], reverse=True) if weights[t] > 0.3]
    all_q_ids = q_ids
    return EvidenceReport(
        per_candidate=per,
        best_coverage=round(best, 4),
        union_coverage=round(union_cov, 4),
        query_identifiers=all_q_ids,
        missing_identifiers=[q for q in all_q_ids if q not in found_ids],
        found_identifiers=[q for q in all_q_ids if q in found_ids],
        salient_terms=salient,
    )


def absent_numeric_details(query: str, candidates: Sequence[Any]) -> List[str]:
    """
    Numeric details of the question (years, article numbers, levels, quantities) whose number never occurs
    in the retrieved passages, returned as the original wording around them.
    They signal a premise the documents do not support ("theo quy định năm X" when no document mentions X).
    Identifiers are excluded: the identifier gate handles them.
    """
    words = (query or "").split()
    if not words or not candidates:
        return []
    norm_texts = [_padded(normalize_for_match(candidate_text(c) + " " + candidate_heading(c))) for c in candidates]
    details: List[str] = []
    for i, word in enumerate(words):
        number = normalize_for_match(word)
        if not any(ch.isdigit() for ch in number) or extract_identifiers(word):
            continue
        # The number itself anywhere in the passages (whatever its neighbours) means it is not a missing premise.
        if any(_padded(number) in t for t in norm_texts):
            continue
        details.append(" ".join(words[max(0, i - 1):i + 2]).strip(" ?.,!;:"))
    return unique_in_order(details)


def restore_diacritics_from_corpus(query: str, texts: Iterable[str]) -> str:
    """
    Re-accents an unaccented query using the vocabulary of the retrieved passages.

    Each unaccented query word takes the most frequent accented form found in the passages
    ("huong dan" -> "hướng dẫn" when the passages contain it). Bigrams are preferred over unigrams so that ambiguous
    syllables take the accent of the phrase they belong to. Tokens that already carry diacritics,
    and tokens with no corpus match, are left unchanged.
    """
    if not query:
        return query

    def key_of(word: str) -> str:
        return _Y_TO_I_RE.sub("i", strip_diacritics(word.lower()))

    uni: Dict[str, Dict[str, int]] = {}
    bi: Dict[str, Dict[str, int]] = {}
    for text in texts:
        src = (text or "").lower()
        matches = list(_WORD_RE.finditer(src))
        for m in matches:
            t = m.group(0)
            uni.setdefault(key_of(t), {}).setdefault(t, 0)
            uni[key_of(t)][t] += 1
        for m1, m2 in zip(matches, matches[1:], strict=False):
            # Only words separated by plain whitespace or a hyphen form a phrase ("a].[b" does not).
            if src[m1.end():m2.start()].strip(" -\t") != "":
                continue
            a, b = m1.group(0), m2.group(0)
            key = f"{key_of(a)} {key_of(b)}"
            bi.setdefault(key, {}).setdefault(f"{a} {b}", 0)
            bi[key][f"{a} {b}"] += 1

    def best(forms: Dict[str, int]) -> str:
        return max(forms.items(), key=lambda kv: kv[1])[0]

    def fuzzy_bigram(key: str) -> Optional[str]:
        # One-character typos inside a phrase, corrected only towards phrases that exist in the passages.
        a, b = key.split(" ", 1)
        hits = [
            k for k in bi
            if abs(len(k) - len(key)) <= 1 and k[:1] == key[:1] and _edit_distance_le1(k, key)
            and (k.split(" ", 1)[0] == a or k.split(" ", 1)[1] == b)
        ]
        if not hits:
            return None
        return best(max((bi[k] for k in hits), key=lambda forms: sum(forms.values())))

    parts = re.split(r"(\w+)", query)
    words_idx = [i for i, p in enumerate(parts) if p and _WORD_RE.fullmatch(p)]
    replaced: Dict[int, str] = {}
    for a_i, b_i in zip(words_idx, words_idx[1:], strict=False):
        if parts[a_i + 1].strip() not in ("", "-"):
            continue
        a, b = parts[a_i], parts[b_i]
        if has_vietnamese_diacritics(a) or has_vietnamese_diacritics(b):
            continue
        key = f"{key_of(a)} {key_of(b)}"
        form = best(bi[key]) if key in bi else (fuzzy_bigram(key) if len(key) >= 7 else None)
        if form:
            fa, fb = form.split(" ", 1)
            replaced.setdefault(a_i, fa)
            replaced.setdefault(b_i, fb)
    for i in words_idx:
        if i in replaced:
            continue
        w = parts[i]
        if has_vietnamese_diacritics(w) or (w.isupper() and len(w) > 1):
            continue
        forms = uni.get(key_of(w))
        if forms:
            replaced[i] = best(forms)
        elif len(w) >= 5 and not w.isdigit():
            near = [k for k in uni if abs(len(k) - len(w)) <= 1 and k[:1] == w[:1].lower() and _edit_distance_le1(k, key_of(w))]
            if near:
                replaced[i] = best(max((uni[k] for k in near), key=lambda forms: sum(forms.values())))
    for i, form in replaced.items():
        orig = parts[i]
        parts[i] = form[:1].upper() + form[1:] if orig[:1].isupper() else form
    return "".join(parts)


def find_codes_with_prefix(prefix: str, texts: Iterable[str]) -> List[str]:
    """All identifiers in `texts` starting with `prefix`, in first-seen order."""
    out: Dict[str, None] = {}
    up = prefix.upper()
    for t in texts:
        for code in extract_identifiers(t):
            if code.startswith(up):
                out.setdefault(code, None)
    return list(out.keys())


def nearest_existing_codes(missing: str, texts: Sequence[str]) -> Tuple[str, List[str]]:
    """
    For an identifier absent from the documents, returns the longest prefix (cut at a separator) that
    does exist together with the identifiers under it, e.g. 'X.Y.9' -> ('X.Y', ['X.Y.1', 'X.Y.2']).
    When even the first two segments are unknown, returns that prefix with an empty list.
    """
    up = missing.upper()
    cuts = [m.start() for m in _ID_SEPARATORS_RE.finditer(up)]
    for pos in reversed(cuts[1:]):
        scope = up[:pos]
        codes = [c for c in find_codes_with_prefix(scope, texts) if len(c) > len(scope) and _ID_SEPARATORS_RE.match(c[len(scope)])]
        if codes:
            return scope, codes
    scope = up[: cuts[1]] if len(cuts) > 1 else up
    return scope, []


def _edit_distance_le1(a: str, b: str) -> bool:
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la > lb:
        a, b, la, lb = b, a, lb, la
    i = j = edits = 0
    while i < la and j < lb:
        if a[i] == b[j]:
            i += 1
            j += 1
            continue
        edits += 1
        if edits > 1:
            return False
        if la == lb:
            i += 1
        j += 1
    return edits + (lb - j) + (la - i) <= 1


def unique_in_order(items: Iterable[Optional[str]]) -> List[str]:
    seen: Dict[str, None] = {}
    for i in items:
        if i:
            seen.setdefault(i, None)
    return list(seen.keys())
