"""
Base document parser interface for infrastructure layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from ...domain.entities import ParsedDocument, ParsedPage
from ...domain.ports import DocumentParserPort


class BaseDocumentParser(DocumentParserPort, ABC):
    """Abstract base class for format-specific parsers."""

    @abstractmethod
    def parse(self, file_bytes: bytes, filename: str) -> ParsedDocument:
        ...
