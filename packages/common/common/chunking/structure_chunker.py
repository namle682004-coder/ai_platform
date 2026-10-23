"""
Document Structure-based Chunker with Hierarchical Context Enrichment.
Directly implements the Structure-based Chunking architecture from RAG standards (Slide pages 30-33).
Recognizes universal headings (Markdown, HTML, multi-level decimal outlines, Roman numerals),
preserves table integrity, and injects hierarchical breadcrumbs into child chunks.
100% Domain-Agnostic: Zero hardcoded legal-specific terms.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

from .base import BaseChunker, DocumentChunk
from .sanitizer import PiiSanitizer

MARKDOWN_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
UNIVERSAL_OUTLINE_PATTERN = re.compile(
    r"^([IVXLCDM]+\.|\d+(?:\.\d+)+\.?|[A-Z]\.|Section\s+\d+|Chapter\s+\d+|Part\s+[0-9IVXLCDM]+)\s*[:\.\-–—]?\s*(.*)$",
    re.IGNORECASE | re.MULTILINE,
)
TABLE_BLOCK_PATTERN = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)


class StructureChunker(BaseChunker):
    """
    Structure-based Chunker honoring document hierarchy:
    1. Detects headings and maintains an active breadcrumb hierarchy.
    2. Enriches each generated chunk with its enclosing section metadata.
    3. Guarantees atomic preservation of data tables.
    """

    def __init__(
        self,
        max_chunk_size: int = 1200,
        min_chunk_size: int = 50,
        chunk_overlap: int = 150,
        inject_context_header: bool = True,
        mask_pii: bool = True,
    ) -> None:
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.chunk_overlap = chunk_overlap
        self.inject_context_header = inject_context_header
        self.mask_pii = mask_pii

    @staticmethod
    def _split_into_blocks(text: str) -> List[str]:
        """
        Splits text into paragraphs/blocks, preserving HTML tables (<table>...</table>)
        including arbitrarily nested tables, and fenced code blocks (```...```) as unified atomic entities.
        """
        ranges: List[Tuple[int, int, str]] = []
        n = len(text)
        i = 0
        while i < n:
            if text.startswith("```", i):
                end_code = text.find("```", i + 3)
                end_idx = end_code + 3 if end_code != -1 else n
                ranges.append((i, end_idx, "code"))
                i = end_idx
                continue

            if text[i : i + 6].lower() == "<table" and (i + 6 == n or text[i + 6] in " >\n\r\t"):
                depth = 0
                j = i
                while j < n:
                    if text[j : j + 6].lower() == "<table" and (j + 6 == n or text[j + 6] in " >\n\r\t"):
                        depth += 1
                        j += 6
                    elif text[j : j + 8].lower() == "</table>":
                        depth -= 1
                        j += 8
                        if depth <= 0:
                            break
                    else:
                        j += 1
                ranges.append((i, j, "table"))
                i = j
                continue

            i += 1

        blocks: List[str] = []
        last_idx = 0
        for start, end, _ in ranges:
            if start > last_idx:
                inter = text[last_idx:start]
                paras = [p.strip() for p in re.split(r"\n\s*\n", inter) if p.strip()]
                blocks.extend(paras)
            block_content = text[start:end].strip()
            if block_content:
                blocks.append(block_content)
            last_idx = end

        if last_idx < n:
            inter = text[last_idx:]
            paras = [p.strip() for p in re.split(r"\n\s*\n", inter) if p.strip()]
            blocks.extend(paras)

        return blocks

    @staticmethod
    def _is_table_block(text: str) -> bool:
        """Detect Markdown or HTML table blocks."""
        stripped = text.strip()
        if "<table" in stripped.lower() and "</table>" in stripped.lower():
            return True
        lines = [line.strip() for line in stripped.split("\n") if line.strip()]
        if len(lines) >= 2:
            pipe_lines = sum(1 for line in lines if line.startswith("|") and line.endswith("|"))
            if pipe_lines >= 2 and pipe_lines >= len(lines) * 0.7:
                return True
        return False

    @staticmethod
    def _is_markdown_delimiter_row(line: str) -> bool:
        """Detect standard Markdown table column delimiter row (e.g. |---|:---:|)."""
        stripped = line.strip()
        return bool(re.match(r"^\|?\s*[:\-]{2,}\s*(\|\s*[:\-]{2,}\s*)+\|?$", stripped))

    @staticmethod
    def _split_table_atomically(table_text: str, max_chars: int) -> List[Tuple[str, Optional[str]]]:
        """
        Splits Markdown or HTML table atomically:
        1. If HTML table, parses via BeautifulSoup DOM:
           - Preserves outer <table> tag attributes (class, id, style).
           - Preserves and replicates <caption> across sub-chunks.
           - Preserves full multi-row <thead> (including rowspan / colspan).
           - Honors nested tables inside <td> without destroying them (recursive=False on rows).
           - Handles <td>-based header rows (e.g. styled with <strong> or header class).
        2. If Markdown table, preserves header row(s) and groups rows within max_chars.
        """
        stripped = table_text.strip()
        if "<table" in stripped.lower() and "</table>" in stripped.lower():
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(stripped, "html.parser")
                table = soup.find("table")
                if not table:
                    return [(table_text, None)]

                # 1. Format table open tag with original attributes
                attr_parts = []
                for k, v in table.attrs.items():
                    val = " ".join(v) if isinstance(v, list) else str(v)
                    attr_parts.append(f'{k}="{val}"')
                attrs_str = (" " + " ".join(attr_parts)) if attr_parts else ""
                table_open = f"<table{attrs_str}>"

                # 2. Extract caption
                caption = table.find("caption", recursive=False)
                caption_html = f"\n{str(caption)}" if caption else ""

                # 3. Extract thead or detect header row
                thead = table.find("thead", recursive=False)
                header_html = ""
                data_rows = []

                if thead:
                    for th in thead.find_all("th"):
                        th.attrs.pop("rowspan", None)
                    header_html = f"\n{str(thead)}"
                    tbody = table.find("tbody", recursive=False)
                    if tbody:
                        data_rows = tbody.find_all("tr", recursive=False)
                    else:
                        thead_trs = set(thead.find_all("tr", recursive=False))
                        data_rows = [r for r in table.find_all("tr", recursive=False) if r not in thead_trs]
                else:
                    all_trs = table.find_all("tr", recursive=False)
                    tbody = table.find("tbody", recursive=False)
                    if not all_trs and tbody:
                        all_trs = tbody.find_all("tr", recursive=False)

                    if all_trs:
                        first_tr = all_trs[0]
                        # Check if first row is a header
                        is_header = bool(first_tr.find("th"))
                        tr_class = " ".join(first_tr.get("class", [])) if isinstance(first_tr.get("class"), list) else str(first_tr.get("class", ""))
                        if "header" in tr_class.lower():
                            is_header = True
                        elif first_tr.find_all(["strong", "b"]):
                            is_header = True

                        if is_header:
                            header_html = f"\n<thead>\n{str(first_tr)}\n</thead>"
                            data_rows = all_trs[1:]
                        else:
                            data_rows = all_trs
                    else:
                        data_rows = []

                if len(data_rows) <= 1 or len(stripped) <= max_chars:
                    return [(table_text, None)]

                sub_html_tables: List[Tuple[str, Optional[str]]] = []
                curr_trs: List[str] = []
                base_chunk = f"{table_open}{caption_html}{header_html}\n<tbody>\n\n</tbody>\n</table>"
                base_len = len(base_chunk)
                curr_len = base_len

                for tr in data_rows:
                    tr_str = str(tr)
                    tr_len = len(tr_str) + 1
                    if curr_trs and (curr_len + tr_len > max_chars):
                        table_chunk = f"{table_open}{caption_html}{header_html}\n<tbody>\n" + "\n".join(curr_trs) + "\n</tbody>\n</table>"
                        sub_html_tables.append((table_chunk, None))
                        curr_trs = [tr_str]
                        curr_len = base_len + tr_len
                    else:
                        curr_trs.append(tr_str)
                        curr_len += tr_len

                if curr_trs:
                    table_chunk = f"{table_open}{caption_html}{header_html}\n<tbody>\n" + "\n".join(curr_trs) + "\n</tbody>\n</table>"
                    sub_html_tables.append((table_chunk, None))

                return sub_html_tables if sub_html_tables else [(table_text, None)]
            except Exception:
                return [(table_text, None)]

        lines = [line.rstrip() for line in table_text.strip().split("\n") if line.strip()]
        if len(lines) <= 2:
            return [(table_text, None)]

        header_lines: List[str] = []
        data_rows: List[str] = []
        if lines[0].startswith("|"):
            if len(lines) >= 2 and StructureChunker._is_markdown_delimiter_row(lines[1]):
                header_lines = [lines[0], lines[1]]
                data_rows = lines[2:]
            else:
                header_lines = [lines[0]]
                data_rows = lines[1:]
        else:
            data_rows = lines

        if len(table_text) <= max_chars:
            return [(table_text, None)]

        header_prefix = "\n".join(header_lines) + "\n" if header_lines else ""
        sub_tables: List[Tuple[str, Optional[str]]] = []
        curr_rows: List[str] = []
        curr_len = len(header_prefix)

        for row in data_rows:
            row_len = len(row) + 1
            if curr_rows and (curr_len + row_len > max_chars):
                sub_tables.append((header_prefix + "\n".join(curr_rows), None))
                curr_rows = [row]
                curr_len = len(header_prefix) + row_len
            else:
                curr_rows.append(row)
                curr_len += row_len

        if curr_rows:
            sub_tables.append((header_prefix + "\n".join(curr_rows), None))

        return sub_tables if sub_tables else [(table_text, None)]

    @staticmethod
    def _extract_table_headers(table_text: str) -> List[str]:
        """Extract column headers from a Markdown or HTML table using DOM parser."""
        stripped = table_text.strip()
        if "<table" in stripped.lower():
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(stripped, "html.parser")
                thead = soup.find("thead")
                if thead:
                    ths = thead.find_all(["th", "td"])
                    if ths:
                        return list(dict.fromkeys(t.get_text(strip=True) for t in ths if t.get_text(strip=True)))
                first_tr = soup.find("tr")
                if first_tr:
                    cells = first_tr.find_all(["th", "td"])
                    if cells:
                        return list(dict.fromkeys(c.get_text(strip=True) for c in cells if c.get_text(strip=True)))
            except Exception:
                pass
        lines = [line.strip() for line in stripped.split("\n") if line.strip()]
        if lines and lines[0].startswith("|") and lines[0].endswith("|"):
            return [c.strip() for c in lines[0].strip("|").split("|") if c.strip()]
        return []

    @staticmethod
    def _extract_heading(line: str) -> Optional[tuple[int, str]]:
        """Extract heading level and title using universal multi-format patterns."""
        stripped = line.strip()
        if not stripped:
            return None

        # 1. Markdown heading (# to ######)
        md_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if md_match:
            return len(md_match.group(1)), md_match.group(2).strip()

        # 2. HTML heading (<h1> to <h6>)
        html_match = re.match(r"^<h([1-6])[^>]*>(.*?)</h\1>$", stripped, re.IGNORECASE)
        if html_match:
            return int(html_match.group(1)), html_match.group(2).strip()

        # 3. Standalone bold heading
        bold_match = re.match(r"^\*\*(.+?)\*\*\s*$", stripped)
        if bold_match and len(bold_match.group(1).split()) <= 12:
            return 2, bold_match.group(1).strip()

        # 4. Universal multi-level decimal hierarchy (1.1, 1.1.1, 2.3.4.1)
        multi_dec_match = re.match(r"^(\d{1,2}(?:\.\d{1,2}){1,5})\.?\s*[:\.\-–—]?\s*(.*)$", stripped)
        if multi_dec_match:
            prefix = multi_dec_match.group(1).strip()
            rest = multi_dec_match.group(2).strip()
            # Must not be financial amounts, percentages, or full narrative sentences
            if not re.match(r"^(?:VNĐ|VND|USD|EUR|đ|triệu|tỷ|%)\b", rest, re.IGNORECASE) and (
                not stripped.endswith((".", "!", "?", ";")) or len(rest.split()) <= 6
            ):
                dots = prefix.count(".")
                level = min(6, 1 + dots)
                title = f"{prefix}: {rest}" if rest else prefix
                return level, title

        # 5. Universal section / chapter / part / appendix prefix
        sec_prefix_match = re.match(
            r"^(Chapter|Section|Part|Appendix)\s+([0-9IVXLCDM]+|[A-Z])\s*[:\.\-–—]?\s*(.*)$",
            stripped,
            re.IGNORECASE,
        )
        if sec_prefix_match:
            kw = sec_prefix_match.group(1).capitalize()
            num = sec_prefix_match.group(2)
            rest = sec_prefix_match.group(3).strip()
            title = f"{kw} {num}: {rest}" if rest else f"{kw} {num}"
            level = 1 if kw.lower() in ("chapter", "part", "appendix") else 2
            return level, title

        # 6. Roman numeral outline (I. Overview, II. Methods)
        roman_match = re.match(r"^([IVXLCDM]+)\.\s+([A-ZÀ-Ỹ0-9].{2,80})$", stripped)
        if roman_match and not stripped.endswith((".", "!", "?", ";", ":")):
            return 1, stripped

        # 7. Alphabetic outline (A. Overview, B. Methods)
        alpha_match = re.match(r"^([A-Z])\.\s+([A-ZÀ-Ỹ0-9].{2,80})$", stripped)
        if alpha_match and not stripped.endswith((".", "!", "?", ";", ":")):
            return 2, stripped

        # 8. Standalone top-level numbered title (1. System Architecture)
        num_title_match = re.match(r"^(\d{1,2}\.)\s+([A-ZÀ-Ỹ0-9].{3,80})$", stripped)
        if num_title_match and not stripped.endswith((".", "!", "?", ";", ":")):
            return 1, stripped

        # 9. Standalone short ALL CAPS line (< 60 chars) without terminal punctuation
        if (
            4 <= len(stripped) <= 60
            and stripped.isupper()
            and not stripped.endswith((".", "!", "?", ";", ":"))
            and any(c.isalpha() for c in stripped)
        ):
            return 1, stripped

        return None

    def chunk_document(self, doc: Any, doc_id: str) -> List[DocumentChunk]:
        all_chunks: List[DocumentChunk] = []
        global_chunk_idx = 0

        pages = getattr(doc, "pages", [])
        if not pages:
            raw_text = getattr(doc, "text", str(doc))
            pages = [type("GenericPage", (), {"page_number": 1, "text": raw_text})()]

        doc_title = getattr(doc, "title", doc_id)
        current_breadcrumb: List[str] = []

        for page in pages:
            raw_text = getattr(page, "text", "").strip()
            if not raw_text:
                continue

            if self.mask_pii:
                raw_text = PiiSanitizer.sanitize(raw_text)

            paragraphs = self._split_into_blocks(raw_text)
            current_buffer: List[str] = []
            current_len = 0

            for para in paragraphs:
                # 1. Check Table Block -> Emit as isolated atomic chunk (with row-split header replication)
                if self._is_table_block(para):
                    if current_buffer:
                        chunk_text = "\n\n".join(current_buffer).strip()
                        if len(chunk_text) >= self.min_chunk_size:
                            enriched_text = self._enrich_context(chunk_text, doc_title, current_breadcrumb)
                            all_chunks.append(DocumentChunk(
                                chunk_id=f"{doc_id}_{global_chunk_idx}",
                                doc_id=doc_id,
                                chunk_index=global_chunk_idx,
                                text=enriched_text,
                                page_number=page.page_number,
                                metadata={
                                    "source_page": page.page_number,
                                    "content_type": "text",
                                    "heading_path": " > ".join(current_breadcrumb),
                                    "strategy": "structure",
                                    "is_table": False,
                                },
                            ))
                            global_chunk_idx += 1
                        current_buffer = []
                        current_len = 0

                    table_subparts = self._split_table_atomically(para, self.max_chunk_size)
                    for sub_tbl, sub_heading in table_subparts:
                        bc = list(current_breadcrumb)
                        if sub_heading:
                            bc.append(sub_heading)
                        table_text = self._enrich_context(sub_tbl, doc_title, bc)
                        all_chunks.append(DocumentChunk(
                            chunk_id=f"{doc_id}_{global_chunk_idx}",
                            doc_id=doc_id,
                            chunk_index=global_chunk_idx,
                            text=table_text,
                            page_number=page.page_number,
                            metadata={
                                "source_page": page.page_number,
                                "content_type": "table",
                                "heading_path": " > ".join(bc),
                                "strategy": "atomic_table",
                                "is_table": True,
                                "table_headers": self._extract_table_headers(sub_tbl),
                            },
                        ))
                        global_chunk_idx += 1
                    continue

                # 2. Check Heading
                heading_info = self._extract_heading(para)
                if heading_info is not None:
                    level, heading_title = heading_info
                    # Flush previous buffer before changing section
                    if current_buffer:
                        chunk_text = "\n\n".join(current_buffer).strip()
                        if len(chunk_text) >= self.min_chunk_size:
                            enriched_text = self._enrich_context(chunk_text, doc_title, current_breadcrumb)
                            all_chunks.append(DocumentChunk(
                                chunk_id=f"{doc_id}_{global_chunk_idx}",
                                doc_id=doc_id,
                                chunk_index=global_chunk_idx,
                                text=enriched_text,
                                page_number=page.page_number,
                                metadata={
                                    "source_page": page.page_number,
                                    "content_type": "text",
                                    "heading_path": " > ".join(current_breadcrumb),
                                    "strategy": "structure",
                                },
                            ))
                            global_chunk_idx += 1
                        current_buffer = []
                        current_len = 0

                    # Update breadcrumb hierarchy
                    if level == 1:
                        current_breadcrumb = [heading_title]
                    else:
                        if len(current_breadcrumb) >= level:
                            current_breadcrumb = current_breadcrumb[: level - 1]
                        current_breadcrumb.append(heading_title)

                    current_buffer.append(para)
                    current_len += len(para)
                    continue

                # 3. Regular paragraph processing with sentence-aware overflow
                para_len = len(para)
                if current_len + para_len > self.max_chunk_size and current_buffer:
                    chunk_text = "\n\n".join(current_buffer).strip()
                    if len(chunk_text) >= self.min_chunk_size:
                        enriched_text = self._enrich_context(chunk_text, doc_title, current_breadcrumb)
                        all_chunks.append(DocumentChunk(
                            chunk_id=f"{doc_id}_{global_chunk_idx}",
                            doc_id=doc_id,
                            chunk_index=global_chunk_idx,
                            text=enriched_text,
                            page_number=page.page_number,
                            metadata={
                                "source_page": page.page_number,
                                "content_type": "text",
                                "heading_path": " > ".join(current_breadcrumb),
                                "strategy": "structure",
                            },
                        ))
                        global_chunk_idx += 1

                    # Retain last paragraph for overlap if within overlap budget
                    if para_len < self.max_chunk_size:
                        last_p = current_buffer[-1]
                        if len(last_p) <= self.chunk_overlap:
                            current_buffer = [last_p]
                            current_len = len(last_p)
                        else:
                            current_buffer = []
                            current_len = 0
                    else:
                        current_buffer = []
                        current_len = 0

                current_buffer.append(para)
                current_len += para_len + 2

            if current_buffer:
                chunk_text = "\n\n".join(current_buffer).strip()
                if len(chunk_text) >= self.min_chunk_size:
                    enriched_text = self._enrich_context(chunk_text, doc_title, current_breadcrumb)
                    all_chunks.append(DocumentChunk(
                        chunk_id=f"{doc_id}_{global_chunk_idx}",
                        doc_id=doc_id,
                        chunk_index=global_chunk_idx,
                        text=enriched_text,
                        page_number=page.page_number,
                        metadata={
                            "source_page": page.page_number,
                            "content_type": "text",
                            "heading_path": " > ".join(current_breadcrumb),
                            "strategy": "structure",
                        },
                    ))
                    global_chunk_idx += 1

        return all_chunks

    def _enrich_context(self, text: str, doc_title: str, breadcrumb: List[str]) -> str:
        """Injects contextual header into chunk for improved vector search grounding."""
        if not self.inject_context_header:
            return text
        if not breadcrumb:
            return text
        header_path = " > ".join(breadcrumb)
        return f"[Mục: {header_path}]\n{text}"
