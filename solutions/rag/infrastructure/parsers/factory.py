"""
Document Parser Factory resolving format-specific parsers.
"""

from __future__ import annotations

import os
from typing import Dict, Type

from ...domain.entities import ParsedDocument
from ...domain.ports import DocumentParserPort
from .base import BaseDocumentParser
from .docx_parser import DocxDocumentParser
from .excel_parser import ExcelDocumentParser
from .pdf_parser import PdfDocumentParser
from .text_parser import TextDocumentParser


class DocumentParserFactory(DocumentParserPort):
    """Factory and unified adapter for all document parsers."""

    _registry: Dict[str, Type[BaseDocumentParser]] = {
        ".pdf": PdfDocumentParser,
        ".docx": DocxDocumentParser,
        ".xlsx": ExcelDocumentParser,
        ".xls": ExcelDocumentParser,
        ".txt": TextDocumentParser,
        ".md": TextDocumentParser,
        ".markdown": TextDocumentParser,
        ".json": TextDocumentParser,
        ".csv": TextDocumentParser,
    }

    def parse(self, file_bytes: bytes, filename: str) -> ParsedDocument:
        ext = os.path.splitext(filename)[1].lower() if filename else ""

        # Magic byte detection as robust fallback
        if (not ext or ext not in self._registry) and file_bytes:
            if file_bytes.startswith(b"%PDF"):
                ext = ".pdf"
            elif file_bytes.startswith(b"PK\x03\x04"):
                if filename.lower().endswith((".xlsx", ".xls")):
                    ext = ".xlsx"
                else:
                    ext = ".docx"

        parser_cls = self._registry.get(ext, TextDocumentParser)
        parser = parser_cls()
        return parser.parse(file_bytes, filename)

    def get_parser(self, filename: str) -> BaseDocumentParser:
        """Resolve format-specific parser instance."""
        ext = os.path.splitext(filename)[1].lower() if filename else ""
        parser_cls = self._registry.get(ext, TextDocumentParser)
        return parser_cls()


parser_factory = DocumentParserFactory()
