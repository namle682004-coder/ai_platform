"""
Deterministic post-processing of generated answers (streaming and non-streaming alike).

All rules are structural, not lexical:
- a source list written by the model (lines "[n] <title of a cited document> …", optionally under a
  short heading ending with ':') is dropped; the system appends its own footer from citation
  metadata, so document titles are always spelled exactly as stored;
- citation markers are renumbered in order of first use and markers pointing to no passage removed;
- GitHub admonitions ("> [!IMPORTANT]"), images whose URL is not in the retrieved passages, chunk
  breadcrumbs, echoed system-prompt sentences and runs of scripts other than the answer language
  (CJK / Cyrillic code-switching artefacts) are removed;
- a model refusal (the configured refusal sentence, compared accent- and markdown-free so bold, line
  breaks or a reworded opening still match) is detected from the opening sentence, before anything is
  streamed, so the caller can replace it with an escalation reply.

`AnswerStreamFilter` streams prose as soon as a line is clearly longer than a heading and holds short
or structural lines (lists, quotes, tables, headings) until they are complete.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .answer_verifier import GroundingContext, last_safe_boundary, split_sentences
from .lexical_evidence import extract_identifiers, normalize_for_match
from .prompt_builder import IMAGE_ALIAS_PREFIX, REFUSAL_MESSAGE

# An answer sharing this many consecutive words with the prompt's instructions is disclosing the
# system prompt (prompt injection): the whole answer is withheld, not just the echoed line.
LEAK_SPAN_TOKENS = 8

_REF_LINE_RE = re.compile(r"^\s*(?:[-*>]\s*)*\[(\d{1,2})\]\s*[\(:\-–]?\s*(.*)$")
_ADMONITION_RE = re.compile(r"^\s*>\s*\[!(?:IMPORTANT|NOTE|WARNING|TIP|CAUTION)\]\s*:?\s*", re.IGNORECASE)
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]*)\)")
_BREADCRUMB_RE = re.compile(r"\s*\[(?:Ngữ cảnh|Tài liệu)\s*:[^\]\n]*\]")
_FOREIGN_RE = re.compile(
    r"[Ѐ-ӿ　-〿぀-ヿ㐀-䶿一-鿿가-힯！-｠]+[，。；：！？、]*"
)
_MARKER_RE = re.compile(r"\[(\d{1,2})\]")
# "[11].C3.MR4": a source marker that is really the first segment of an identifier.
_BRACKETED_ID_RE = re.compile(r"\[(\d{1,3})\](\.[A-Z0-9]{1,4}(?:\.[A-Z0-9]{1,4})+)\b")
# Context-block headers of prompt_builder.extract_citations_and_blocks ("(Tài liệu: …, Trang: …, Mục: …)")
# copied into the answer by the model.
_CONTEXT_HEADER_RE = re.compile(r"\s*\((?:Tài liệu|Nguồn)\s*:[^)\n]{0,300}\)")
_STRUCTURAL_START_RE = re.compile(r"^\s*(?:[#>\|!\[]|[-*+]\s|\d+[\.\)]\s|\*\*)")
_MARKDOWN_EDGES_RE = re.compile(r"^[\s#>*_\-]+|[\s*_]+$")

_SENTENCE_END_RE = re.compile(r"[.!?…](?=\s|$)|\n\s*\n")

HEADING_MAX_CHARS = 80

# The refusal sentinel compared accent-free and markdown-free: models wrap it in bold, break the line
# after the first word or reword the opening ("Hiện tại, …"), which a raw prefix test misses.
_REFUSAL_NORM = normalize_for_match(REFUSAL_MESSAGE)
_REFUSAL_TOKENS = set(_REFUSAL_NORM.split())
REFUSAL_MIN_TOKEN_OVERLAP = 0.8
REFUSAL_MAX_EXTRA_TOKENS = 4


def _opening_sentence(text: str) -> Optional[str]:
    """First sentence of `text` (normalized), or None while it is still incomplete."""
    head = (text or "").strip()
    m = _SENTENCE_END_RE.search(head)
    return normalize_for_match(head[: m.start()]) if m else None


# A reworded refusal: "<the document / text> <not / not yet> <has / mentions / provides …> <information …>"
# with nothing grounded in it. These are words of the answer's own language, not of any document.
_NO_INFO_SOURCE = tuple(normalize_for_match(w) for w in ("tài liệu", "văn bản"))
_NO_INFO_NEGATION = tuple(normalize_for_match(w) for w in ("không", "chưa"))
_NO_INFO_CLAIM = tuple(normalize_for_match(w) for w in (
    "thông tin", "đề cập", "cung cấp", "nêu", "quy định", "nhắc", "ghi",
))
NO_INFO_MAX_TOKENS = 40
_NO_INFO_CONTRAST_RE = re.compile(r" (?:{}) ".format("|".join(
    re.escape(normalize_for_match(w)) for w in ("nhưng", "tuy nhiên", "song")
)))


def is_no_information_sentence(sentence: str) -> bool:
    """
    One sentence that only says the documents do not contain the answer. A citation marker on such a
    sentence is not evidence (models cite the passage they did not find the answer in); an identifier is.
    """
    raw = _MARKER_RE.sub(" ", sentence or "").strip()
    if not raw or extract_identifiers(raw):
        return False
    norm = f" {normalize_for_match(raw)} "
    if len(norm.split()) > NO_INFO_MAX_TOKENS:
        return False
    head, *rest = _NO_INFO_CONTRAST_RE.split(norm)
    if any(r.strip() and not any(f" {w} " in f" {r} " for w in _NO_INFO_NEGATION) for r in rest):
        return False  # "… has no information on X, but Y says …": a partial answer
    return (any(f" {w} " in head for w in _NO_INFO_SOURCE)
            and any(f" {w} " in head for w in _NO_INFO_NEGATION)
            and any(f" {w} " in head for w in _NO_INFO_CLAIM))


SUBSTANTIVE_MIN_WORDS = 1


def _states_only_absence(sentence: str) -> bool:
    """
    "The document only covers A, but has no information on B": a scope remark ending in a no-information
    clause, with nothing cited. It tells the user the answer is not there, it does not answer.
    """
    raw = _MARKER_RE.sub(" ", sentence or "").strip()
    if not raw or extract_identifiers(raw):
        return False
    norm = f" {normalize_for_match(raw)} "
    if len(norm.split()) > NO_INFO_MAX_TOKENS:
        return False
    # The last clause (after "nhưng" / a comma) must itself be "<not> … <information / mention>":
    # "…ở lớp 11, lớp 10 không có yêu cầu này" answers (a fact about grade 10), it is not an absence remark.
    parts = [p for p in _NO_INFO_CONTRAST_RE.split(norm) if p.strip()]
    if len(parts) > 1:
        last = parts[-1].split()  # what follows "nhưng / tuy nhiên"
    else:
        raw_clauses = [c for c in re.split(r"[,;]", raw) if normalize_for_match(c).strip()]
        last = normalize_for_match(raw_clauses[-1]).split() if raw_clauses else []
    neg = next((i for i, w in enumerate(last) if w in _NO_INFO_NEGATION), None)
    if neg is None or not any(f" {w} " in norm for w in _NO_INFO_SOURCE):
        return False
    after = f" {' '.join(last[neg + 1:])} "
    return any(f" {w} " in after for w in _NO_INFO_CLAIM)


def is_substantive_sentence(sentence: str) -> bool:
    """A sentence that tells the user something: not a no-information remark, not markers or punctuation."""
    raw = _MARKDOWN_EDGES_RE.sub("", _MARKER_RE.sub(" ", sentence or "").replace("**", "")).strip()
    if extract_identifiers(raw):
        return True  # a code / number of the documents is an answer, however short ("11.C3.MR4 [1]")
    if len(normalize_for_match(raw).split()) < SUBSTANTIVE_MIN_WORDS:
        return False
    if normalize_for_match(raw) == normalize_for_match(PARTIAL_ANSWER_OPENING):
        return False
    return not _states_only_absence(raw)


def has_substantive_content(text: str, complete_only: bool = False) -> bool:
    """
    Some sentence of `text` answers. `complete_only`: only finished sentences count (a streamed answer
    whose next sentence may still turn out to be another no-information remark).
    """
    body = text or ""
    pos = 0
    for m in _SENTENCE_END_RE.finditer(body):
        if is_substantive_sentence(body[pos:m.end()]):
            return True
        pos = m.end()
    return not complete_only and is_substantive_sentence(body[pos:])


def _raw_opening_sentence(text: str) -> Optional[str]:
    head = (text or "").strip()
    m = _SENTENCE_END_RE.search(head)
    return head[: m.start()] if m else None


def is_llm_refusal(text: str) -> bool:
    """The answer opens with the configured refusal sentence (formatting and light rewording tolerated)."""
    first = _opening_sentence(text)
    if first is None:
        first = normalize_for_match((text or "").strip()[:300])
    if not first:
        return False
    if first.startswith(_REFUSAL_NORM):
        return True
    raw_first = _raw_opening_sentence(text)
    if raw_first is None:
        raw_first = (text or "").strip()[:300]
    if is_no_information_sentence(_MARKDOWN_EDGES_RE.sub("", raw_first.replace("**", ""))):
        return True
    tokens = first.split()
    if len(tokens) > len(_REFUSAL_NORM.split()) + REFUSAL_MAX_EXTRA_TOKENS:
        return False
    return len(_REFUSAL_TOKENS & set(tokens)) / len(_REFUSAL_TOKENS) >= REFUSAL_MIN_TOKEN_OVERLAP


def refusal_probe_ready(text: str) -> bool:
    """Enough of the answer has arrived to tell a refusal from a real answer."""
    return _opening_sentence(text) is not None or len(normalize_for_match(text)) > len(_REFUSAL_NORM) + 20


# Models often open with the refusal sentence and then answer anyway ("… chưa có thông tin… Tuy nhiên,
# X thuộc mục Y [2]."). Such a continuation is kept when it carries evidence (a citation marker or an
# identifier); the misleading opening is replaced by a neutral one.
PARTIAL_ANSWER_OPENING = "Tài liệu không có thông tin đúng như câu hỏi đặt ra."
REFUSAL_CONTINUATION_MIN_CHARS = 40


def _after_opening_sentence(text: str) -> str:
    head = (text or "").strip()
    m = _SENTENCE_END_RE.search(head)
    return head[m.end():] if m else ""


EVIDENCE_SPAN_TOKENS = 5


def _token_spans(norm: str, n: int = EVIDENCE_SPAN_TOKENS) -> Set[Tuple[str, ...]]:
    tokens = norm.split()
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def _is_evidenced_continuation(rest: str, evidence_spans: Optional[Set[Tuple[str, ...]]] = None) -> bool:
    """
    The text after a refusal opening is an answer when it cites (marker / identifier) or quotes the
    passages (a run of EVIDENCE_SPAN_TOKENS words copied from them).
    """
    norm = normalize_for_match(rest)
    if len(norm) < REFUSAL_CONTINUATION_MIN_CHARS:
        return False
    if _MARKER_RE.search(rest) or extract_identifiers(rest):
        return True
    return bool(evidence_spans) and bool(_token_spans(norm) & evidence_spans)


@dataclass
class SanitizeContext:
    titles: Sequence[str] = ()
    allowed_image_urls: Set[str] = field(default_factory=set)
    prompt_text: str = ""
    valid_indices: Set[int] = field(default_factory=set)
    renumber: bool = True  # False keeps the model's marker numbers (multi-pass synthesis)
    grounding: Optional[GroundingContext] = None  # sentence-level verification (language, identifiers, numbers)
    evidence_text: str = ""  # the passages of the prompt (a refusal followed by a quote of them is an answer)
    dropped: List[Tuple[str, str]] = field(default_factory=list)  # (problem, sentence) removed by verification
    leaked: bool = False  # the model reproduced the prompt's instructions; the answer is withheld
    image_url_mapper: Optional[Callable[[str], str]] = None  # passage image URL -> URL the browser can load


class AnswerStreamFilter:
    """Incremental sanitizer: feed raw LLM tokens, get back text that is safe to show."""

    MAX_INLINE_HOLD = 40
    MAX_UNVERIFIED_HOLD = 600  # a run-on sentence longer than this is released unverified

    def __init__(self, ctx: SanitizeContext) -> None:
        self.ctx = ctx
        self._buf = ""
        self._probed = False
        self._refusal_pending = False
        self._line_mode: Optional[str] = None  # None | "stream" | "hold"
        self._emitted_any = False
        self._pending_header: Optional[str] = None
        self._in_ref_block = False
        self.refused = False
        self.marker_map: Dict[int, int] = {}
        self.dropped: List[Tuple[str, str]] = []  # (reason, sentence) removed by verification
        self._out: List[str] = []
        self._prompt_norm = normalize_for_match(ctx.prompt_text) if ctx.prompt_text else ""
        self._evidence_spans = _token_spans(normalize_for_match(ctx.evidence_text)) if ctx.evidence_text else set()
        # Spans of the instructions a legitimate answer never contains: the refusal sentence the rules
        # prescribe and anything the passages themselves say are excluded.
        self._leak_spans: Set[Tuple[str, ...]] = set()
        if self._prompt_norm:
            self._leak_spans = _token_spans(self._prompt_norm, LEAK_SPAN_TOKENS) - _token_spans(
                _REFUSAL_NORM, LEAK_SPAN_TOKENS)
            if ctx.evidence_text:
                self._leak_spans -= _token_spans(normalize_for_match(ctx.evidence_text), LEAK_SPAN_TOKENS)
        self.leaked = False
        self._titles = [t for t in ctx.titles if t and len(t) >= 6]
        self._title_tokens = [set(normalize_for_match(t).split()) for t in self._titles]
        self._title_res = [re.compile(re.escape(t), re.IGNORECASE) for t in self._titles]

    # ---------------------------------------------------------------- public
    def feed(self, token: str) -> List[str]:
        if self.refused or not token:
            return []
        self._buf += token
        return self._drain(final=False)

    def finish(self) -> List[str]:
        if self.refused:
            return []
        out = self._drain(final=True)
        if self._pending_header is not None:
            out += self._emit(self._pending_header)
            self._pending_header = None
        return out

    @property
    def text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "".join(self._out)).strip()

    # --------------------------------------------------------------- helpers
    def _emit(self, piece: str) -> List[str]:
        if not piece:
            return []
        if not self._emitted_any:
            piece = piece.lstrip("\n ")
            if not piece:
                return []
        self._emitted_any = True
        self._out.append(piece)
        return [piece]

    def _verify(self, text: str) -> str:
        """Drops sentences in another language or citing identifiers/numbers the passages do not contain."""
        g = self.ctx.grounding
        if g is None or not text.strip():
            return text
        kept = []
        for sentence in split_sentences(text):
            problem = g.sentence_problem(sentence)
            if problem:
                self.dropped.append((problem, sentence.strip()[:120]))
                self.ctx.dropped.append((problem, sentence.strip()[:120]))
                # Keep the line structure (a dropped list item must not glue two lines together).
                if sentence.endswith("\n"):
                    kept.append("\n")
                continue
            kept.append(sentence)
        return "".join(kept)

    def _renumber(self, text: str) -> str:
        text = _BRACKETED_ID_RE.sub(r"\1\2", text)

        def repl(m: re.Match) -> str:
            orig = int(m.group(1))
            if self.ctx.valid_indices and orig not in self.ctx.valid_indices:
                return ""
            if orig not in self.marker_map:
                self.marker_map[orig] = len(self.marker_map) + 1 if self.ctx.renumber else orig
            return f"[{self.marker_map[orig]}]"

        out = _MARKER_RE.sub(repl, text)
        return re.sub(r"(\[\d+\])(?:\s*,?\s*\1)+", r"\1", out)

    def _clean_inline(self, text: str) -> str:
        text = _CONTEXT_HEADER_RE.sub("", text)
        text = _BREADCRUMB_RE.sub("", text)
        text = _FOREIGN_RE.sub("", text)
        text = _IMAGE_RE.sub(self._image_tag, text)
        for rx, title in zip(self._title_res, self._titles, strict=True):
            text = rx.sub(title, text)
        return self._renumber(text)

    def _image_tag(self, m: re.Match) -> str:
        """Images of the passages are kept (with a loadable URL); any other image the model wrote is removed."""
        url = m.group(2)
        if url.startswith(IMAGE_ALIAS_PREFIX):
            # The prompt shows images by a short alias of their file name; resolve it to the passage's URL.
            alias = url[len(IMAGE_ALIAS_PREFIX):]
            url = next((u for u in sorted(self.ctx.allowed_image_urls)
                        if re.search(rf"/{re.escape(alias)}[0-9a-f]{{8}}\.[a-z0-9]{{2,5}}$", u.split("?")[0])), "")
        if url not in self.ctx.allowed_image_urls:
            return ""
        mapper = self.ctx.image_url_mapper
        return f"![{m.group(1)}]({mapper(url)})" if mapper else m.group(0)

    def _is_ref_line(self, line: str) -> bool:
        """'[n] <cited document title>, Trang …' — a source entry written by the model."""
        m = _REF_LINE_RE.match(line)
        if not m:
            return False
        rest = set(normalize_for_match(m.group(2)).split())
        if not rest:
            return False
        return any(tokens and len(tokens & rest) / len(tokens) >= 0.6 for tokens in self._title_tokens)

    @staticmethod
    def _is_heading_like(line: str) -> bool:
        bare = _MARKDOWN_EDGES_RE.sub("", line)
        return 0 < len(bare) <= HEADING_MAX_CHARS and bare.endswith(":")

    def _is_leaked_instruction(self, line: str) -> bool:
        if not self._prompt_norm:
            return False
        norm = normalize_for_match(line)
        return len(norm) >= 40 and norm in self._prompt_norm

    def _discloses_prompt(self, text: str) -> bool:
        """True (and the whole answer withheld) when `text` reproduces a stretch of the prompt's instructions."""
        if not self._leak_spans or not text.strip():
            return False
        tokens = normalize_for_match(text).split()
        if not any(tuple(tokens[i:i + LEAK_SPAN_TOKENS]) in self._leak_spans
                   for i in range(len(tokens) - LEAK_SPAN_TOKENS + 1)):
            return False
        self.leaked = self.ctx.leaked = True
        self.refused = True
        self._buf = ""
        self._pending_header = None
        return True

    def _process_full_line(self, line: str, newline: bool) -> List[str]:
        out: List[str] = []
        stripped = line.strip()
        if self._is_ref_line(stripped):
            self._pending_header = None  # the heading belonged to the model's source list
            self._in_ref_block = True
            return out
        if self._in_ref_block and not stripped:
            return out
        self._in_ref_block = False
        if self._pending_header is not None:
            if not stripped:
                self._pending_header += "\n"
                return out
            out += self._emit(self._pending_header)
            self._pending_header = None
        if self._discloses_prompt(stripped):
            return []
        if self._is_leaked_instruction(stripped):
            return out
        line = _ADMONITION_RE.sub("**Lưu ý:** ", line)
        cleaned = self._verify(self._clean_inline(line))
        if stripped and not cleaned.strip():
            return out
        piece = cleaned + ("\n" if newline else "")
        if self._is_heading_like(stripped):
            # Wait for the next line: a heading followed by source entries is dropped with them.
            self._pending_header = piece
            return out
        return out + self._emit(piece)

    def _drain(self, final: bool) -> List[str]:
        out: List[str] = []
        if not self._probed:
            if not final and not refusal_probe_ready(self._buf):
                return out
            self._probed = True
            self._refusal_pending = is_llm_refusal(self._buf)
        if self._refusal_pending:
            # Hold everything until the continuation shows evidence (partial answer) or the stream ends.
            rest = _after_opening_sentence(self._buf)
            # Evidence alone is not an answer: "… only covers A, has no information on B [1]" cites the
            # passage it did not find the answer in. A sentence that says something is required.
            if (_is_evidenced_continuation(rest, self._evidence_spans)
                    and has_substantive_content(rest, complete_only=not final)):
                self._refusal_pending = False
                self._buf = f"{PARTIAL_ANSWER_OPENING} {rest.lstrip()}"
            elif final:
                self.refused = True
                self._buf = ""
                return out
            else:
                return out
        while self._buf:
            nl = self._buf.find("\n")
            if self._line_mode is None:
                head = self._buf if nl == -1 else self._buf[:nl]
                if nl == -1 and not final and len(head) <= HEADING_MAX_CHARS:
                    break  # could still be a heading or a source entry
                structural = bool(_STRUCTURAL_START_RE.match(head)) or not head.strip()
                self._line_mode = "hold" if (structural or nl != -1 or final) else "stream"
                if self._line_mode == "stream" and self._pending_header is not None:
                    out += self._emit(self._pending_header)
                    self._pending_header = None
            if self._line_mode == "hold":
                if nl == -1:
                    if final:
                        out += self._process_full_line(self._buf, newline=False)
                        self._buf = ""
                    break
                line, self._buf = self._buf[:nl], self._buf[nl + 1:]
                out += self._process_full_line(line, newline=True)
                self._line_mode = None
                if self.refused:
                    return out
                continue
            # Stream mode: long prose line; emit up to an unfinished "[...]" (citation marker or breadcrumb).
            segment = self._buf if nl == -1 else self._buf[:nl]
            if nl == -1 and not final:
                cut = len(segment)
                if self.ctx.grounding is not None:
                    # Verified answers stream sentence by sentence: a sentence is checked as a whole.
                    cut = last_safe_boundary(segment)
                    if not cut and len(segment) > self.MAX_UNVERIFIED_HOLD:
                        cut = len(segment)
                open_br = segment.rfind("[", 0, cut)
                if open_br != -1 and "]" not in segment[open_br:cut] and cut - open_br <= self.MAX_INLINE_HOLD:
                    cut = open_br
                if cut:
                    if self._discloses_prompt(segment[:cut]):
                        return out
                    out += self._emit(self._verify(self._clean_inline(segment[:cut])))
                self._buf = self._buf[cut:]
                break
            if self._discloses_prompt(segment):
                return out
            out += self._emit(self._verify(self._clean_inline(segment)) + ("\n" if nl != -1 else ""))
            self._buf = "" if nl == -1 else self._buf[nl + 1:]
            self._line_mode = None
        return out


def sanitize_answer(text: str, ctx: SanitizeContext) -> Tuple[str, Dict[int, int], bool]:
    """Non-streaming wrapper. Returns (clean_text, marker_map, is_refusal)."""
    f = AnswerStreamFilter(ctx)
    f.feed(text or "")
    f.finish()
    return f.text, dict(f.marker_map), f.refused


def remap_citations(citations: List[Dict[str, Any]], marker_map: Dict[int, int]) -> List[Dict[str, Any]]:
    """Keeps the cited sources only, re-indexed to the renumbered markers."""
    by_index = {int(c.get("index", 0)): c for c in citations}
    out = []
    for orig, new in sorted(marker_map.items(), key=lambda kv: kv[1]):
        c = by_index.get(orig)
        if c is None:
            continue
        item = dict(c)
        item["index"] = new
        out.append(item)
    return out


def build_sources_footer(citations: Sequence[Dict[str, Any]]) -> str:
    if not citations:
        return ""
    lines = ["", "", "**Nguồn:**"]
    for c in citations:
        heading = (c.get("heading") or "").strip()
        loc = f"Trang {c.get('page_number') or 1}"
        if heading and heading != "Thông tin văn bản":
            loc += f", Mục: {heading}"
        lines.append(f"- [{c.get('index')}] {c.get('title') or 'Tài liệu'} – {loc}")
    return "\n".join(lines)


def _table_rows(text: str) -> List[List[str]]:
    rows = []
    lines = [ln.strip() for ln in (text or "").splitlines()]
    for i, ln in enumerate(lines):
        if not (ln.startswith("|") and ln.endswith("|")):
            continue
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if nxt.startswith("|") and all(set(c.strip()) <= set("-: ") for c in nxt.strip("|").split("|")):
            continue  # header row
        if len(cells) >= 2 and cells[-1]:
            rows.append(cells)
    return rows


def build_suggestions(answer: str, ranked_chunks: Sequence[Dict[str, Any]], max_items: int = 2) -> str:
    """
    1–2 follow-up suggestions taken from real passages: table rows sharing the first column with a
    row that was answered, then rows / headings of the next-best passages that were not cited.
    The label is the right-most cell that is not just identifiers, so any table layout works.
    """
    answered = set(extract_identifiers(answer))
    answer_norm = normalize_for_match(answer)
    seen_codes: Set[str] = set(answered)
    parsed: List[Tuple[str, List[str], List[str]]] = []
    answered_groups: Set[str] = set()
    for ch in ranked_chunks:
        payload = ch.get("payload", ch) if isinstance(ch, dict) else {}
        heading = str(payload.get("heading") or "").strip()
        for cells in _table_rows(str(payload.get("text") or "")):
            codes = extract_identifiers(" ".join(cells))
            parsed.append((heading, cells, codes))
            if codes and set(codes) & answered:
                answered_groups.add(cells[0])
    same_group: List[str] = []
    others: List[str] = []
    for heading, cells, codes in parsed:
        if not codes or set(codes) & seen_codes:
            continue
        descriptive = [c for c in cells if c and not extract_identifiers(c)]
        label = descriptive[-1] if descriptive else cells[0]
        if not label or len(label) > 160 or normalize_for_match(label) in answer_norm:
            continue
        group = cells[0] if cells[0] and cells[0] != label and not extract_identifiers(cells[0]) else ""
        where = ", ".join(x for x in (heading, group) if x)
        item = f"«{label}» ({where}: {', '.join(codes)})" if where else f"«{label}» ({', '.join(codes)})"
        seen_codes.update(codes)
        (same_group if cells[0] in answered_groups else others).append(item)
    picks = (same_group + others)[:max_items]
    if not picks and not parsed:
        headings: List[str] = []
        for ch in ranked_chunks:
            payload = ch.get("payload", ch) if isinstance(ch, dict) else {}
            h = str(payload.get("heading") or "").strip()
            if h and h not in headings and h != "Thông tin văn bản" and normalize_for_match(h) not in answer_norm:
                headings.append(h)
        picks = [f"mục «{h}»" for h in headings[:max_items]]
    if not picks:
        return ""
    return "\n\n**Gợi ý tra cứu thêm:** " + "; ".join(picks) + "."


def collect_image_urls(texts: Iterable[str]) -> Set[str]:
    urls: Set[str] = set()
    for t in texts:
        for m in _IMAGE_RE.finditer(t or ""):
            if m.group(2):
                urls.add(m.group(2))
    return urls
