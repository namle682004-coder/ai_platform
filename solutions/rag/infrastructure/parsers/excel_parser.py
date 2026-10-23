"""
Excel Spreadsheet (.xlsx, .xls) Document Parser.
Converts spreadsheet worksheets into structured Markdown tables directly in RAM.
"""

from __future__ import annotations

import io
import logging
from typing import List
from ...domain.entities import ParsedDocument, ParsedPage
from ...domain.exceptions import DocumentParsingError
from .base import BaseDocumentParser

logger = logging.getLogger("aip-rag.parser.excel")


class ExcelDocumentParser(BaseDocumentParser):
    """Parser for Excel spreadsheets converting sheets into Markdown tables."""

    def parse(self, file_bytes: bytes, filename: str) -> ParsedDocument:
        try:
            import openpyxl
        except ImportError:
            raise DocumentParsingError("Thư viện 'openpyxl' chưa được cài đặt để đọc bảng tính Excel (.xlsx).")

        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
            pages: List[ParsedPage] = []

            for sheet_idx, sheet_name in enumerate(wb.sheetnames, start=1):
                ws = wb[sheet_name]
                lines = [f"### Bảng tính: {sheet_name}\n"]

                rows = list(ws.iter_rows(values_only=True))
                # Filter out completely empty rows
                non_empty_rows = [
                    [str(cell if cell is not None else "").strip() for cell in r]
                    for r in rows
                    if any(cell is not None and str(cell).strip() != "" for cell in r)
                ]

                if not non_empty_rows:
                    continue

                header = non_empty_rows[0]
                max_cols = len(header)
                lines.append("| " + " | ".join(header[i] if i < len(header) else "" for i in range(max_cols)) + " |")
                lines.append("| " + " | ".join(["---"] * max_cols) + " |")

                for row in non_empty_rows[1:]:
                    row_vals = [row[i] if i < len(row) else "" for i in range(max_cols)]
                    lines.append("| " + " | ".join(row_vals) + " |")

                sheet_text = "\n".join(lines)
                pages.append(ParsedPage(page_number=sheet_idx, text=sheet_text))

            if not pages:
                pages.append(ParsedPage(page_number=1, text="[File Excel trống dữ liệu]"))

            ext = filename.split(".")[-1].lower() if "." in filename else "xlsx"
            return ParsedDocument(
                filename=filename,
                file_type=ext,
                pages=pages,
                metadata={"total_sheets": len(wb.sheetnames)},
            )
        except Exception as exc:
            logger.error("Failed to parse Excel document '%s': %s", filename, exc)
            raise DocumentParsingError(f"Excel parsing failed: {exc}") from exc
