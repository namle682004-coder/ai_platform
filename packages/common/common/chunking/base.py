"""
Base Chunking contracts and dataclasses.
Shared enterprise contract across AIP Platform services and workers.
Compliant with Enterprise RAG Architecture standards.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class DocumentChunk:
    chunk_id: str
    doc_id: str
    chunk_index: int
    text: str
    page_number: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseChunker(ABC):
    """Abstract interface for all chunking implementations."""

    @abstractmethod
    def chunk_document(self, doc: Any, doc_id: str) -> List[DocumentChunk]:
        """Split a ParsedDocument or generic document container into an ordered list of DocumentChunks."""
        pass

    def split_text(self, text: str, default_page: int = 1) -> List[Dict[str, Any]]:
        """Convenience helper to chunk raw string into standard dict representation."""
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
