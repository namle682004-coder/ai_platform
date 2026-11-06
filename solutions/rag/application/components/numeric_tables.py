"""
Exact answers to numeric questions over tables (highest, lowest, difference, total, average, ranking).

Language models estimate and invent figures when asked to compare numbers across passages. Here the
tables of a document are parsed back into rows, numeric columns are detected from their values, and
an LLM only *chooses* the tables, the column and the operation (as JSON, against the schema of what
exists). The arithmetic is done in code and the answer is rendered with the original cell values, so
every figure shown is either copied from the document or computed from it.

Nothing is specific to a document: column names, table titles (section breadcrumbs) and row labels
are read from the tenant's own tables; totals rows are detected arithmetically, not by name.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .context_selector import chunk_order_key, payload_of
from .lexical_evidence import candidate_heading, candidate_text, normalize_for_match
from .table_rows import parse_table_rows

PLANNER_MARKER = "[NUMERIC_PLANNER]"
OPERATIONS = ("max", "min", "diff", "sum", "avg", "sort_desc", "sort_asc", "lookup")
_BREADCRUMB_RE = re.compile(r"^\s*\[(?:Ngữ cảnh|Tài liệu)\s*:\s*([^\]\n]*)\]")
# A cell that is a figure: digits with thousand/decimal separators and an optional magnitude/percent sign.
_NUMERIC_CELL_RE = re.compile(r"^\s*([+-]?\d{1,3}(?:[.,]\d{3})+|[+-]?\d+(?:[.,]\d+)?)\s*([kKmM%‰])?\s*$")
NUMERIC_COLUMN_MIN_RATIO = 0.6
SCHEMA_MAX_TABLES = 80
SCHEMA_MAX_ROW_LABELS = 12
SORT_MAX_ROWS = 15
_INVISIBLE_RE = re.compile("[﻿​‌‍­]")


def parse_number(cell: str) -> Optional[float]:
    """Value of a figure cell ("3,5k" -> 3500, "1.234" -> 1234, "12%" -> 12), None if not a figure."""
    m = _NUMERIC_CELL_RE.match(cell or "")
    if not m:
        return None
    digits, suffix = m.group(1), (m.group(2) or "")
    mult = 1000.0 if suffix in ("k", "K") else 1_000_000.0 if suffix in ("m", "M") else 1.0
    if re.fullmatch(r"[+-]?\d{1,3}(?:[.,]\d{3})+", digits) and not suffix:
        value = float(re.sub(r"[.,]", "", digits))  # thousands separators
    else:
        last = max(digits.rfind("."), digits.rfind(","))
        if last == -1:
            value = float(digits)
        else:
            value = float(re.sub(r"[.,]", "", digits[:last]) + "." + digits[last + 1:])
    return value * mult


def format_number(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return f"{int(round(value)):,}".replace(",", ".")
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".").rstrip("0").rstrip(",")


def chunk_path(chunk: Any) -> str:
    m = _BREADCRUMB_RE.match(candidate_text(chunk) or "")
    if m and m.group(1).strip():
        return m.group(1).strip()
    p = payload_of(chunk)
    return str(p.get("heading_path") or candidate_heading(chunk) or "").strip()


@dataclass
class NumRow:
    label: str
    cells: List[str]
    values: Dict[int, float]
    is_total: bool = False
    raw_label: str = ""  # the label cell as written (label may get a disambiguating suffix)


@dataclass
class NumTable:
    id: int
    doc_id: str
    title: str  # last breadcrumb segment (what the table is about)
    path: str  # full breadcrumb (section > subsection > title)
    columns: List[str]
    label_column: int
    numeric_columns: List[int]
    rows: List[NumRow] = field(default_factory=list)
    sources: List[Any] = field(default_factory=list)

    def column_index(self, name: str) -> Optional[int]:
        n = normalize_for_match(name)
        if not n:
            return None
        for i in self.numeric_columns:
            if normalize_for_match(self.columns[i]) == n:
                return i
        for i in self.numeric_columns:
            c = normalize_for_match(self.columns[i])
            if n in c or c in n:
                return i
        return None

    def data_rows(self) -> List[NumRow]:
        return [r for r in self.rows if not r.is_total]


def _merge_header(header: List[str], row: List[str]) -> Optional[List[str]]:
    """Second header row of a two-level header (no figures, repeats some header cells)."""
    if any(parse_number(c) is not None for c in row):
        return None
    same = sum(1 for a, b in zip(header, row, strict=False) if a and a == b)
    if same < 2:
        return None
    return [b or a for a, b in zip(header, row, strict=False)]


def _mark_totals(rows: List[NumRow], numeric_columns: List[int]) -> None:
    """
    A totals row is detected arithmetically: in columns where at least two other rows have figures, its
    figure equals their sum more often than not (columns of merged cells repeated per row do not add up).
    """
    if len(rows) < 3:
        return
    for r in rows:
        others = [o for o in rows if o is not r]
        hits = misses = 0
        for c in numeric_columns:
            contributors = [o.values[c] for o in others if c in o.values]
            if c not in r.values or len(contributors) < 2:
                continue
            if abs(r.values[c] - sum(contributors)) < 1e-6:
                hits += 1
            else:
                misses += 1
        r.is_total = hits >= 1 and hits >= misses


def _disambiguate_labels(table: NumTable) -> None:
    """Rows sharing a label (same source, several items) get the next text cell appended."""
    counts: Dict[str, int] = {}
    for r in table.rows:
        counts[r.label] = counts.get(r.label, 0) + 1
    text_cols = [i for i in range(len(table.columns)) if i not in table.numeric_columns and i != table.label_column]
    for r in table.rows:
        if counts.get(r.label, 0) > 1 or not r.label:
            extra = next((r.cells[i].strip() for i in text_cols
                          if i < len(r.cells) and r.cells[i].strip() and parse_number(r.cells[i]) is None
                          and len(r.cells[i].strip()) > 3), "")
            if extra:
                r.label = f"{r.label} – {extra}" if r.label else extra


def _clean_cell(cell: str) -> str:
    return _INVISIBLE_RE.sub("", cell or "").strip()


def parse_numeric_tables(chunks: Sequence[Any]) -> List[NumTable]:
    """
    Tables with at least one numeric column, in document order. A table continued over several chunks
    (same section, same first header row) is one table; a two-level header (second header row without
    figures repeating cells of the first) is merged. Numeric columns are decided over all rows.
    """
    groups: Dict[Tuple[str, str, Tuple[str, ...]], Dict[str, Any]] = {}
    order: List[Tuple[str, str, Tuple[str, ...]]] = []
    for chunk in sorted(chunks, key=chunk_order_key):
        rows = parse_table_rows([chunk])
        if not rows:
            continue
        path = _clean_cell(chunk_path(chunk))
        raw_header = [_clean_cell(c) for c in rows[0].columns]
        data = [[_clean_cell(c) for c in r.cells] for r in rows]
        key = (str(payload_of(chunk).get("doc_id") or ""), path, tuple(raw_header))
        g = groups.get(key)
        if g is None:
            g = {"header": raw_header, "data": [], "sources": []}
            groups[key] = g
            order.append(key)
        if data:
            merged = _merge_header(raw_header, data[0])
            if merged:
                g["header"], data = merged, data[1:]
        g["data"] += [d for d in data if d != raw_header and d != g["header"]]
        g["sources"].append(chunk)

    tables: List[NumTable] = []
    for key in order:
        g = groups[key]
        header, data = g["header"], g["data"]
        if not data:
            continue
        numeric_cols = []
        for i in range(len(header)):
            cells = [d[i] for d in data if i < len(d) and d[i]]
            if cells and sum(1 for c in cells if parse_number(c) is not None) / len(cells) >= NUMERIC_COLUMN_MIN_RATIO:
                numeric_cols.append(i)
        if not numeric_cols:
            continue
        # Label column: the text column filled in most rows (leftmost on ties).
        text_cols = [i for i in range(len(header)) if i not in numeric_cols]
        label_col = max(text_cols, key=lambda i: (sum(1 for d in data if i < len(d) and d[i]), -i)) if text_cols else 0
        path = key[1]
        table = NumTable(
            id=len(tables), doc_id=key[0], title=path.split(">")[-1].strip() or path, path=path,
            columns=[h or f"Cột {i + 1}" for i, h in enumerate(header)], label_column=label_col,
            numeric_columns=numeric_cols, sources=list(g["sources"]),
        )
        for d in data:
            values = {i: v for i in numeric_cols if i < len(d) for v in [parse_number(d[i])] if v is not None}
            if values:
                label = d[label_col] if label_col < len(d) else ""
                table.rows.append(NumRow(label=label, cells=d, values=values, raw_label=label))
        _disambiguate_labels(table)
        _mark_totals(table.rows, numeric_cols)
        if table.data_rows():
            tables.append(table)
    return tables


# ------------------------------------------------------------------ planning
SCHEMA_TITLE_CHARS = 70
SCHEMA_MAX_FAMILY_TABLES = 40


def table_families(tables: Sequence[NumTable]) -> List[List[NumTable]]:
    """
    Tables sharing the same columns are one logical table split by section (one small table per article,
    per event, per unit…). Listing them once keeps the planner's schema inside a small model's window,
    and a question over "the articles" is answered over all of them, not over the ones the planner recalled.
    """
    fams: Dict[Tuple[str, ...], List[NumTable]] = {}
    for t in tables:
        fams.setdefault(tuple(normalize_for_match(c) for c in t.columns), []).append(t)
    return list(fams.values())


def schema_text(tables: Sequence[NumTable]) -> str:
    out = []
    for fam in table_families(tables[:SCHEMA_MAX_TABLES]):
        first = fam[0]
        labels: List[str] = []
        for t in fam:
            for r in t.data_rows():
                lab = (r.raw_label or r.label)[:80]
                if lab and lab not in labels:
                    labels.append(lab)
        entry: Dict[str, Any] = {"numeric_columns": [first.columns[i] for i in first.numeric_columns]}
        if len(fam) == 1:
            entry.update(id=first.id, path=first.path)
        else:
            section = first.path.split(">")[0].strip() if ">" in first.path else ""
            entry["tables"] = [{"id": t.id, "title": t.title[:SCHEMA_TITLE_CHARS]} for t in fam[:SCHEMA_MAX_FAMILY_TABLES]]
            if section and all(t.path.split(">")[0].strip() == section for t in fam):
                entry["section"] = section
        entry["row_labels"] = labels[:SCHEMA_MAX_ROW_LABELS]
        out.append(entry)
    return json.dumps(out, ensure_ascii=False)


def _title_named(title: str, question: str) -> bool:
    """The question names this table (its title, or most of its words)."""
    t, q = normalize_for_match(title), f" {normalize_for_match(question)} "
    if not t:
        return False
    if f" {t} " in q:
        return True
    tokens = [w for w in dict.fromkeys(t.split()) if len(w) >= 2]
    hits = sum(1 for w in tokens if f" {w} " in q)
    return len(tokens) >= 2 and hits >= 2 and hits / len(tokens) >= 0.6


def expand_to_families(chosen: Sequence[NumTable], tables: Sequence[NumTable], question: str) -> List[NumTable]:
    """
    A planner choosing some tables of a family for a question that names none of them meant the whole
    family ("which article has the most comments" is over every article, not the three it listed).
    """
    picked = list(chosen)
    for fam in table_families(tables):
        ids = {t.id for t in fam}
        if len(fam) < 2 or not ids & {t.id for t in picked}:
            continue
        if any(_title_named(t.title, question) for t in fam):
            continue
        picked += [t for t in fam if t.id not in {p.id for p in picked}]
    return sorted(picked, key=lambda t: t.id)


def label_named(label: str, question: str) -> bool:
    """The question names this row (the label, or most of its words)."""
    return _title_named(label, question)


def column_named(column: str, question: str) -> bool:
    """Most words of a column header appear in the question ("lượt bình luận", "số … bài")."""
    tokens = [w for w in dict.fromkeys(normalize_for_match(column).split()) if len(w) >= 2]
    q = f" {normalize_for_match(question)} "
    hits = sum(1 for w in tokens if f" {w} " in q)
    return bool(tokens) and hits >= min(2, len(tokens)) and hits * 3 >= len(tokens) * 2


def planner_messages(question: str, tables: Sequence[NumTable], aggregate_hint: str = "") -> List[Dict[str, str]]:
    system = (
        f"{PLANNER_MARKER} Bạn chọn dữ liệu để TRẢ LỜI CHÍNH XÁC câu hỏi về số liệu từ các bảng của tài liệu. "
        "Chỉ chọn, KHÔNG tính toán. Trả về DUY NHẤT JSON:\n"
        '{"applicable": true, "tables": [id], "column": "", "operation": "", "unit": "row", "table_reduce": "sum", "rows": []}\n'
        "- applicable: true khi câu hỏi được trả lời bằng các số trong các bảng dưới đây; false nếu không.\n"
        "- tables: id các bảng thuộc phạm vi câu hỏi (dựa vào path/title – mục/chủ đề của bảng). Các bảng cùng cột được "
        "gom trong một mục 'tables'; phạm vi rộng (cả một nhóm/mục, mọi bài) thì chọn mọi bảng của mục đó.\n"
        "- column: tên cột số cần dùng, chép đúng từ numeric_columns.\n"
        "- operation: max | min | diff (chênh lệch giữa lớn nhất và nhỏ nhất) | sum | avg | sort_desc | sort_asc | lookup "
        "(chỉ đọc giá trị).\n"
        "- unit: 'row' khi so sánh các dòng (ví dụ các nguồn/đơn vị trong bảng); 'table' khi so sánh các bảng với nhau "
        "(ví dụ bài/mục nào cao nhất), khi đó mỗi bảng được gộp theo table_reduce ('sum' hoặc 'max').\n"
        "- rows: nhãn dòng cần giới hạn (chép đúng từ row_labels), rỗng nếu dùng mọi dòng."
    )
    user = f"BẢNG: {schema_text(tables)}\n"
    if aggregate_hint:
        user += f"GỢI Ý PHÉP TÍNH: {aggregate_hint}\n"
    user += f"CÂU HỎI: {question}\n\nJSON:"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


@dataclass
class NumericPlan:
    tables: List[NumTable]
    column: str
    operation: str
    unit: str
    table_reduce: str
    rows: List[str]


def parse_plan(raw: str, tables: Sequence[NumTable]) -> Optional[NumericPlan]:
    s = (raw or "").strip()
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(s[start:end + 1])
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    applicable = data.get("applicable", False)
    if isinstance(applicable, str):
        applicable = applicable.strip().lower() == "true"
    if not applicable:
        return None
    by_id = {t.id: t for t in tables}
    ids = data.get("tables") if isinstance(data.get("tables"), list) else []
    chosen = [by_id[i] for i in (int(x) for x in ids if str(x).strip().lstrip("-").isdigit()) if i in by_id]
    column = str(data.get("column") or "").strip()
    chosen = [t for t in chosen if t.column_index(column) is not None]
    operation = str(data.get("operation") or "").strip().lower()
    if not chosen or operation not in OPERATIONS:
        return None
    rows = [str(r).strip() for r in data.get("rows") or [] if str(r).strip()] if isinstance(data.get("rows"), list) else []
    unit = "table" if str(data.get("unit") or "").strip().lower() == "table" and len(chosen) > 1 else "row"
    reduce = "max" if str(data.get("table_reduce") or "").strip().lower() == "max" else "sum"
    return NumericPlan(tables=chosen, column=column, operation=operation, unit=unit, table_reduce=reduce, rows=rows)


# ------------------------------------------------------------------ computation & rendering
@dataclass
class Entry:
    label: str
    value: float
    shown: str  # value as written in the document (or computed, for table totals)
    table: NumTable
    raw_label: str = ""


def _row_matches(label: str, wanted: Sequence[str]) -> bool:
    if not wanted:
        return True
    nl = normalize_for_match(label)
    return any(normalize_for_match(w) and (normalize_for_match(w) in nl or nl in normalize_for_match(w)) for w in wanted)


def entries_for(plan: NumericPlan) -> List[Entry]:
    out: List[Entry] = []
    for t in plan.tables:
        col = t.column_index(plan.column)
        rows = [r for r in t.data_rows() if col in r.values and _row_matches(r.label, plan.rows)]
        if not rows:
            continue
        if plan.unit == "table":
            vals = [r.values[col] for r in rows]
            v = sum(vals) if plan.table_reduce == "sum" else max(vals)
            shown = format_number(v) if plan.table_reduce == "sum" and len(rows) > 1 else rows[vals.index(v)].cells[col]
            out.append(Entry(label=t.title, value=v, shown=shown, table=t))
        else:
            for r in rows:
                label = r.label if len(plan.tables) == 1 else f"{r.label} ({t.title})"
                out.append(Entry(label=label, value=r.values[col], shown=r.cells[col].strip(), table=t,
                                 raw_label=r.raw_label or r.label))
    return _collapse_repeated(out) if plan.unit == "row" else out


def _collapse_repeated(entries: List[Entry]) -> List[Entry]:
    """
    Rows repeating one label with the same figure carry an attribute of that label, written once per row
    of a merged cell (a source's post count beside each of its posts): it is one entry, not several.
    """
    by_label: Dict[str, List[Entry]] = {}
    for e in entries:
        by_label.setdefault(normalize_for_match(e.raw_label), []).append(e)
    out: List[Entry] = []
    seen = set()
    for e in entries:
        key = normalize_for_match(e.raw_label)
        group = by_label.get(key, [e])
        if key and len(group) > 1 and len({g.value for g in group}) == 1:
            if key in seen:
                continue
            seen.add(key)
            out.append(Entry(label=e.raw_label, value=e.value, shown=e.shown, table=e.table, raw_label=e.raw_label))
        else:
            out.append(e)
    return out


def compute_answer(plan: NumericPlan, max_rows: int = SORT_MAX_ROWS) -> Optional[Tuple[str, List[Any]]]:
    """
    (markdown answer, source chunks) – every figure is a document cell or computed from cells.
    `max_rows`: rows shown in the table (a "list all" question shows them all).
    """
    entries = entries_for(plan)
    if not entries:
        return None
    col_name = plan.tables[0].columns[plan.tables[0].column_index(plan.column)]
    scope = plan.tables[0].path if len(plan.tables) == 1 else ", ".join(dict.fromkeys(t.path.split(">")[0].strip() for t in plan.tables))
    basis = "tổng các dòng của mỗi bảng" if plan.unit == "table" and plan.table_reduce == "sum" else ""
    lines: List[str] = []
    op = plan.operation
    if op in ("max", "min"):
        best = max(e.value for e in entries) if op == "max" else min(e.value for e in entries)
        winners = [e for e in entries if abs(e.value - best) < 1e-9]
        word = "cao nhất" if op == "max" else "thấp nhất"
        names = "; ".join(f"**{e.label}**" for e in winners)
        lines.append(f"Theo tài liệu ({scope}), {names} có «{col_name}» {word}: **{winners[0].shown}**.")
    elif op == "diff":
        hi = max(entries, key=lambda e: e.value)
        lo = min(entries, key=lambda e: e.value)
        lines.append(
            f"Theo tài liệu ({scope}), «{col_name}» cao nhất là **{hi.label}** ({hi.shown}), thấp nhất là "
            f"**{lo.label}** ({lo.shown}); chênh lệch **{format_number(hi.value - lo.value)}**."
        )
    elif op == "sum":
        lines.append(f"Theo tài liệu ({scope}), tổng «{col_name}» là **{format_number(sum(e.value for e in entries))}**.")
    elif op == "avg":
        lines.append(
            f"Theo tài liệu ({scope}), trung bình «{col_name}» là **{format_number(sum(e.value for e in entries) / len(entries))}**."
        )
    else:
        lines.append(f"Theo tài liệu ({scope}), «{col_name}»:")
    if basis:
        lines.append(f"(Giá trị mỗi mục là {basis}.)")
    ordered = entries
    if op in ("max", "sort_desc", "diff"):
        ordered = sorted(entries, key=lambda e: e.value, reverse=True)
    elif op in ("min", "sort_asc"):
        ordered = sorted(entries, key=lambda e: e.value)
    shown = ordered[:max(1, max_rows)]
    lines += ["", f"| Mục | {col_name} |", "| --- | --- |"]
    lines += [f"| {e.label} | {e.shown} |" for e in shown]
    if len(ordered) > len(shown):
        lines.append(f"\n(Còn {len(ordered) - len(shown)} mục khác.)")
    sources: List[Any] = []
    for t in dict.fromkeys(e.table.id for e in entries):
        sources += next(x for x in plan.tables if x.id == t).sources
    return "\n".join(lines), sources
