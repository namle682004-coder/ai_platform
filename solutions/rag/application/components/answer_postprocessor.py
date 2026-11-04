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
- a model refusal (the configured refusal sentence) is detected from the first characters, before
  anything is streamed, so the caller can replace it with an escalation reply.

`AnswerStreamFilter` streams prose as soon as a line is clearly longer than a heading and holds short
or structural lines (lists, quotes, tables, headings) until they are complete.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .lexical_evidence import extract_identifiers, normalize_for_match
from .prompt_builder import REFUSAL_MESSAGE

_REF_LINE_RE = re.compile(r"^\s*(?:[-*>]\s*)*\[(\d{1,2})\]\s*[\(:\-–]?\s*(.*)$")
_ADMONITION_RE = re.compile(r"^\s*>\s*\[!(?:IMPORTANT|NOTE|WARNING|TIP|CAUTION)\]\s*:?\s*", re.IGNORECASE)
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]*)\)")
_BREADCRUMB_RE = re.compile(r"\s*\[(?:Ngữ cảnh|Tài liệu)\s*:[^\]\n]*\]")
_FOREIGN_RE = re.compile(
    r"[Ѐ-ӿ　-〿぀-ヿ㐀-䶿一-鿿가-힯！-｠]+[，。；：！？、]*"
)
_MARKER_RE = re.compile(r"\[(\d{1,2})\]")
_STRUCTURAL_START_RE = re.compile(r"^\s*(?:[#>\|!\[]|[-*+]\s|\d+[\.\)]\s|\*\*)")
_MARKDOWN_EDGES_RE = re.compile(r"^[\s#>*_\-]+|[\s*_]+$")

HEADING_MAX_CHARS = 80


def is_llm_refusal(text: str) -> bool:
    head = (text or "").strip()[:200]
    return bool(head) and head.startswith(REFUSAL_MESSAGE[:40])


@dataclass
class SanitizeContext:
    titles: Sequence[str] = ()
    allowed_image_urls: Set[str] = field(default_factory=set)
    prompt_text: str = ""
    valid_indices: Set[int] = field(default_factory=set)
    renumber: bool = True  # False keeps the model's marker numbers (multi-pass synthesis)


class AnswerStreamFilter:
    """Incremental sanitizer: feed raw LLM tokens, get back text that is safe to show."""

    PROBE_CHARS = 48
    MAX_INLINE_HOLD = 40

    def __init__(self, ctx: SanitizeContext) -> None:
        self.ctx = ctx
        self._buf = ""
        self._probed = False
        self._line_mode: Optional[str] = None  # None | "stream" | "hold"
        self._emitted_any = False
        self._pending_header: Optional[str] = None
        self._in_ref_block = False
        self.refused = False
        self.marker_map: Dict[int, int] = {}
        self._out: List[str] = []
        self._prompt_norm = normalize_for_match(ctx.prompt_text) if ctx.prompt_text else ""
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

    def _renumber(self, text: str) -> str:
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
        text = _BREADCRUMB_RE.sub("", text)
        text = _FOREIGN_RE.sub("", text)
        text = _IMAGE_RE.sub(lambda m: m.group(0) if m.group(2) in self.ctx.allowed_image_urls else "", text)
        for rx, title in zip(self._title_res, self._titles, strict=True):
            text = rx.sub(title, text)
        return self._renumber(text)

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
        if self._is_leaked_instruction(stripped):
            return out
        line = _ADMONITION_RE.sub("**Lưu ý:** ", line)
        cleaned = self._clean_inline(line)
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
            if len(self._buf.strip()) < self.PROBE_CHARS and not final:
                return out
            self._probed = True
            if is_llm_refusal(self._buf):
                self.refused = True
                self._buf = ""
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
                continue
            # Stream mode: long prose line; emit up to an unfinished "[...]" (citation marker or breadcrumb).
            segment = self._buf if nl == -1 else self._buf[:nl]
            if nl == -1 and not final:
                cut = len(segment)
                open_br = segment.rfind("[")
                if open_br != -1 and "]" not in segment[open_br:] and len(segment) - open_br <= self.MAX_INLINE_HOLD:
                    cut = open_br
                if cut:
                    out += self._emit(self._clean_inline(segment[:cut]))
                self._buf = self._buf[cut:]
                break
            out += self._emit(self._clean_inline(segment) + ("\n" if nl != -1 else ""))
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
