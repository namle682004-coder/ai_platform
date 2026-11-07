"""
Format-independent table rendering: a grid of cells (with merge information) to Markdown in which every
data cell has a real column name.

Parsers (docx, xlsx, pdf) only turn their table into a grid of `GridCell(text, key)`, where cells of one
merged region share the same non-None `key`. Rendering then handles, the same way for every format:

- caption rows: leading rows holding one value across the table ("BẢNG 1: …") become a caption line, not
  the header;
- multi-level headers: a header cell spanning several columns followed by a row that splits those
  columns ("Sắc thái" over "Tích cực | Tiêu cực | Trung tính") gives one flat header
  "Sắc thái / Tích cực | …", so every chunk of the table repeats complete column names;
- form tables: rows of "Label: value" without a header row are rendered as lines, not as a fake table;
- merged data cells: a value spanning several columns is written once; a value spanning several rows is
  repeated on each row, so every row reads on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Sequence

MAX_HEADER_LEVELS = 3


@dataclass(frozen=True)
class GridCell:
    text: str
    key: Any = None  # identical non-None keys = one merged region


def clean(text: Any) -> str:
    return " ".join(str(text if text is not None else "").split()).replace("|", "\\|")


def _pad(rows: List[List[GridCell]]) -> List[List[GridCell]]:
    width = max(len(r) for r in rows)
    return [list(r) + [GridCell("")] * (width - len(r)) for r in rows]


def _same_region(a: GridCell, b: GridCell) -> bool:
    return a.key is not None and a.key == b.key


def _distinct_values(row: Sequence[GridCell]) -> List[str]:
    out: List[str] = []
    for i, c in enumerate(row):
        if c.text and not (i and _same_region(row[i - 1], c)) and c.text not in out:
            out.append(c.text)
    return out


def is_caption_row(row: Sequence[GridCell]) -> bool:
    """One value across the table: a merged cell spanning (nearly) every column, or a lone cell."""
    filled = [c for c in row if c.text]
    if not filled or len(row) < 2:
        return False
    if len(_distinct_values(row)) != 1:
        return False
    spanning = sum(1 for c in row if _same_region(c, filled[0]))
    return len(filled) == 1 or spanning >= max(2, len(row) // 2)


def is_form_row(row: Sequence[GridCell]) -> bool:
    """A row of field labels awaiting values ("Mã vị trí việc làm:") is not a column header."""
    return any(c.text.rstrip().endswith(":") for c in row if c.text)


def _horizontal_groups(row: Sequence[GridCell]) -> List[List[int]]:
    groups, i = [], 0
    while i < len(row):
        j = i
        while j + 1 < len(row) and _same_region(row[i], row[j + 1]):
            j += 1
        if j > i and row[i].text:
            groups.append(list(range(i, j + 1)))
        i = j + 1
    return groups


def _is_subheader(level: Sequence[GridCell], nxt: Sequence[GridCell], groups: List[List[int]]) -> bool:
    """`nxt` names the columns that header cells of `level` span, and repeats (or leaves empty) the rest."""
    in_group = {c for g in groups for c in g}
    splits = any(len({nxt[c].text for c in g if nxt[c].text}) >= 2 for g in groups)
    rest_is_header = all(
        not nxt[c].text or _same_region(level[c], nxt[c]) or nxt[c].text == level[c].text
        for c in range(len(nxt)) if c not in in_group
    )
    return splits and rest_is_header


def _header(rows: List[List[GridCell]]) -> tuple[List[str], int]:
    """Flat column names and the number of rows they consumed."""
    level = rows[0]
    labels = [c.text for c in level]
    used = 1
    for _ in range(MAX_HEADER_LEVELS - 1):
        if used >= len(rows):
            break
        groups = _horizontal_groups(level)
        nxt = rows[used]
        if not groups or not _is_subheader(level, nxt, groups):
            break
        for g in groups:
            for c in g:
                if nxt[c].text and nxt[c].text != labels[c]:
                    labels[c] = f"{labels[c]} / {nxt[c].text}" if labels[c] else nxt[c].text
        level, used = nxt, used + 1
    return labels, used


def _data_row(row: Sequence[GridCell]) -> List[str]:
    """A value spanning several columns is written once (in its first column)."""
    return ["" if i and _same_region(row[i - 1], c) else c.text for i, c in enumerate(row)]


def render_table(grid: Sequence[Sequence[GridCell]], caption_prefix: str = "**") -> str:
    rows = [list(r) for r in grid if any(c.text for c in r)]
    if not rows:
        return ""
    rows = _pad(rows)
    keep = [c for c in range(len(rows[0])) if any(r[c].text for r in rows)]
    rows = [[r[c] for c in keep] for r in rows]
    out: List[str] = []
    while len(rows) > 1 and is_caption_row(rows[0]):
        out.append(f"{caption_prefix}{_distinct_values(rows[0])[0]}{caption_prefix[::-1]}")
        rows.pop(0)
    if len(rows[0]) == 1 or (len(rows) == 1 and is_caption_row(rows[0])):
        return "\n".join(out + [v for r in rows for v in _distinct_values(r)])
    if any(is_form_row(r) for r in rows[:1]):
        return "\n".join(out + ["; ".join(_distinct_values(r)) for r in rows])
    labels, used = _header(rows)
    width = len(labels)
    lines = ["| " + " | ".join(labels) + " |", "| " + " | ".join(["---"] * width) + " |"]
    for r in rows[used:]:
        lines.append("| " + " | ".join(_data_row(r)) + " |")
    # The caption is its own block (a heading for the chunker), so the table block starts with its header row
    # and the chunker repeats that header in every chunk of the table.
    return "\n\n".join(out + ["\n".join(lines)])


def split_blocks(rows: Sequence[Sequence[GridCell]]) -> List[List[List[GridCell]]]:
    """
    Several tables in one sheet: a new table starts after an empty row when the next row is a caption.
    An empty row inside a table (spacing) does not split it.
    """
    blocks: List[List[List[GridCell]]] = [[]]
    gap = False
    for r in rows:
        if not any(c.text for c in r):
            gap = True
            continue
        if gap and blocks[-1] and is_caption_row(r):
            blocks.append([])
        blocks[-1].append(list(r))
        gap = False
    return [b for b in blocks if b]


def grid_from_strings(rows: Sequence[Sequence[Optional[str]]]) -> List[List[GridCell]]:
    """Grid without merge information (cells are independent)."""
    return [[GridCell(clean(v)) for v in r] for r in rows]


def grid_from_pdf(rows: Sequence[Sequence[Optional[str]]], table_id: Any) -> List[List[GridCell]]:
    """
    PyMuPDF `Table.extract()` rows: a cell covered by a merged region is None. It continues the region on
    its left (horizontal span, the case that matters for headers and captions), else the one above.
    """
    grid: List[List[GridCell]] = []
    for r, row in enumerate(rows):
        out: List[GridCell] = []
        for c, v in enumerate(row):
            if v is None and c > 0:
                if out[-1].key is None:  # the left cell starts a merged region
                    out[-1] = GridCell(out[-1].text, (table_id, r, c - 1))
                out.append(out[-1])
            elif v is None and r > 0 and c < len(grid[r - 1]):
                if grid[r - 1][c].key is None:
                    grid[r - 1][c] = GridCell(grid[r - 1][c].text, (table_id, r - 1, c))
                out.append(grid[r - 1][c])
            else:
                out.append(GridCell(clean(v)))
        grid.append(out)
    return grid


def _single_value(cells: Sequence[GridCell]) -> Optional[str]:
    values = _distinct_values(cells)
    return values[0] if len(values) == 1 else ("" if not values else None)


def append_columns(left: List[List[GridCell]], right: List[List[GridCell]], region: Any) -> List[List[GridCell]]:
    """
    Columns of the same rows printed on a later page (a spreadsheet printed wider than the page) joined to the
    first part. A caption cut in two ("BẢNG" | "1: TIÊU CHÍ …") becomes one caption again.
    """
    out = []
    for r, (a, b) in enumerate(zip(left, right, strict=True)):  # callers join tables with equal row counts
        va, vb = _single_value(a), _single_value(b)
        if va is not None and vb is not None and (va or vb):
            text = " ".join(v for v in (va, vb) if v)
            cell = GridCell(text, (region, r))
            out.append([cell] * (len(a) + len(b)))
        else:
            out.append(list(a) + list(b))
    return out
