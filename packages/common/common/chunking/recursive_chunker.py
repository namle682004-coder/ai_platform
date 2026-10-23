"""
Recursive Character & Hierarchy-aware Chunker.
Directly implements the Recursive Chunking architecture from RAG standards (Slide pages 22-24).
Splits recursively by hierarchical separators: ["\\n\\n", "\\n", ". ", "! ", "? ", "; ", " ", ""].
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import BaseChunker, DocumentChunk
from .sanitizer import PiiSanitizer


class RecursiveChunker(BaseChunker):
    """
    Production Recursive Chunker implementing hierarchical splitting.
    Prioritizes paragraph breaks, then line breaks, then sentence boundaries, then words.
    Maintains semantic integrity and natural reading flow without mutilating Vietnamese tokens.
    """

    DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", "! ", "? ", "; ", " ", ""]

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 150,
        min_chunk_length: int = 50,
        separators: Optional[List[str]] = None,
        keep_separator: bool = True,
        strip_whitespace: bool = True,
        add_start_index: bool = True,
        mask_pii: bool = True,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = min(chunk_overlap, chunk_size // 2)
        self.min_chunk_length = min_chunk_length
        self.separators = separators or list(self.DEFAULT_SEPARATORS)
        self.keep_separator = keep_separator
        self.strip_whitespace = strip_whitespace
        self.add_start_index = add_start_index
        self.mask_pii = mask_pii

    def _split_text_recursive(self, text: str, separators: List[str]) -> List[str]:
        """Recursively split text using the first matching separator."""
        separator = separators[-1]
        new_separators: List[str] = []

        for i, sep in enumerate(separators):
            if sep == "":
                separator = ""
                break
            if sep in text:
                separator = sep
                new_separators = separators[i + 1 :]
                break

        splits = text.split(separator) if separator else list(text)

        good_splits: List[str] = []
        for s in splits:
            if not s and not self.keep_separator:
                continue
            item = s if not self.keep_separator else (s + separator if s else "")
            if len(item) < self.chunk_size:
                good_splits.append(item)
            else:
                if new_separators:
                    sub_splits = self._split_text_recursive(s, new_separators)
                    good_splits.extend(sub_splits)
                else:
                    good_splits.append(item)

        return good_splits

    def _merge_splits(self, splits: List[str], separator: str = "") -> List[Dict[str, Any]]:
        """Merges small splits into chunks up to chunk_size with chunk_overlap."""
        docs: List[Dict[str, Any]] = []
        current_doc: List[str] = []
        total = 0
        current_start_idx = 0
        running_char_offset = 0

        for split in splits:
            split_len = len(split)
            if total + split_len > self.chunk_size and current_doc:
                doc_text = "".join(current_doc)
                if self.strip_whitespace:
                    doc_text = doc_text.strip()
                if len(doc_text) >= self.min_chunk_length:
                    docs.append({
                        "text": doc_text,
                        "start_index": current_start_idx,
                        "end_index": current_start_idx + len(doc_text),
                    })

                # Maintain overlap by retaining trailing splits
                while total > self.chunk_overlap or (total + split_len > self.chunk_size and total > 0):
                    popped = current_doc.pop(0)
                    total -= len(popped)
                    current_start_idx += len(popped)

            current_doc.append(split)
            total += split_len
            running_char_offset += split_len

        if current_doc:
            doc_text = "".join(current_doc)
            if self.strip_whitespace:
                doc_text = doc_text.strip()
            if len(doc_text) >= self.min_chunk_length:
                docs.append({
                    "text": doc_text,
                    "start_index": current_start_idx,
                    "end_index": current_start_idx + len(doc_text),
                })

        return docs

    def chunk_document(self, doc: Any, doc_id: str) -> List[DocumentChunk]:
        """Chunks a document or page-based container with page continuity."""
        all_chunks: List[DocumentChunk] = []
        global_chunk_idx = 0

        pages = getattr(doc, "pages", [])
        if not pages:
            raw_text = getattr(doc, "text", str(doc))
            pages = [type("GenericPage", (), {"page_number": 1, "text": raw_text})()]

        # Process page by page while maintaining metadata tracking
        for page in pages:
            raw_text = getattr(page, "text", "").strip()
            if not raw_text:
                continue

            if self.mask_pii:
                raw_text = PiiSanitizer.sanitize(raw_text)

            splits = self._split_text_recursive(raw_text, self.separators)
            merged_items = self._merge_splits(splits)

            for item in merged_items:
                metadata: Dict[str, Any] = {
                    "source_page": page.page_number,
                    "strategy": "recursive",
                }
                if self.add_start_index:
                    metadata["start_index"] = item.get("start_index", 0)
                    metadata["end_index"] = item.get("end_index", 0)

                all_chunks.append(DocumentChunk(
                    chunk_id=f"{doc_id}_{global_chunk_idx}",
                    doc_id=doc_id,
                    chunk_index=global_chunk_idx,
                    text=item["text"],
                    page_number=page.page_number,
                    metadata=metadata,
                ))
                global_chunk_idx += 1

        return all_chunks
