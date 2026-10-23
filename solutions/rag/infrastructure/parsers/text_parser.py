"""
Plaintext / Markdown / JSON / CSV Document Parser.
"""

from __future__ import annotations

import logging
from typing import List

from ...domain.entities import ParsedDocument, ParsedPage
from ...domain.exceptions import DocumentParsingError
from .base import BaseDocumentParser

logger = logging.getLogger("aip-rag.parser.text")


class TextDocumentParser(BaseDocumentParser):
    """Parser for plaintext, markdown, JSON, CSV files."""

    def parse(self, file_bytes: bytes, filename: str) -> ParsedDocument:
        try:
            text = file_bytes.decode("utf-8", errors="replace").strip()
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            pages = [ParsedPage(page_number=1, text=text)]
            ext = filename.split(".")[-1].lower() if "." in filename else "txt"
            return ParsedDocument(
                filename=filename,
                file_type=ext,
                pages=pages,
                metadata={"total_pages": 1},
            )
        except Exception as exc:
            logger.error("Failed to parse text document '%s': %s", filename, exc)
            raise DocumentParsingError(f"Text parsing failed: {exc}") from exc
