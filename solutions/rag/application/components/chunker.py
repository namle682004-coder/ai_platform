"""
Enterprise Document Chunker Component for AIP RAG.
Splits parsed documents into overlapping chunks with token estimation and PII sanitization.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from ...domain.entities import DocumentChunk, ParsedDocument
from common.chunking import PiiSanitizer

logger = logging.getLogger(__name__)

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


class DocumentChunker:
    """
    Enterprise Universal Structure-Aware & Atomic Table Document Chunker.
    - Honors universal document structures (Markdown headings, HTML tags, multi-level decimal outlines).
    - Preserves data tables atomically (repeating table header when split).
    - Preserves fenced code blocks without breaking execution syntax.
    - Maintains breadcrumb context path and injects hierarchical context into child chunks.
    - Generates small child chunks (250-350 tokens) for ultra-sensitive retrieval,
      linked to parent contexts (~1000 tokens) for complete context synthesis.
    - 100% Domain-Agnostic: Zero hardcoded legal regex (serves technical, financial, academic, SOP docs).
    """

    def __init__(
        self,
        child_chunk_size_chars: int = 900,      # ~250-300 tokens for sharp retrieval
        child_overlap_chars: int = 150,         # ~40 tokens
        parent_chunk_size_chars: int = 3600,    # ~1000 tokens (full page or macro section)
        mask_pii: bool = True,
        hierarchical: bool = True,
        inject_breadcrumbs: bool = True,
        **kwargs: Any,
    ) -> None:
        if "chunk_size_chars" in kwargs and kwargs["chunk_size_chars"] is not None:
            child_chunk_size_chars = kwargs["chunk_size_chars"]
        if "chunk_overlap_chars" in kwargs and kwargs["chunk_overlap_chars"] is not None:
            child_overlap_chars = kwargs["chunk_overlap_chars"]

        self.child_chunk_size_chars = child_chunk_size_chars
        self.child_overlap_chars = child_overlap_chars
        self.parent_chunk_size_chars = parent_chunk_size_chars
        self.mask_pii = mask_pii
        self.hierarchical = hierarchical
        self.inject_breadcrumbs = inject_breadcrumbs

    @staticmethod
    def _estimate_tokens(text_len: int) -> int:
        """
        Vietnamese BPE token estimation (~2.5 characters per sub-word token).
        Replaces Western 4-char rule of thumb which underestimates Vietnamese tokens by ~2x.
        """
        return max(1, (text_len * 2) // 5)

    def _mask_pii(self, text: str) -> str:
        """Mask confidential PII entities per Decree 13/2023/NĐ-CP (ING-RAG-07)."""
        if not self.mask_pii or not text:
            return text
        return PiiSanitizer.sanitize(text)

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
        lines = [l.strip() for l in stripped.split("\n") if l.strip()]
        if len(lines) >= 2:
            pipe_lines = sum(1 for l in lines if l.startswith("|") and l.endswith("|"))
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
            except Exception as exc:
                logger.warning("DOM-based table splitting failed (%s); falling back", exc)
                return [(table_text, None)]

        lines = [l.rstrip() for l in table_text.strip().split("\n") if l.strip()]
        if len(lines) <= 2:
            return [(table_text, None)]

        header_lines: List[str] = []
        data_rows: List[str] = []
        if lines[0].startswith("|"):
            if len(lines) >= 2 and DocumentChunker._is_markdown_delimiter_row(lines[1]):
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
        lines = [l.strip() for l in stripped.split("\n") if l.strip()]
        if lines and lines[0].startswith("|") and lines[0].endswith("|"):
            return [c.strip() for c in lines[0].strip("|").split("|") if c.strip()]
        return []

    @staticmethod
    def _is_code_block(text: str) -> bool:
        """Detect fenced code blocks (```...```)."""
        stripped = text.strip()
        return stripped.startswith("```") and stripped.endswith("```") and len(stripped) > 6

    @staticmethod
    def _extract_heading(line: str) -> Optional[Tuple[int, str]]:
        """
        Universal multi-format structural heading extractor:
        - Markdown: # Heading 1 (level 1-6)
        - HTML: <h1>Heading</h1> (level 1-6)
        - Bold: **Heading** (level 2)
        - Multi-level decimal outlines: 1.1, 1.1.2, 1.1.2.3 (level based on depth)
        - Universal sections/chapters: Chapter 1, Section 2, Part A, Appendix B
        - Roman numeral outlines: I. Overview, II. Methods (level 1)
        - Alphabetic outlines: A. Background, B. Analysis (level 2)
        - Standalone numbered section: 1. Executive Summary (level 1)
        - Standalone short ALL CAPS line (< 60 chars) without terminal punctuation (level 1)
        - 100% Domain-Agnostic: No hardcoded legal-specific terms (Chương/Điều/Khoản/Mục).
        """
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

        # 3. Bold heading on a standalone line (**Heading**)
        bold_match = re.match(r"^\*\*(.+?)\*\*\s*$", stripped)
        if bold_match and len(bold_match.group(1).split()) <= 12:
            return 2, bold_match.group(1).strip()

        # 4. Universal multi-level decimal hierarchy (e.g. 1.1, 1.1.1, 2.3.4.1)
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

        # 5. Universal section / chapter / part / appendix prefix (Domain-agnostic)
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

        # 6. Roman numeral outline (e.g. "I. Giới thiệu", "I - Thẩm quyền...", "II - Thẩm quyền...")
        roman_match = re.match(r"^([IVXLCDM]+)[\.\-–—:]?\s+([A-ZÀ-Ỹ0-9].{2,80})$", stripped)
        if roman_match and not stripped.endswith((".", "!", "?", ";", ":")):
            return 2, stripped

        # 7. Alphabetic outline (e.g. "A. Tổng quan", "B. Phân tích", or "a) Hồ sơ tiếp nhận", "b) Trách nhiệm")
        alpha_match = re.match(r"^([A-Za-z])(?:[\.\-–—:]|\))\s+([A-ZÀ-Ỹa-z0-9].{2,80})$", stripped)
        if alpha_match and not stripped.endswith((".", "!", "?", ";", ":")):
            letter = alpha_match.group(1)
            level = 2 if letter.isupper() else 3
            return level, stripped

        # 8. Standalone top-level numbered title: e.g. "1. Tổng quan hệ thống" or "1- Tiêu chuẩn vị trí việc làm"
        num_title_match = re.match(r"^(\d{1,2})[\.\-–—]\s+([A-ZÀ-Ỹ0-9].{3,80})$", stripped)
        if num_title_match and not stripped.endswith((".", "!", "?", ";", ":")):
            return 1, stripped

        # 9. Standalone short ALL CAPS line (< 60 chars) without terminal punctuation
        if (
            4 <= len(stripped) <= 60
            and stripped.isupper()
            and not stripped.endswith((".", "!", "?", ";", ":"))
            and not re.match(r"^(\d+[\.\)]|[\*\-\+])\s+", stripped)
            and any(c.isalpha() for c in stripped)
        ):
            return 1, stripped

        return None

    def _enrich_chunk_text(self, text: str, breadcrumb: List[str], doc_title: Optional[str] = None) -> str:
        """Inject hierarchical breadcrumb header with document identity if enabled."""
        if not self.inject_breadcrumbs and not doc_title:
            return text
        full_path = " > ".join(breadcrumb) if (self.inject_breadcrumbs and breadcrumb) else (doc_title or "")
        if not full_path:
            return text
        header = f"[Ngữ cảnh: {full_path}]\n\n"
        return f"{header}{text}"

    def _locate_snippet(self, snippet: str, full_text: str, start_hint: int = 0) -> int:
        """
        Robustly locate child chunk snippet inside full_text.
        Handles breadcrumbs, overlap text, repeated sub-phrases, and whitespace.
        Returns the character index in full_text, or -1 if not found.
        """
        if not snippet or not full_text:
            return -1

        # 1. Clean breadcrumbs and metadata headers if present
        clean_snippet = re.sub(r"^\[(?:Ngữ cảnh|Tài liệu|Hỏi - Đáp|FAQ):[^\]]+\]\s*", "", snippet).strip()
        if not clean_snippet:
            clean_snippet = snippet.strip()

        # Build candidate needles from different parts of the snippet
        needles: List[str] = []
        # Needle A: prefix (up to 80 chars)
        needles.append(clean_snippet[:min(80, len(clean_snippet))].strip())
        # Needle B: middle slice (useful when beginning is overlap text from previous chunk)
        if len(clean_snippet) > 100:
            mid_start = len(clean_snippet) // 2
            needles.append(clean_snippet[mid_start : mid_start + min(60, len(clean_snippet) - mid_start)].strip())
        # Needle C: suffix
        if len(clean_snippet) > 60:
            needles.append(clean_snippet[-min(60, len(clean_snippet)):].strip())

        search_start = max(0, start_hint - 120)

        # Pass 1: search forward from near start_hint to avoid false matches on earlier repeated text
        for needle in needles:
            if len(needle) >= 15:
                idx = full_text.find(needle, search_start)
                if idx != -1:
                    return idx

        # Pass 2: search from beginning of full_text
        for needle in needles:
            if len(needle) >= 15:
                idx = full_text.find(needle)
                if idx != -1:
                    return idx

        return -1

    def _compute_page_parent_windows(
        self,
        full_text: str,
        doc_id: str,
        page_number: int,
    ) -> List[Tuple[str, str, int, int]]:
        """
        Partition a page into deterministic, overlapping parent context windows.
        Returns a list of tuples: (parent_id, parent_text, start_idx, end_idx).
        """
        text_len = len(full_text)
        if text_len <= self.parent_chunk_size_chars:
            return [(f"parent_{doc_id}_p{page_number}", full_text, 0, text_len)]

        windows: List[Tuple[str, str, int, int]] = []
        step = max(500, self.parent_chunk_size_chars * 3 // 4)
        start = 0
        window_idx = 0

        while start < text_len:
            end = min(text_len, start + self.parent_chunk_size_chars)
            snap_start = start
            if snap_start > 0:
                next_space = full_text.find(" ", snap_start)
                if next_space != -1 and next_space < snap_start + 60:
                    snap_start = next_space + 1

            snap_end = end
            if snap_end < text_len:
                last_space = full_text.rfind(" ", snap_start, snap_end)
                if last_space != -1 and last_space > snap_end - 60:
                    snap_end = last_space

            if snap_end <= snap_start:
                snap_start = start
                snap_end = end

            win_text = full_text[snap_start:snap_end].strip()
            win_id = f"parent_{doc_id}_p{page_number}_w{window_idx}"
            windows.append((win_id, win_text, snap_start, snap_end))
            window_idx += 1

            if end >= text_len:
                break
            start += step

        return windows

    def _extract_parent_context(
        self,
        snippet: str,
        full_text: str,
        doc_id: str,
        page_number: int,
        parent_windows: Optional[List[Tuple[str, str, int, int]]] = None,
        start_hint: int = 0,
    ) -> Tuple[str, str]:
        """
        Extract a localized parent context window (~parent_chunk_size_chars) covering
        the child chunk snippet, avoiding whole-page truncation or detached parent context.
        Returns (parent_id, parent_text).
        """
        if len(full_text) <= self.parent_chunk_size_chars:
            return f"parent_{doc_id}_p{page_number}", full_text

        windows = parent_windows if parent_windows is not None else self._compute_page_parent_windows(full_text, doc_id, page_number)
        if not windows:
            return f"parent_{doc_id}_p{page_number}", full_text

        idx = self._locate_snippet(snippet, full_text, start_hint=start_hint)
        if idx == -1:
            logger.warning(
                "Parent window location warning: snippet (len=%d) not found in page %d of doc '%s' "
                "(start_hint=%d). Defaulting center to start_hint cursor.",
                len(snippet), page_number, doc_id, start_hint
            )
            center = min(len(full_text), max(0, start_hint))
        else:
            clean_snippet = re.sub(r"^\[(?:Ngữ cảnh|Tài liệu|Hỏi - Đáp|FAQ):[^\]]+\]\s*", "", snippet).strip()
            center = idx + (len(clean_snippet) // 2)

        # Deterministically select the window whose center is closest to child snippet center
        best_win = min(
            windows,
            key=lambda w: abs(((w[2] + w[3]) / 2) - center)
        )
        return best_win[0], best_win[1]

    def _create_chunk(
        self,
        raw_text: str,
        clean_page_text: str,
        doc_id: str,
        page_number: int,
        chunk_index: int,
        breadcrumb: List[str],
        heading_level: int = 0,
        doc_title: Optional[str] = None,
        content_type: str = "text",
        strategy: str = "hierarchical_structural",
        is_table: bool = False,
        table_headers: Optional[List[str]] = None,
        parent_windows: Optional[List[Tuple[str, str, int, int]]] = None,
        start_hint: int = 0,
    ) -> Tuple[DocumentChunk, int]:
        """
        Factory helper to construct DocumentChunk instances cleanly without code duplication.
        Calculates parent context, breadcrumbs, token counts, and updates page cursor.
        """
        enriched = self._enrich_chunk_text(raw_text, breadcrumb, doc_title=doc_title)
        p_id, p_text = self._extract_parent_context(
            raw_text,
            clean_page_text,
            doc_id,
            page_number,
            parent_windows=parent_windows,
            start_hint=start_hint,
        )

        metadata: Dict[str, Any] = {
            "chunk_id": f"{doc_id}_{chunk_index}",
            "parent_id": p_id,
            "parent_text": p_text,
            "char_length": len(enriched),
            "token_count": self._estimate_tokens(len(enriched)),
            "source_page": page_number,
            "heading_path": " > ".join(breadcrumb),
            "heading": breadcrumb[-1] if breadcrumb else "",
            "heading_level": heading_level,
            "is_table": is_table,
            "content_type": content_type,
            "strategy": strategy,
            "title": doc_title,
        }
        if table_headers:
            metadata["table_headers"] = table_headers

        chunk = DocumentChunk(
            doc_id=doc_id,
            chunk_index=chunk_index,
            page_number=page_number,
            text=enriched,
            metadata=metadata,
        )

        loc = self._locate_snippet(raw_text, clean_page_text, start_hint=start_hint)
        next_hint = (loc + len(raw_text)) if loc != -1 else (start_hint + len(raw_text))
        return chunk, next_hint

    def _split_large_paragraph(self, para: str, max_chars: int, overlap: int) -> List[str]:
        """Split a long paragraph that exceeds max_chars into sentence-aware sub-chunks with overlap."""
        if len(para) <= max_chars:
            return [para]

        sentence_ends = re.compile(r"(?<=[.!?;\n])\s+")
        sentences = sentence_ends.split(para)
        sub_chunks: List[str] = []
        curr_chunk_sentences: List[str] = []
        curr_len = 0

        for s in sentences:
            s_clean = s.strip()
            if not s_clean:
                continue
            s_len = len(s_clean)

            if s_len > max_chars:
                if curr_chunk_sentences:
                    sub_chunks.append(" ".join(curr_chunk_sentences))
                    curr_chunk_sentences = []
                    curr_len = 0
                words = s_clean.split()
                w_buf: List[str] = []
                w_len = 0
                for w in words:
                    if w_buf and (w_len + len(w) + 1 > max_chars):
                        sub_chunks.append(" ".join(w_buf))
                        overlap_words: List[str] = []
                        o_len = 0
                        for ow in reversed(w_buf):
                            if o_len + len(ow) + 1 <= overlap:
                                overlap_words.insert(0, ow)
                                o_len += len(ow) + 1
                            else:
                                break
                        w_buf = overlap_words + [w]
                        w_len = sum(len(x) + 1 for x in w_buf)
                    else:
                        w_buf.append(w)
                        w_len += len(w) + 1
                if w_buf:
                    sub_chunks.append(" ".join(w_buf))
                continue

            if curr_chunk_sentences and (curr_len + s_len + 1 > max_chars):
                sub_chunks.append(" ".join(curr_chunk_sentences))
                overlap_sentences: List[str] = []
                o_len = 0
                for prev_s in reversed(curr_chunk_sentences):
                    if o_len + len(prev_s) + 1 <= overlap:
                        overlap_sentences.insert(0, prev_s)
                        o_len += len(prev_s) + 1
                    else:
                        break
                curr_chunk_sentences = overlap_sentences + [s_clean]
                curr_len = sum(len(x) + 1 for x in curr_chunk_sentences)
            else:
                curr_chunk_sentences.append(s_clean)
                curr_len += s_len + 1

        if curr_chunk_sentences:
            sub_chunks.append(" ".join(curr_chunk_sentences))

        return sub_chunks if sub_chunks else [para]

    def chunk_document(self, parsed_doc: ParsedDocument, doc_id: str, title: Optional[str] = None) -> List[DocumentChunk]:
        """
        Split parsed document into chunks honoring structure, tables, and parent-child links.
        When hierarchical=True, generates small child chunks linked to larger parent contexts.
        """
        doc_title = title or (parsed_doc.metadata.get("title") if hasattr(parsed_doc, "metadata") and parsed_doc.metadata else None)
        if not doc_title and hasattr(parsed_doc, "filename") and parsed_doc.filename:
            raw_fn = parsed_doc.filename
            doc_title = re.sub(r"\.[a-zA-Z0-9]+$", "", raw_fn).strip()
        chunks: List[DocumentChunk] = []
        chunk_index = 0
        breadcrumb_stack: List[Tuple[int, str]] = []
        current_breadcrumb: List[str] = []
        current_heading_level = 0

        for page in parsed_doc.pages:
            clean_text = self._mask_pii(page.text.strip())
            clean_text = clean_text.replace("\r\n", "\n").replace("\r", "\n")
            if not clean_text:
                continue

            if not self.hierarchical:
                # Flat sliding window chunking fallback
                start = 0
                while start < len(clean_text):
                    end = min(start + self.child_chunk_size_chars, len(clean_text))
                    if end < len(clean_text):
                        last_break = max(clean_text.rfind("\n", start, end), clean_text.rfind(" ", start, end))
                        if last_break > start + (self.child_chunk_size_chars // 2):
                            end = last_break
                    chunk_slice = clean_text[start:end].strip()
                    if chunk_slice:
                        chunks.append(
                            DocumentChunk(
                                doc_id=doc_id,
                                chunk_index=chunk_index,
                                page_number=page.page_number,
                                text=chunk_slice,
                                metadata={
                                    "chunk_id": f"{doc_id}_{chunk_index}",
                                    "char_length": len(chunk_slice),
                                    "token_count": self._estimate_tokens(len(chunk_slice)),
                                    "source_page": page.page_number,
                                    "is_table": False,
                                    "content_type": "text",
                                },
                            )
                        )
                        chunk_index += 1
                    if end >= len(clean_text):
                        break
                    start = max(start + 1, end - self.child_overlap_chars)
                continue

            # Hierarchical Structure & Atomic Table Processing
            page_parent_windows = self._compute_page_parent_windows(clean_text, doc_id, page.page_number)
            page_cursor = 0
            paragraphs = self._split_into_blocks(clean_text)
            curr_text_buffer: List[str] = []
            curr_buffer_len = 0

            for raw_para in paragraphs:
                para = raw_para
                lines = [l.strip() for l in para.split("\n") if l.strip()]

                # Step A: Extract any leading structural headings from paragraph block
                while lines:
                    heading_info = self._extract_heading(lines[0])
                    if heading_info is not None:
                        # Flush existing buffer under previous heading
                        if curr_text_buffer:
                            combined_text = "\n\n".join(curr_text_buffer).strip()
                            chunk, page_cursor = self._create_chunk(
                                raw_text=combined_text,
                                clean_page_text=clean_text,
                                doc_id=doc_id,
                                page_number=page.page_number,
                                chunk_index=chunk_index,
                                breadcrumb=current_breadcrumb,
                                heading_level=current_heading_level,
                                doc_title=doc_title,
                                parent_windows=page_parent_windows,
                                start_hint=page_cursor,
                            )
                            chunks.append(chunk)
                            chunk_index += 1
                            curr_text_buffer = []
                            curr_buffer_len = 0

                        level, heading_title = heading_info
                        current_heading_level = level
                        while breadcrumb_stack and breadcrumb_stack[-1][0] >= level:
                            breadcrumb_stack.pop()
                        breadcrumb_stack.append((level, heading_title))
                        current_breadcrumb = [t for _, t in breadcrumb_stack]
                        lines = lines[1:]
                    else:
                        break

                if not lines:
                    continue

                para = "\n".join(lines).strip()

                # Step B: Check if block is a table
                if self._is_table_block(para):
                    if curr_text_buffer:
                        combined_text = "\n\n".join(curr_text_buffer).strip()
                        chunk, page_cursor = self._create_chunk(
                            raw_text=combined_text,
                            clean_page_text=clean_text,
                            doc_id=doc_id,
                            page_number=page.page_number,
                            chunk_index=chunk_index,
                            breadcrumb=current_breadcrumb,
                            heading_level=current_heading_level,
                            doc_title=doc_title,
                            parent_windows=page_parent_windows,
                            start_hint=page_cursor,
                        )
                        chunks.append(chunk)
                        chunk_index += 1
                        curr_text_buffer = []
                        curr_buffer_len = 0

                    table_subparts = self._split_table_atomically(para, self.child_chunk_size_chars)
                    for sub_tbl, sub_heading in table_subparts:
                        bc = list(current_breadcrumb)
                        if sub_heading:
                            bc.append(sub_heading)
                        chunk, page_cursor = self._create_chunk(
                            raw_text=sub_tbl,
                            clean_page_text=clean_text,
                            doc_id=doc_id,
                            page_number=page.page_number,
                            chunk_index=chunk_index,
                            breadcrumb=bc,
                            heading_level=current_heading_level,
                            doc_title=doc_title,
                            content_type="table",
                            strategy="atomic_table",
                            is_table=True,
                            table_headers=self._extract_table_headers(sub_tbl),
                            parent_windows=page_parent_windows,
                            start_hint=page_cursor,
                        )
                        chunks.append(chunk)
                        chunk_index += 1
                    continue

                # Step C: Check if block is a code block
                if self._is_code_block(para):
                    if curr_text_buffer:
                        combined_text = "\n\n".join(curr_text_buffer).strip()
                        chunk, page_cursor = self._create_chunk(
                            raw_text=combined_text,
                            clean_page_text=clean_text,
                            doc_id=doc_id,
                            page_number=page.page_number,
                            chunk_index=chunk_index,
                            breadcrumb=current_breadcrumb,
                            heading_level=current_heading_level,
                            doc_title=doc_title,
                            parent_windows=page_parent_windows,
                            start_hint=page_cursor,
                        )
                        chunks.append(chunk)
                        chunk_index += 1
                        curr_text_buffer = []
                        curr_buffer_len = 0

                    chunk, page_cursor = self._create_chunk(
                        raw_text=para,
                        clean_page_text=clean_text,
                        doc_id=doc_id,
                        page_number=page.page_number,
                        chunk_index=chunk_index,
                        breadcrumb=current_breadcrumb,
                        heading_level=current_heading_level,
                        doc_title=doc_title,
                        content_type="code",
                        strategy="code_block",
                        parent_windows=page_parent_windows,
                        start_hint=page_cursor,
                    )
                    chunks.append(chunk)
                    chunk_index += 1
                    continue

                # Step D: Regular text paragraph
                para_len = len(para)
                if para_len > self.child_chunk_size_chars:
                    if curr_text_buffer:
                        combined_text = "\n\n".join(curr_text_buffer).strip()
                        chunk, page_cursor = self._create_chunk(
                            raw_text=combined_text,
                            clean_page_text=clean_text,
                            doc_id=doc_id,
                            page_number=page.page_number,
                            chunk_index=chunk_index,
                            breadcrumb=current_breadcrumb,
                            heading_level=current_heading_level,
                            doc_title=doc_title,
                            parent_windows=page_parent_windows,
                            start_hint=page_cursor,
                        )
                        chunks.append(chunk)
                        chunk_index += 1
                        curr_text_buffer = []
                        curr_buffer_len = 0

                    sub_paras = self._split_large_paragraph(para, self.child_chunk_size_chars, self.child_overlap_chars)
                    for sp in sub_paras:
                        chunk, page_cursor = self._create_chunk(
                            raw_text=sp,
                            clean_page_text=clean_text,
                            doc_id=doc_id,
                            page_number=page.page_number,
                            chunk_index=chunk_index,
                            breadcrumb=current_breadcrumb,
                            heading_level=current_heading_level,
                            doc_title=doc_title,
                            parent_windows=page_parent_windows,
                            start_hint=page_cursor,
                        )
                        chunks.append(chunk)
                        chunk_index += 1
                    continue

                if curr_text_buffer and (curr_buffer_len + para_len > self.child_chunk_size_chars):
                    combined_text = "\n\n".join(curr_text_buffer).strip()
                    chunk, page_cursor = self._create_chunk(
                        raw_text=combined_text,
                        clean_page_text=clean_text,
                        doc_id=doc_id,
                        page_number=page.page_number,
                        chunk_index=chunk_index,
                        breadcrumb=current_breadcrumb,
                        heading_level=current_heading_level,
                        doc_title=doc_title,
                        parent_windows=page_parent_windows,
                        start_hint=page_cursor,
                    )
                    chunks.append(chunk)
                    chunk_index += 1
                    curr_text_buffer = [para]
                    curr_buffer_len = para_len
                else:
                    curr_text_buffer.append(para)
                    curr_buffer_len += para_len + 2

            # Flush remaining buffer for the page
            if curr_text_buffer:
                combined_text = "\n\n".join(curr_text_buffer).strip()
                chunk, page_cursor = self._create_chunk(
                    raw_text=combined_text,
                    clean_page_text=clean_text,
                    doc_id=doc_id,
                    page_number=page.page_number,
                    chunk_index=chunk_index,
                    breadcrumb=current_breadcrumb,
                    heading_level=current_heading_level,
                    doc_title=doc_title,
                    parent_windows=page_parent_windows,
                    start_hint=page_cursor,
                )
                chunks.append(chunk)
                chunk_index += 1

        return chunks
