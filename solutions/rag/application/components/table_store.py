"""
Structured tables of a document, extracted once at ingestion.

Retrieval returns passages; a question that counts, filters or lists rows of a table ("which posts are
neutral", "which positions require level 4") needs every row of every relevant table, whatever retrieval
returned and however many documents hold such a table. At ingestion each Markdown table of the parsed
document (as rendered by the parsers' shared table renderer, so every column has a real name) is stored
whole: document, section path, caption, column names and rows. `table_query` then answers those questions in
code over the stored rows.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .lexical_evidence import normalize_for_match

_DELIMITER = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_BOLD_LINE = re.compile(r"^\*\*(.+?)\*\*\s*$")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)


@dataclass
class TableRecord:
    doc_id: str
    title: str  # document title
    section: str  # heading path in the document ("Chương II > Điều 7"), or the sheet
    caption: str  # the table's own title line, if any ("BẢNG 1: …")
    columns: List[str]
    rows: List[List[str]]
    page: int = 1
    index: int = 0  # order of the table in the document
    total_rows: List[int] = field(default_factory=list)  # rows that are sums of the others (detected arithmetically)

    @property
    def signature(self) -> str:
        """Same column names = same kind of table (one per document of a template)."""
        return "|".join(normalize_for_match(c) for c in self.columns)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["signature"] = self.signature
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TableRecord":
        keys = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in d.items() if k in keys})


def split_cells(line: str) -> List[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [_BR.sub(" ", c).replace("\\|", "|").strip() for c in re.split(r"(?<!\\)\|", body)]


def parse_number(cell: str) -> Optional[float]:
    s = (cell or "").strip().replace(" ", "")
    if not s or not re.fullmatch(r"[-+]?[\d.,]+%?", s):
        return None
    s = s.rstrip("%")
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    elif s.count(".") > 1 or (s.count(".") == 1 and len(s.split(".")[1]) == 3 and s.count(",") == 0):
        s = s.replace(".", "")
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


MAX_MERGED_LABEL_CHARS = 60


def merged_heads(rows: Sequence[Sequence[str]], indices: Sequence[int], target: int) -> List[int]:
    """
    One row per merged cell of the target column. A figure merged down over several rows sits beside a label
    merged over the same rows (the source beside its post count): the rows are cut into segments of constant
    label, and a label column qualifies when the figure is constant inside every segment and at least one
    segment spans several rows. Each segment then counts once. Long text repeated on neighbouring rows
    (identical notes) is not a label; neighbouring labels with equal figures ("2" and "2") stay separate.
    Returns `indices` unchanged when no column qualifies.
    """
    def segments(c: int) -> List[List[int]]:
        out: List[List[int]] = []
        for r in indices:
            if out and r == out[-1][-1] + 1 and rows[r][c] == rows[out[-1][0]][c]:
                out[-1].append(r)
            else:
                out.append([r])
        return out

    width = min((len(rows[r]) for r in indices), default=0)
    for c in range(width):
        if c == target:
            continue
        labels = [rows[r][c] for r in indices]
        if any(not v or parse_number(v) is not None or len(v) > MAX_MERGED_LABEL_CHARS for v in labels):
            continue
        segs = segments(c)
        if any(len(s) > 1 for s in segs) and all(len({rows[r][target] for r in s}) == 1 for s in segs):
            return [s[0] for s in segs]
    return list(indices)


def total_rows(rows: Sequence[Sequence[str]]) -> List[int]:
    """
    Rows that sum the others, found arithmetically (never by a word such as "Tổng"): in the numeric columns,
    the row's figure equals the sum of the rows above it since the previous total more often than not.
    A column of merged cells (a value repeated on each row it spans) does not add up and does not count.
    """
    found: List[int] = []
    start = 0
    # A total row carries a label at most, not the descriptive text of a data row: rows with as many text
    # cells as a typical row are data even when a small figure happens to equal the sum above it.
    text_counts = sorted(sum(1 for c in r if c.strip() and parse_number(c) is None) for r in rows)
    typical_text = text_counts[len(text_counts) // 2] if text_counts else 0
    for i, row in enumerate(rows):
        if typical_text >= 2 and sum(1 for c in row if c.strip() and parse_number(c) is None) >= typical_text:
            continue
        # With one text cell per row (label + figures) there is no such signal: more evidence is required.
        min_figures = 2 if typical_text >= 2 else 3
        hits = misses = 0
        for c, cell in enumerate(row):
            v = parse_number(cell)
            if v is None:
                continue
            span = [k for k in range(start, i) if k not in found and c < len(rows[k]) and parse_number(rows[k][c]) is not None]
            figures = [parse_number(rows[k][c]) for k in span]
            if len(figures) < min_figures:
                continue
            # A column of merged cells adds up once per merge (each source's post count), not once per row.
            heads = merged_heads(rows, span, c) if span else []
            merged_sum = sum(parse_number(rows[k][c]) for k in heads)
            if abs(sum(figures) - v) < 1e-6 or (len(heads) < len(span) and abs(merged_sum - v) < 1e-6):
                hits += 1
            else:
                misses += 1
        if hits >= 1 and hits >= misses:
            found.append(i)
            start = i + 1
    return found


def extract_tables(pages: Sequence[Any], doc_id: str, title: str) -> List[TableRecord]:
    """Every Markdown table of the parsed pages with its section path and caption."""
    out: List[TableRecord] = []
    stack: List[Tuple[int, str]] = []
    caption = ""
    for page in pages:
        lines = (getattr(page, "text", "") or "").splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            heading = _MD_HEADING.match(line)
            bold = _BOLD_LINE.match(line)
            if heading:
                level, text = len(heading.group(1)), heading.group(2).strip()
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, text))
                caption = ""
            elif bold:
                caption = bold.group(1).strip()
            elif line.startswith("|") and i + 1 < len(lines) and _DELIMITER.match(lines[i + 1].strip()):
                columns = split_cells(line)
                j, rows = i + 2, []
                while j < len(lines) and lines[j].strip().startswith("|"):
                    cells = split_cells(lines[j])
                    rows.append((cells + [""] * len(columns))[: len(columns)])
                    j += 1
                if rows:
                    out.append(TableRecord(
                        doc_id=doc_id, title=title, section=" > ".join(t for _, t in stack), caption=caption,
                        columns=columns, rows=rows, page=int(getattr(page, "page_number", 1) or 1),
                        index=len(out), total_rows=total_rows(rows),
                    ))
                caption = ""
                i = j
                continue
            elif line and not _IMAGE.fullmatch(line):
                caption = ""  # a caption is the line right before its table
            i += 1
    return out


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text or "")
