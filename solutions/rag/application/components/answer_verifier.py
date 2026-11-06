"""
Post-generation verification of answers against the retrieved passages (no document vocabulary).

- sentence splitting that does not cut "10.A1.1. Text" after the identifier;
- language guard: sentences written in another language than the answer language are dropped;
- grounding: identifiers and long numbers (years, document numbers) an answer sentence cites must
  occur in the passages; identifiers that only occur outside the tabulated items of a document that
  has tables are illustrative (examples of a convention) and are not valid answers;
- completeness: items of the context that match the question as well as the best one but are missing
  from the answer are listed after it;
- extractive fallback: lines of the passages that contain the asked-about terms, used when the model
  refuses although the passages contain them.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .lexical_evidence import (
    IDENTIFIER_RE,
    candidate_heading,
    candidate_text,
    extract_identifiers,
    has_vietnamese_diacritics,
    identifier_matches,
    STOPWORDS_ACCENTED,
    normalize_for_match,
    query_terms,
)
from .prompt_builder import strip_breadcrumb
from .numeric_tables import parse_numeric_tables
from .table_rows import parse_table_rows, row_items, text_items

_SENTENCE_BOUNDARY_RE = re.compile(r"[.!?…](?=\s)")
_WORD_RE = re.compile(r"[^\W\d_]+")
# A figure as written in text: "3,5k", "1.234", "12%", "50"; dates and identifiers are masked first.
_NUMBER_TOKEN_RE = re.compile(
    r"(?<![\w.,/:])([+-]?\d{1,3}(?:[.,]\d{3})+(?![.,]?\d)|\d+(?:[.,]\d+)?)(?:\s?([kKmM%‰])(?!\w))?(?![\w/]|[.,]\d)"
)
_DATE_RE = re.compile(r"(?<![\w/])\d{1,2}/\d{1,2}(?:/\d{2,4})?(?![\w/])")
# The two words that follow a figure (what is counted), not crossing punctuation.
_UNIT_WORDS_RE = re.compile(r"[ \t]*([^\W\d_]+)(?:[ \t\n]+([^\W\d_]+))?")
# Integers below this are counts/ordinals a model may legitimately produce (list positions, "3 sources").
SMALL_INTEGER_LIMIT = 10
_MARKER_RE = re.compile(r"\[\d{1,3}\]")

# English function words: a language resource used to tell an English sentence from Vietnamese text
# without diacritics (proper nouns, tool names and code lists carry none of these).
ENGLISH_FUNCTION_WORDS = frozenset(
    "the a an is are was were be been being of to and or which that this these those it its should "
    "can could would will may must how why what when where who whom with for in on at by from as "
    "than then so such students student requirement requirements specifically include includes".split()
)
OFF_LANGUAGE_MIN_WORDS = 5
OFF_LANGUAGE_FUNCTION_RATIO = 0.25


def split_sentences(text: str) -> List[str]:
    """Sentences with their trailing whitespace; a period right after an identifier is not a boundary."""
    out, start = [], 0
    for m in _SENTENCE_BOUNDARY_RE.finditer(text):
        token = text[:m.start() + 1].rsplit(None, 1)[-1] if text[:m.start() + 1].strip() else ""
        if IDENTIFIER_RE.fullmatch(token.rstrip(".")) or re.fullmatch(r"\d{1,2}\.", token):
            continue  # "10.A1.1." / "1." are item labels, not sentence ends
        end = m.end()
        while end < len(text) and text[end] in " \t":
            end += 1
        out.append(text[start:end])
        start = end
    if start < len(text):
        out.append(text[start:])
    return out


def last_safe_boundary(text: str) -> int:
    """Index after the last complete sentence of `text` (0 if none is complete yet)."""
    parts = split_sentences(text)
    if len(parts) <= 1:
        return 0
    return len(text) - len(parts[-1])


def is_english_text(text: str) -> bool:
    words = [w.lower() for w in _WORD_RE.findall(text or "")]
    if len(words) < OFF_LANGUAGE_MIN_WORDS or has_vietnamese_diacritics(text):
        return False
    return sum(1 for w in words if w in ENGLISH_FUNCTION_WORDS) / len(words) >= OFF_LANGUAGE_FUNCTION_RATIO


@dataclass
class NumberToken:
    raw: str  # as written ("3,5k", "12%", "50")
    values: Set[float]  # every plausible reading ("3,5k" -> {3500.0, 35000.0})
    checked: bool  # decimals, magnitudes, percents and integers >= SMALL_INTEGER_LIMIT must be grounded
    unit_key: str  # next two words, accent-free ("5 chủ đề ..." -> "chu de"); "" if not two words
    unit_words: str  # the same words as written


def _readings(digits: str, suffix: str) -> Set[float]:
    mult = 1000.0 if suffix in ("k", "K") else 1_000_000.0 if suffix in ("m", "M") else 1.0
    out = {float(re.sub(r"[.,+]", "", digits)) * mult}
    last = max(digits.rfind("."), digits.rfind(","))
    if last != -1:
        out.add(float(re.sub(r"[.,+]", "", digits[:last]) + "." + digits[last + 1:]) * mult)
    return {round(v, 6) for v in out}


def _mask(text: str) -> str:
    """Identifiers, dates and citation markers blanked out so their digits are not read as figures."""
    text = _MARKER_RE.sub(lambda m: " " * len(m.group(0)), text or "")
    text = IDENTIFIER_RE.sub(lambda m: " " * len(m.group(0)), text)
    return _DATE_RE.sub(lambda m: " " * len(m.group(0)), text)


def number_tokens(text: str) -> List[NumberToken]:
    masked = _mask(text)
    out: List[NumberToken] = []
    for m in _NUMBER_TOKEN_RE.finditer(masked):
        digits, suffix = m.group(1), m.group(2) or ""
        values = _readings(digits, suffix)
        checked = bool(suffix) or bool(re.search(r"[.,]", digits)) or min(values) >= SMALL_INTEGER_LIMIT
        w = _UNIT_WORDS_RE.match(masked, m.end())
        unit_key, unit_words = "", ""
        if w and w.group(2) and w.group(1).lower() not in STOPWORDS_ACCENTED:
            unit_words = f"{w.group(1)} {w.group(2)}"
            unit_key = normalize_for_match(unit_words)
        out.append(NumberToken(m.group(0).strip(), values, checked, unit_key, unit_words))
    return out


def date_tokens(text: str) -> Set[Tuple[int, ...]]:
    return {tuple(int(p) for p in d.split("/")) for d in _DATE_RE.findall(_MARKER_RE.sub(" ", text or ""))}


def _sentence_of(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind("\n", 0, start), text.rfind(";", 0, start))
    rights = [p for p in (text.find(".", end), text.find("\n", end), text.find(";", end)) if p != -1]
    right = min(rights) if rights else len(text)
    return re.sub(r"\s+", " ", text[left + 1:right]).strip()[:220]


@dataclass
class GroundingContext:
    """What an answer may state: identifiers, figures (with their units) and dates present in its passages."""

    identifiers: Set[str] = field(default_factory=set)
    example_identifiers: Set[str] = field(default_factory=set)
    values: Set[float] = field(default_factory=set)
    dates: Set[Tuple[int, ...]] = field(default_factory=set)
    unit_values: Dict[str, Set[float]] = field(default_factory=dict)
    unit_examples: Dict[str, List[str]] = field(default_factory=dict)
    question_values: Set[float] = field(default_factory=set)
    allow_examples: bool = False
    language_guard: bool = True
    check_numbers: bool = True
    check_units: bool = True

    def _known(self, values: Set[float]) -> bool:
        return bool(values & self.values) or bool(values & self.question_values)

    def sentence_problem(self, sentence: str) -> Optional[str]:
        if self.language_guard and is_english_text(_MARKER_RE.sub(" ", sentence)):
            return "language"
        for ident in extract_identifiers(sentence):
            if ident in self.example_identifiers and not self.allow_examples:
                return f"example:{ident}"
            if self.identifiers and ident not in self.identifiers and not identifier_matches(ident, self.identifiers):
                return f"identifier:{ident}"
        if not self.check_numbers or not self.values:
            return None
        for d in date_tokens(sentence):
            if self.dates and d not in self.dates and not any(d == x[: len(d)] or x == d[: len(x)] for x in self.dates):
                return "number:" + "/".join(str(p) for p in d)
        for tok in number_tokens(sentence):
            if not self._known(tok.values):
                if tok.checked:
                    return f"number:{tok.raw}"
                continue
            if (self.check_units and tok.unit_key in self.unit_values
                    and not tok.values & self.unit_values[tok.unit_key] and not tok.values & self.question_values):
                return f"unit:{tok.raw}|{tok.unit_key}|{tok.unit_words}"
        return None

    def hint(self, problem: str) -> str:
        """What the model must know to correct a dropped sentence (for the corrective regeneration)."""
        kind, _, detail = problem.partition(":")
        if kind == "unit":
            raw, key, words = (detail.split("|") + ["", ""])[:3]
            examples = "; ".join(f"«{e}»" for e in self.unit_examples.get(key, [])[:4])
            return (f"Tài liệu KHÔNG ghi «{raw} {words}». Trong tài liệu, «{words}» đi với các số "
                    f"{', '.join(_fmt(v) for v in sorted(self.unit_values.get(key, set())))}: {examples}. "
                    "Phân biệt đúng đơn vị đếm.")
        if kind == "number":
            return f"Con số «{detail}» không có trong tài liệu; không được dùng."
        if kind in ("identifier", "example"):
            return f"Mã «{detail}» không phải nội dung của tài liệu; không được dùng."
        if kind == "language":
            return "Chỉ viết tiếng Việt."
        return ""


def _fmt(v: float) -> str:
    return str(int(v)) if abs(v - round(v)) < 1e-9 else str(v)


def build_grounding(
    chunks: Sequence[Any],
    document_chunks: Sequence[Any],
    allow_examples: bool,
    language_guard: bool,
    question: str = "",
    check_units: bool = True,
) -> GroundingContext:
    texts = [candidate_text(c) for c in chunks]  # breadcrumbs included: headings carry figures too
    joined = "\n".join(texts + [candidate_heading(c) for c in chunks])
    identifiers = set(extract_identifiers(joined))
    values: Set[float] = set()
    unit_values: Dict[str, Set[float]] = {}
    unit_examples: Dict[str, List[str]] = {}
    for text in texts:
        for tok in number_tokens(text):
            values |= tok.values
        masked = _mask(text)
        for m in _NUMBER_TOKEN_RE.finditer(masked):
            tok = number_tokens(m.group(0) + masked[m.end():m.end() + 60])
            if tok and tok[0].unit_key:
                unit_values.setdefault(tok[0].unit_key, set()).update(tok[0].values)
                example = _sentence_of(text, m.start(), m.end())
                if example and example not in unit_examples.setdefault(tok[0].unit_key, []):
                    unit_examples[tok[0].unit_key].append(example)
    # Digits inside identifiers ("Level 11" in "11.C3.1") are legitimate figures too.
    for ident in identifiers:
        for part in re.findall(r"\d+", ident):
            values.add(float(part))
    # Table columns are units for their cells ("Comments" -> every comment count of the column).
    for table in parse_numeric_tables(chunks):
        for col in table.numeric_columns:
            words = _UNIT_WORDS_RE.match(" " + table.columns[col])
            if words and words.group(2):
                key = normalize_for_match(f"{words.group(1)} {words.group(2)}")
                unit_values.setdefault(key, set()).update(r.values[col] for r in table.rows if col in r.values)
    question_values: Set[float] = set()
    for tok in number_tokens(question):
        question_values |= tok.values
    # In documents whose items are tabulated, identifiers that never appear in a table row are
    # illustrations (e.g. examples explaining a numbering convention), not items of the document.
    rows = parse_table_rows(document_chunks)
    row_ids = {it.identifier for it in row_items(rows)}
    example_ids: Set[str] = set()
    if row_ids:
        all_doc_ids = set(extract_identifiers("\n".join(candidate_text(c) for c in document_chunks)))
        # Any code written in a table cell belongs to the tabulated content, item start or not.
        in_rows = set(extract_identifiers("\n".join(cell for r in rows for cell in r.cells)))
        # Only codes shaped like the tabulated items illustrate their convention ("6.A1.2" next to
        # "10.A1.2"); a code of another shape (the decision number in the header) is real content.
        row_shapes = {identifier_shape(i) for i in row_ids}
        example_ids = {i for i in all_doc_ids - row_ids - in_rows
                       if not identifier_matches(i, row_ids) and identifier_shape(i) in row_shapes}
    return GroundingContext(
        identifiers=identifiers | row_ids,
        example_identifiers=example_ids,
        values={round(v, 6) for v in values},
        dates=date_tokens(joined) | date_tokens(question),
        unit_values=unit_values,
        unit_examples=unit_examples,
        question_values=question_values,
        allow_examples=allow_examples,
        language_guard=language_guard,
        check_units=check_units,
    )


def identifier_shape(identifier: str) -> str:
    """Letters -> A, digit runs -> 9, separators kept: '10.A1.MR2' -> '9.A9.AA9', '2422/QĐ-BGDĐT' -> '9/AA-AAAAA'."""
    return re.sub(r"\d+", "9", re.sub(r"[^\W\d_]", "A", (identifier or "").upper()))


# ------------------------------------------------------------------ completeness
@dataclass
class ContextItem:
    identifier: str
    text: str
    section: str
    search_text: str
    order: Tuple[str, int, int]


def context_items(chunks: Sequence[Any]) -> List[ContextItem]:
    items: List[ContextItem] = []
    seen = set()
    for it in row_items(parse_table_rows(chunks)):
        if it.identifier in seen:
            continue
        seen.add(it.identifier)
        items.append(ContextItem(it.identifier, it.text, it.row.section, it.search_text(), (it.row.doc_id, *it.row.order)))
    for ident, line, chunk in text_items(chunks):
        if ident in seen:
            continue
        seen.add(ident)
        items.append(ContextItem(ident, line, candidate_heading(chunk), line, (str(chunk), 0, 0)))
    return items


def _distinctive_terms(query: str, focus_terms: Sequence[str], items: Sequence[ContextItem]) -> Dict[str, float]:
    unigrams, bigrams = query_terms(query)
    terms = list(dict.fromkeys([normalize_for_match(f) for f in focus_terms if normalize_for_match(f)] + bigrams + unigrams))
    texts = [f" {normalize_for_match(it.search_text)} " for it in items]
    n = len(texts)
    weights: Dict[str, float] = {}
    for t in terms:
        df = sum(1 for x in texts if f" {t} " in x)
        # Terms present everywhere (scope words, generic nouns) do not tell items apart.
        if df == 0 or df > max(2, n // 4):
            continue
        weights[t] = math.log((n + 1.0) / (df + 0.5)) * (1.3 if " " in t else 1.0)
    return weights


def missing_items(
    query: str,
    focus_terms: Sequence[str],
    answer: str,
    chunks: Sequence[Any],
    relative_score: float,
    max_items: int,
    require_anchor: bool = True,
    exclude: Iterable[str] = (),
) -> List[ContextItem]:
    """
    Items as relevant to the question as the best one that the answer does not mention.
    `exclude`: identifiers that are not content (codes a convention section shows as examples).
    """
    excluded = {i.upper() for i in exclude}
    items = [it for it in context_items(chunks) if it.identifier.upper() not in excluded]
    if len(items) < 2:
        return []
    weights = _distinctive_terms(query, focus_terms, items)
    if not weights:
        return []
    # The asked-about subject, when the items name it, is required: words of the question's phrasing
    # ("nội dung", "ghi đủ") score items too, and on a small context they look distinctive.
    subject = [t for t in (normalize_for_match(f) for f in focus_terms) if t in weights]
    scored = []
    for it in items:
        hay = f" {normalize_for_match(it.search_text)} "
        if subject and not any(f" {t} " in hay for t in subject):
            continue
        s = sum(w for t, w in weights.items() if f" {t} " in hay)
        if s > 0:
            scored.append((s, it))
    if not scored:
        return []
    best = max(s for s, _ in scored)
    relevant = [it for s, it in scored if s >= relative_score * best]
    cited = set(extract_identifiers(answer))
    if require_anchor and not cited & {it.identifier for _, it in scored}:
        return []  # the answer cites nothing on the question's topic; do not graft items onto it
    missing = [it for it in relevant if it.identifier not in cited]
    return sorted(missing, key=lambda it: it.order)[:max_items]


def format_missing(items: Sequence[ContextItem]) -> str:
    if not items:
        return ""
    lines = ["", "", "Ngoài ra, tài liệu còn có:"]
    for it in items:
        lines.append(f"- {it.text}" + (f" ({it.section})" if it.section else ""))
    return "\n".join(lines)


# ------------------------------------------------------------------ extractive fallback
def focus_present(focus_terms: Sequence[str], chunks: Sequence[Any]) -> bool:
    terms = [normalize_for_match(t) for t in focus_terms if len(normalize_for_match(t)) >= 2]
    if not terms:
        return False
    hay = " ".join(f" {normalize_for_match(candidate_text(c))} " for c in chunks)
    return any(f" {t} " in hay for t in terms)


def extractive_answer(focus_terms: Sequence[str], chunks: Sequence[Any], max_lines: int = 5) -> str:
    """Passage lines (items first) that contain the asked-about terms, with their section."""
    terms = [normalize_for_match(t) for t in focus_terms if len(normalize_for_match(t)) >= 2]
    if not terms:
        return ""
    picked: List[str] = []
    for it in context_items(chunks):
        hay = f" {normalize_for_match(it.search_text)} "
        if any(f" {t} " in hay for t in terms):
            picked.append(f"- {it.text}" + (f" ({it.section})" if it.section else ""))
        if len(picked) >= max_lines:
            break
    if not picked:
        for c in chunks:
            for line in strip_breadcrumb(candidate_text(c)).splitlines():
                s = line.strip(" |-*")
                if s and any(f" {t} " in f" {normalize_for_match(s)} " for t in terms):
                    picked.append(f"- {s}" + (f" ({candidate_heading(c)})" if candidate_heading(c) else ""))
                if len(picked) >= max_lines:
                    break
    if not picked:
        return ""
    shown = ", ".join(f"«{t}»" for t in focus_terms[:3])
    return f"Tài liệu đề cập {shown} tại:\n" + "\n".join(picked)


SPECIFIC_TERM_MAX_SHARE = 0.5


def specific_focus_terms(
    focus_terms: Sequence[str], scope_terms: Sequence[str], titles: Sequence[str], chunks: Sequence[Any]
) -> List[str]:
    """
    The asked-about terms that single out passages: not a scope word, not words of a document title
    (the whole document is about them) and not present in most of the passages (e.g. the subject of
    the corpus). That such a term occurs in the passages says the answer may be there; that a generic
    one occurs says nothing.
    """
    scopes = {normalize_for_match(s) for s in scope_terms}
    title_tokens = [set(normalize_for_match(t).split()) for t in titles if t]
    texts = [f" {normalize_for_match(candidate_text(c))} " for c in chunks]
    out = []
    for term in focus_terms:
        norm = normalize_for_match(term)
        if len(norm) < 2 or norm in scopes:
            continue
        tokens = set(norm.split())
        if any(tokens <= tt for tt in title_tokens):
            continue
        if len(texts) >= 3 and sum(1 for t in texts if f" {norm} " in t) / len(texts) > SPECIFIC_TERM_MAX_SHARE:
            continue
        out.append(term)
    return out


def focus_locations(focus_terms: Sequence[str], scope_terms: Sequence[str], chunks: Sequence[Any]) -> Tuple[List[str], bool]:
    """(sections where the focus appears, whether any of them matches the user's scope)."""
    terms = [normalize_for_match(t) for t in focus_terms if len(normalize_for_match(t)) >= 2]
    scopes = [normalize_for_match(s) for s in scope_terms if normalize_for_match(s)]
    sections: List[str] = []
    in_scope = False
    for c in chunks:
        text = f" {normalize_for_match(candidate_text(c))} "
        if not any(f" {t} " in text for t in terms):
            continue
        heading = candidate_heading(c) or ""
        if heading and heading not in sections:
            sections.append(heading)
        if scopes and any(f" {s} " in f" {normalize_for_match(heading)} " or f" {s} " in text for s in scopes):
            in_scope = True
    return sections, in_scope


def unique(items: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(i for i in items if i))
