"""
Excel Spreadsheet (.xlsx, .xls) Document Parser.
Converts each worksheet into one or more Markdown tables (a sheet often holds several tables separated by
an empty row and a title row), with merged cells resolved by the shared table renderer.
"""

from __future__ import annotations

import io
import logging
from typing import Dict, List, Tuple

from ...domain.entities import ParsedDocument, ParsedPage
from ...domain.exceptions import DocumentParsingError
from .base import BaseDocumentParser
from .table_grid import GridCell, clean, render_table, split_blocks

logger = logging.getLogger("aip-rag.parser.excel")


def _sheet_grid(ws) -> List[List[GridCell]]:
    """Cell grid of a worksheet; every position of a merged range carries its value and the range as key."""
    merged: Dict[Tuple[int, int], Tuple[str, int]] = {}
    for rng in ws.merged_cells.ranges:
        top_left = ws.cell(row=rng.min_row, column=rng.min_col).value
        for r in range(rng.min_row, rng.max_row + 1):
            for c in range(rng.min_col, rng.max_col + 1):
                merged[(r, c)] = (clean(top_left), id(rng))
    grid: List[List[GridCell]] = []
    for row in ws.iter_rows():
        cells = []
        for cell in row:
            if (cell.row, cell.column) in merged:
                text, key = merged[(cell.row, cell.column)]
                cells.append(GridCell(text, key))
            else:
                cells.append(GridCell(clean(cell.value)))
        grid.append(cells)
    return grid


class ExcelDocumentParser(BaseDocumentParser):
    """Parser for Excel spreadsheets converting sheets into Markdown tables."""

    def parse(self, file_bytes: bytes, filename: str) -> ParsedDocument:
        try:
            import openpyxl
        except ImportError as exc:
            raise DocumentParsingError("Thư viện 'openpyxl' chưa được cài đặt để đọc bảng tính Excel (.xlsx).") from exc

        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
            pages: List[ParsedPage] = []

            for sheet_idx, sheet_name in enumerate(wb.sheetnames, start=1):
                tables = [render_table(block) for block in split_blocks(_sheet_grid(wb[sheet_name]))]
                tables = [t for t in tables if t]
                if not tables:
                    continue
                sheet_text = f"### Bảng tính: {sheet_name}\n\n" + "\n\n".join(tables)
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
