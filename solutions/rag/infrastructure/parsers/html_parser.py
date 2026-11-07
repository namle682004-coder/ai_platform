"""
HTML document parser (pages of internal websites read by the web connector, or uploaded .html files).

The page becomes Markdown: headings keep their level, lists become bullets, tables go through the shared
table renderer (colspan / rowspan resolved, multi-level headers flattened, captions separated) so they are
stored and queried like tables of any other format. Scripts, styles, navigation and footers are dropped.
Standard library only.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urldefrag

from ...domain.entities import ParsedDocument, ParsedPage
from ...domain.exceptions import DocumentParsingError
from .base import BaseDocumentParser
from .table_grid import GridCell, clean, render_table

SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "nav", "footer", "iframe", "form", "button", "select"}
BLOCK_TAGS = {"p", "div", "section", "article", "main", "header", "aside", "blockquote", "pre", "dl", "dt", "dd",
              "figure", "figcaption", "address", "hr"}
HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}


class _Table:
    def __init__(self) -> None:
        self.rows: List[List[Tuple[str, int, int]]] = []  # (text, colspan, rowspan)
        self.caption = ""

    def grid(self, table_id: int) -> List[List[GridCell]]:
        """Expand spans: every grid position of a spanning cell gets its text and a shared key."""
        grid: Dict[Tuple[int, int], GridCell] = {}
        for r, row in enumerate(self.rows):
            c = 0
            for k, (text, colspan, rowspan) in enumerate(row):
                while (r, c) in grid:
                    c += 1
                key = (table_id, r, k) if colspan > 1 or rowspan > 1 else None
                for dr in range(rowspan):
                    for dc in range(colspan):
                        grid[(r + dr, c + dc)] = GridCell(text, key)
                c += colspan
        if not grid:
            return []
        n_rows = max(r for r, _ in grid) + 1
        n_cols = max(c for _, c in grid) + 1
        return [[grid.get((r, c), GridCell("")) for c in range(n_cols)] for r in range(n_rows)]


class _HtmlToMarkdown(HTMLParser):
    def __init__(self, base_url: str = "") -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.blocks: List[str] = []
        self.buf: List[str] = []
        self.title = ""
        self.links: List[str] = []
        self._skip = 0
        self._in_title = False
        self._heading: Optional[int] = None
        self._list_depth = 0
        self._tables: List[_Table] = []
        self._cell: Optional[List[str]] = None
        self._cell_span = (1, 1)
        self._in_caption = False
        self._caption_buf: List[str] = []
        self._table_count = 0

    # -- helpers
    def _flush(self) -> None:
        text = clean(" ".join(self.buf)).replace("\\|", "|")
        self.buf = []
        if not text:
            return
        if self._heading:
            self.blocks.append(f"{'#' * self._heading} {text}")
        elif self._list_depth:
            self.blocks.append(f"{'  ' * (self._list_depth - 1)}- {text}")
        else:
            self.blocks.append(text)

    def _target(self) -> List[str]:
        if self._in_caption and self._tables:
            return self._caption_buf
        return self._cell if self._cell is not None else self.buf

    # -- parser events
    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        a = dict(attrs)
        if tag in SKIP_TAGS:
            self._skip += 1
            return
        if self._skip:
            return
        if tag == "title":
            self._in_title = True
        elif tag == "a" and a.get("href"):
            href = urldefrag(urljoin(self.base_url, a["href"].strip()))[0]
            if href.startswith(("http://", "https://")):
                self.links.append(href)
        elif tag == "table":
            if self._cell is None:
                self._flush()
            self._tables.append(_Table())
        elif tag == "caption" and self._tables:
            self._in_caption, self._caption_buf = True, []
        elif tag == "tr" and self._tables:
            self._tables[-1].rows.append([])
        elif tag in ("td", "th") and self._tables:
            def span(name: str) -> int:
                try:
                    return max(1, min(50, int(a.get(name) or 1)))
                except ValueError:
                    return 1
            self._cell, self._cell_span = [], (span("colspan"), span("rowspan"))
        elif tag == "br":
            self._target().append(" ")
        elif tag in HEADINGS and self._cell is None:
            self._flush()
            self._heading = HEADINGS[tag]
        elif tag in ("ul", "ol") and self._cell is None:
            self._flush()
            self._list_depth += 1
        elif tag == "li" and self._cell is None:
            self._flush()
        elif tag in BLOCK_TAGS and self._cell is None:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if tag == "title":
            self._in_title = False
        elif tag == "caption" and self._tables:
            self._tables[-1].caption = clean(" ".join(self._caption_buf))
            self._in_caption = False
        elif tag in ("td", "th") and self._tables and self._cell is not None:
            if not self._tables[-1].rows:
                self._tables[-1].rows.append([])
            colspan, rowspan = self._cell_span
            self._tables[-1].rows[-1].append((clean(" ".join(self._cell)), colspan, rowspan))
            self._cell = None
        elif tag == "table" and self._tables:
            table = self._tables.pop()
            self._table_count += 1
            md = render_table(table.grid(self._table_count))
            if md:
                if table.caption:
                    md = f"**{table.caption}**\n\n{md}"
                if self._tables and self._cell is not None:  # nested table: its text stays in the outer cell
                    self._cell.append(" ".join(line.strip("| ") for line in md.splitlines() if "---" not in line))
                else:
                    self.blocks.append(md)
        elif tag in HEADINGS and self._heading:
            self._flush()
            self._heading = None
        elif tag in ("ul", "ol") and self._list_depth and self._cell is None:
            self._flush()
            self._list_depth -= 1
        elif (tag in BLOCK_TAGS or tag == "li") and self._cell is None:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._in_title:
            self.title += data
            return
        self._target().append(data)

    def markdown(self) -> str:
        self._flush()
        return "\n\n".join(b for b in self.blocks if b.strip())


def html_to_markdown(html: str, base_url: str = "") -> Tuple[str, str, List[str]]:
    """(title, markdown, absolute links) of an HTML page."""
    parser = _HtmlToMarkdown(base_url)
    parser.feed(html)
    parser.close()
    title = clean(parser.title).replace("\\|", "|")
    md = parser.markdown()
    if not title:
        m = re.search(r"^# (.+)$", md, re.MULTILINE)
        title = m.group(1).strip() if m else ""
    return title, md, list(dict.fromkeys(parser.links))


def decode_html(raw: bytes) -> str:
    head = raw[:2048].decode("ascii", errors="ignore")
    m = re.search(r"charset=[\"']?([\w-]+)", head, re.IGNORECASE)
    for enc in ([m.group(1)] if m else []) + ["utf-8", "cp1258", "latin-1"]:
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


class HtmlDocumentParser(BaseDocumentParser):
    def parse(self, file_bytes: bytes, filename: str) -> ParsedDocument:
        try:
            title, md, links = html_to_markdown(decode_html(file_bytes))
        except Exception as exc:  # noqa: BLE001
            raise DocumentParsingError(f"HTML parsing failed: {exc}") from exc
        text = f"# {title}\n\n{md}" if title and not md.startswith("# ") else md
        return ParsedDocument(filename=filename, file_type="html", pages=[ParsedPage(page_number=1, text=text)],
                              metadata={"total_pages": 1, "title": title, "links": len(links)})
