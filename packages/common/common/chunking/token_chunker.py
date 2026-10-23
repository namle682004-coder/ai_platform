"""
Enterprise Hybrid Structural-Semantic Chunker.
Shared enterprise implementation across AIP Platform services and rag-worker.
Combines Document Structure Tracking (Headings & Tables) + Recursive Sentence-Boundary Sliding Windows.
100% compliant with Enterprise RAG Architecture standards (Slide pages 19-35).
100% Domain-Agnostic: Zero hardcoded legal-specific regex.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .base import BaseChunker, DocumentChunk
from .sanitizer import PiiSanitizer

TABLE_PATTERN = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)
SECTION_PATTERN = re.compile(
    r"^(#{1,6}\s+|[IVXLCDM]+\.\s+|\d+(?:\.\d+)+\.?\s+|[A-Z]\.\s+|(?:Chapter|Section|Part|Appendix)\s+[0-9IVXLCDM]+)\b",
    re.IGNORECASE,
)
SENTENCE_SPLIT_REGEX = re.compile(r"(?<=[.!?…])\s+")


class TokenChunker(BaseChunker):
    """
    Production-grade Hybrid Chunker for Enterprise Documents.
    Features:
    - Atomic Table Preservation (Markdown / HTML).
    - Regulatory & Structure Heading tracking with contextual breadcrumbs.
    - Sentence-aware Recursive Window: Never splits words or sentences in half.
    - Cross-paragraph Sliding Window Overlap (15-20%) for unbroken contextual flow.
    - PII Sanitization (CCCD, emails, phone numbers, secret tokens).
    """

    def __init__(
        self,
        chunk_size_chars: int = 1200,
        chunk_overlap_chars: int = 180,
        min_chunk_length: int = 50,
        mask_pii: bool = True,
        inject_heading_context: bool = True,
    ) -> None:
        self.chunk_size = chunk_size_chars
        self.chunk_overlap = min(chunk_overlap_chars, chunk_size_chars // 2)
        self.min_chunk_length = min_chunk_length
        self.mask_pii = mask_pii
        self.inject_heading_context = inject_heading_context

    @staticmethod
    def _is_table_block(text: str) -> bool:
        """Detect Markdown or HTML table blocks."""
        if "<table" in text.lower():
            return True
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if len(lines) >= 2:
            pipe_lines = sum(1 for line in lines if line.startswith("|") and line.endswith("|"))
            if pipe_lines >= 2 and pipe_lines >= len(lines) * 0.7:
                return True
        return False

    @staticmethod
    def _split_into_sentences(para: str) -> List[str]:
        """Split a paragraph along sentence boundaries without truncating words."""
        sentences = [s.strip() for s in SENTENCE_SPLIT_REGEX.split(para) if s.strip()]
        return sentences if sentences else [para.strip()]

    def chunk_document(self, doc: Any, doc_id: str) -> List[DocumentChunk]:
        all_chunks: List[DocumentChunk] = []
        global_chunk_idx = 0

        pages = getattr(doc, "pages", [])
        if not pages:
            raw_text = getattr(doc, "text", str(doc))
            pages = [type("GenericPage", (), {"page_number": 1, "text": raw_text})()]

        active_heading = ""
        current_sentences: List[tuple[str, int]] = []  # (sentence_text, page_number)
        current_len = 0

        def _flush_buffer(allow_short: bool = False) -> None:
            nonlocal global_chunk_idx, current_sentences, current_len
            if not current_sentences:
                return

            chunk_body = " ".join(s[0] for s in current_sentences).strip()
            if not chunk_body:
                return
            if not allow_short and len(chunk_body) < self.min_chunk_length:
                return

            chunk_page = current_sentences[0][1]
            final_text = chunk_body
            if self.inject_heading_context and active_heading and not chunk_body.startswith(active_heading):
                final_text = f"[{active_heading}]\n{chunk_body}"

            all_chunks.append(DocumentChunk(
                chunk_id=f"{doc_id}_{global_chunk_idx}",
                doc_id=doc_id,
                chunk_index=global_chunk_idx,
                text=final_text,
                page_number=chunk_page,
                metadata={
                    "source_page": chunk_page,
                    "heading": active_heading,
                    "content_type": "text",
                    "strategy": "hybrid_structural_semantic",
                    "char_length": len(final_text),
                    "token_count": max(1, len(final_text) // 4),
                },
            ))
            global_chunk_idx += 1

            # Compute sliding-window overlap using complete sentences
            overlap_sentences: List[tuple[str, int]] = []
            overlap_len = 0
            for s_tuple in reversed(current_sentences):
                s_text = s_tuple[0]
                if overlap_len + len(s_text) <= self.chunk_overlap:
                    overlap_sentences.insert(0, s_tuple)
                    overlap_len += len(s_text) + 1
                else:
                    break

            current_sentences = overlap_sentences
            current_len = sum(len(s[0]) + 1 for s in current_sentences)

        for page in pages:
            raw_text = getattr(page, "text", "").strip()
            if not raw_text:
                continue

            if self.mask_pii:
                raw_text = PiiSanitizer.sanitize(raw_text)

            paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]

            for para in paragraphs:
                # 1. Handle Table Block atomically
                if self._is_table_block(para):
                    _flush_buffer(allow_short=True)
                    current_sentences = []
                    current_len = 0

                    table_text = para
                    if self.inject_heading_context and active_heading:
                        table_text = f"[{active_heading}]\n{para}"

                    all_chunks.append(DocumentChunk(
                        chunk_id=f"{doc_id}_{global_chunk_idx}",
                        doc_id=doc_id,
                        chunk_index=global_chunk_idx,
                        text=table_text,
                        page_number=page.page_number,
                        metadata={
                            "source_page": page.page_number,
                            "heading": active_heading,
                            "content_type": "table",
                            "strategy": "hybrid_structural_semantic",
                            "char_length": len(table_text),
                            "token_count": max(1, len(table_text) // 4),
                        },
                    ))
                    global_chunk_idx += 1
                    continue

                # 2. Handle Heading / Section boundary
                if SECTION_PATTERN.match(para):
                    _flush_buffer(allow_short=True)
                    current_sentences = []
                    current_len = 0
                    active_heading = para.split("\n")[0][:120].strip()

                # 3. Process sentences within paragraph
                sentences = self._split_into_sentences(para)
                for sentence in sentences:
                    s_len = len(sentence)
                    if current_len + s_len > self.chunk_size and current_sentences:
                        _flush_buffer()

                    current_sentences.append((sentence, page.page_number))
                    current_len += s_len + 1

        # Final flush for trailing content
        _flush_buffer(allow_short=True)

        return all_chunks


class TextChunker(TokenChunker):
    """
    Backwards-compatible convenience wrapper for string splitting.
    Fully compatible with legacy tests and endpoints.
    """

    def split_text(self, text: str, default_page: int = 1) -> List[Dict[str, Any]]:
        page = type("SimplePage", (), {"page_number": default_page, "text": text})()
        doc = type("SimpleDoc", (), {"pages": [page]})()
        chunks = self.chunk_document(doc, doc_id="inline")
        return [
            {
                "chunk_index": c.chunk_index,
                "text": c.text,
                "page_number": c.page_number,
                "metadata": c.metadata,
            }
            for c in chunks
        ]
