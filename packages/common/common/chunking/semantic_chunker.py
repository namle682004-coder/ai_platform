"""
Semantic Sentence-Window Chunker.
Directly implements Semantic Chunking from RAG standards (Slide pages 25-29).
Splits documents along natural sentence and semantic boundaries, preventing mid-sentence truncation
and grouping cohesive sentences into optimal context windows.
"""

from __future__ import annotations

import re
from typing import Any, List

from .base import BaseChunker, DocumentChunk
from .sanitizer import PiiSanitizer

VIETNAMESE_SENTENCE_REGEX = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÀ-Ỹ0-9])")


class SemanticChunker(BaseChunker):
    """
    Sentence-aware Semantic Chunker.
    Ensures every chunk is composed of complete, grammatically sound sentences.
    Preserves context bridges across sentence boundaries with sentence-level overlap.
    """

    def __init__(
        self,
        max_chunk_chars: int = 1000,
        min_chunk_chars: int = 100,
        sentence_overlap_count: int = 2,
        mask_pii: bool = True,
    ) -> None:
        self.max_chunk_chars = max_chunk_chars
        self.min_chunk_chars = min_chunk_chars
        self.sentence_overlap_count = sentence_overlap_count
        self.mask_pii = mask_pii

    @staticmethod
    def _split_into_sentences(text: str) -> List[str]:
        """Splits text into cohesive sentences supporting Vietnamese punctuation and abbreviations."""
        raw_paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        all_sentences: List[str] = []

        for p in raw_paragraphs:
            # Split by sentence enders while guarding against decimals or abbreviations
            sub_sentences = VIETNAMESE_SENTENCE_REGEX.split(p)
            for s in sub_sentences:
                cleaned = s.strip()
                if cleaned:
                    all_sentences.append(cleaned)

        return all_sentences

    def chunk_document(self, doc: Any, doc_id: str) -> List[DocumentChunk]:
        all_chunks: List[DocumentChunk] = []
        global_chunk_idx = 0

        pages = getattr(doc, "pages", [])
        if not pages:
            raw_text = getattr(doc, "text", str(doc))
            pages = [type("GenericPage", (), {"page_number": 1, "text": raw_text})()]

        for page in pages:
            raw_text = getattr(page, "text", "").strip()
            if not raw_text:
                continue

            if self.mask_pii:
                raw_text = PiiSanitizer.sanitize(raw_text)

            sentences = self._split_into_sentences(raw_text)
            if not sentences:
                continue

            current_window: List[str] = []
            current_len = 0

            for sentence in sentences:
                s_len = len(sentence)
                if current_len + s_len > self.max_chunk_chars and current_window:
                    chunk_text = " ".join(current_window).strip()
                    if len(chunk_text) >= self.min_chunk_chars:
                        all_chunks.append(DocumentChunk(
                            chunk_id=f"{doc_id}_{global_chunk_idx}",
                            doc_id=doc_id,
                            chunk_index=global_chunk_idx,
                            text=chunk_text,
                            page_number=page.page_number,
                            metadata={
                                "source_page": page.page_number,
                                "sentence_count": len(current_window),
                                "strategy": "semantic_sentence_window",
                            },
                        ))
                        global_chunk_idx += 1

                    # Slide window with sentence overlap
                    overlap_sentences = current_window[-self.sentence_overlap_count :]
                    current_window = list(overlap_sentences)
                    current_len = sum(len(s) + 1 for s in current_window)

                current_window.append(sentence)
                current_len += s_len + 1

            if current_window:
                chunk_text = " ".join(current_window).strip()
                if len(chunk_text) >= self.min_chunk_chars:
                    all_chunks.append(DocumentChunk(
                        chunk_id=f"{doc_id}_{global_chunk_idx}",
                        doc_id=doc_id,
                        chunk_index=global_chunk_idx,
                        text=chunk_text,
                        page_number=page.page_number,
                        metadata={
                            "source_page": page.page_number,
                            "sentence_count": len(current_window),
                            "strategy": "semantic_sentence_window",
                        },
                    ))
                    global_chunk_idx += 1

        return all_chunks
