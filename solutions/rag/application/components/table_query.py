"""
Questions over stored tables answered in code: filter rows by column conditions, then list, count or
aggregate. An LLM only maps the question to a plan (tables, conditions, operation) against the schema of the
candidate tables; every row it returns, every count and every figure is computed here, so the same question
gets the same complete answer each time.

- A plan names tables of the schema; every stored table with the same columns (the same template in other
  documents) is included, so "which positions require level 4" reads the table of every position.
- Rows that are sums of the others (`TableRecord.total_rows`) are never counted as data.
- Summing a column whose value is repeated on each row of a merged cell counts that value once per merge
  (the run of rows that also repeats the merged label), not once per row.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .lexical_evidence import normalize_for_match
from .table_store import TableRecord, merged_heads, parse_number

OPERATIONS = ("list", "count", "sum", "avg", "min", "max")
DOCUMENT_COLUMN = "Tài liệu"  # pseudo-column: the title of the document holding the table
DOC = -1
COMPARATORS = ("=", "!=", ">", ">=", "<", "<=", "contains", "nonempty", "empty")
SCHEMA_SAMPLE_VALUES = 8
SCHEMA_MAX_TABLES = 40


@dataclass
class Condition:
    column: str
    op: str
    value: str = ""


@dataclass
class TableQuery:
    table_ids: List[int]
    operation: str
    conditions: List[Condition] = field(default_factory=list)
    target: str = ""  # column aggregated by sum / avg / min / max
    show: List[str] = field(default_factory=list)  # columns shown for each listed row
    expand_family: bool = True


@dataclass
class Match:
    table: TableRecord
    row: List[str]


@dataclass
class QueryResult:
    operation: str
    matches: List[Match]
    value: Optional[float] = None
    tables: List[TableRecord] = field(default_factory=list)
    show: List[int] = field(default_factory=list)  # resolved column indexes shown (first table's columns)

    @property
    def documents(self) -> List[str]:
        return list(dict.fromkeys(m.table.title for m in self.matches))


# ------------------------------------------------------------------ columns and conditions
def column_index(table: TableRecord, name: str) -> Optional[int]:
    """
    Exact name first, then a name that is the last part ('Trung tính' for 'Sắc thái / Trung tính'), then
    containment. Each step compares with diacritics before without them: "Mức" and "Mục" are different
    columns that only match each other once the accents are stripped.
    """
    exact = " ".join(unicodedata.normalize("NFC", name or "").lower().split())
    accented = [" ".join(unicodedata.normalize("NFC", c).lower().split()) for c in table.columns]
    for i, c in enumerate(accented):
        if c == exact or c.split(" / ")[-1] == exact:
            return i
    n = normalize_for_match(name)
    if not n:
        return None
    cols = [normalize_for_match(c) for c in table.columns]
    for i, c in enumerate(cols):
        if c == n:
            return i
    for i, c in enumerate(cols):
        if c.split(" / ")[-1] == n or normalize_for_match(table.columns[i].split("/")[-1]) == n:
            return i
    for i, c in enumerate(cols):
        if n in c or (c and c in n):
            return i
    return None


def _holds(cell: str, cond: Condition) -> bool:
    cell = (cell or "").strip()
    if cond.op == "nonempty":
        return bool(cell)
    if cond.op == "empty":
        return not cell
    a, b = parse_number(cell), parse_number(cond.value)
    if cond.op in (">", ">=", "<", "<="):
        if a is None or b is None:
            return False
        return {">": a > b, ">=": a >= b, "<": a < b, "<=": a <= b}[cond.op]
    if cond.op in ("=", "!="):
        same = (a == b) if (a is not None and b is not None) else normalize_for_match(cell) == normalize_for_match(cond.value)
        return same if cond.op == "=" else not same
    if cond.op == "contains":
        return normalize_for_match(cond.value) in normalize_for_match(cell)
    return False


def _family(tables: Sequence[TableRecord], chosen: Sequence[TableRecord]) -> List[TableRecord]:
    signatures = {t.signature for t in chosen}
    return [t for t in tables if t.signature in signatures]


def _total_of(table: TableRecord, target: int) -> Optional[float]:
    """The document's own total for a column (its arithmetically detected totals row), if any."""
    for r in table.total_rows:
        v = parse_number(table.rows[r][target]) if target < len(table.rows[r]) else None
        if v is not None:
            return v
    return None


def _sum_rows(table: TableRecord, hits: List[int], target: int, whole_table: bool) -> List[int]:
    """
    Rows whose figure is added. Markdown keeps no merge information, so a figure repeated on consecutive
    rows is either one merged cell or equal figures of distinct rows. The document decides when it can:
    over the whole table, the reading that matches its own totals row is used.
    """
    collapsed = _merged_runs(table, hits, target)
    if collapsed == hits:
        return hits
    total = _total_of(table, target) if whole_table else None
    if total is not None:
        def value(rows: List[int]) -> float:
            return sum(v for v in (parse_number(table.rows[r][target]) for r in rows) if v is not None)

        if abs(value(hits) - total) < 1e-6:
            return hits
        if abs(value(collapsed) - total) < 1e-6:
            return collapsed
    return collapsed


def _merged_runs(table: TableRecord, rows: List[int], target: int) -> List[int]:
    """One row per merged cell of the target column (see table_store.merged_heads)."""
    return merged_heads(table.rows, rows, target)


def run_query(tables: Sequence[TableRecord], query: TableQuery) -> Optional[QueryResult]:
    """Executes a plan; None when it cannot be executed (unknown table / column / operation)."""
    if query.operation not in OPERATIONS:
        return None
    chosen = [tables[i] for i in query.table_ids if 0 <= i < len(tables)]
    if not chosen:
        return None
    scope = _family(tables, chosen) if query.expand_family else chosen
    result = QueryResult(operation=query.operation, matches=[], tables=scope)
    figures: List[float] = []
    for t in scope:
        # DOCUMENT_COLUMN filters on the document a row comes from (tables of one template in many documents).
        conds = [(DOC if normalize_for_match(c.column) == normalize_for_match(DOCUMENT_COLUMN) else column_index(t, c.column), c)
                 for c in query.conditions]
        if any(i is None for i, _ in conds) or any(c.op not in COMPARATORS for _, c in conds):
            return None
        target = column_index(t, query.target) if query.target else None
        if query.operation in ("sum", "avg", "min", "max") and target is None:
            return None
        hits = [r for r, row in enumerate(t.rows)
                if r not in t.total_rows and all(_holds(t.title if i == DOC else row[i], c) for i, c in conds)]
        result.matches.extend(Match(t, t.rows[r]) for r in hits)
        if target is not None:
            rows = (_sum_rows(t, hits, target, whole_table=not query.conditions)
                    if query.operation in ("sum", "avg") else hits)
            figures.extend(v for v in (parse_number(t.rows[r][target]) for r in rows) if v is not None)
    if query.operation == "count":
        result.value = float(len(result.matches))
    elif query.operation in ("sum", "avg", "min", "max"):
        if not figures:
            return None
        result.value = {"sum": sum(figures), "avg": sum(figures) / len(figures),
                        "min": min(figures), "max": max(figures)}[query.operation]
    first = scope[0]
    result.show = [i for i in (column_index(first, s) for s in query.show) if i is not None]
    return result


# ------------------------------------------------------------------ rendering
def format_number(v: float) -> str:
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:.2f}".rstrip("0").rstrip(",.").replace(".", ",")


def render_result(result: QueryResult, max_rows: int = 200) -> str:
    """Deterministic answer text: the figure, then the rows it rests on (document named when several)."""
    many_docs = len(result.documents) > 1
    n = len(result.matches)
    lines: List[str] = []
    if result.operation == "count":
        lines.append(f"Có **{n}** dòng thỏa điều kiện.")
    elif result.operation in ("sum", "avg", "min", "max") and result.value is not None:
        label = {"sum": "Tổng", "avg": "Trung bình", "min": "Nhỏ nhất", "max": "Lớn nhất"}[result.operation]
        lines.append(f"{label}: **{format_number(result.value)}** (tính trên {n} dòng).")
    else:
        lines.append(f"Có **{n}** dòng thỏa điều kiện:" if n else "Không có dòng nào thỏa điều kiện.")
    if result.operation in ("list", "count") or n <= 20:
        for m in result.matches[:max_rows]:
            cells = [m.row[i] for i in result.show if i < len(m.row) and m.row[i]] or [c for c in m.row if c][:3]
            prefix = f"{m.table.title}: " if many_docs else ""
            lines.append(f"- {prefix}{' | '.join(cells)}")
        if n > max_rows:
            lines.append(f"- … và {n - max_rows} dòng khác.")
    return "\n".join(lines)


# ------------------------------------------------------------------ planning (LLM chooses, code computes)
def _sample_values(table: TableRecord, col: int) -> List[str]:
    values = list(dict.fromkeys(r[col] for k, r in enumerate(table.rows) if r[col] and k not in table.total_rows))
    return values[:SCHEMA_SAMPLE_VALUES] if len(values) <= 3 * SCHEMA_SAMPLE_VALUES else []


def schema_text(tables: Sequence[TableRecord]) -> str:
    """One entry per kind of table (same columns); the documents holding it are named."""
    lines, seen = [], {}
    for i, t in enumerate(tables[:SCHEMA_MAX_TABLES]):
        if t.signature in seen:
            seen[t.signature].append(t.title)
            continue
        seen[t.signature] = [t.title]
        cols = []
        for c, name in enumerate(t.columns):
            sample = _sample_values(t, c)
            cols.append(f"{name}" + (f" (giá trị: {', '.join(sample)})" if sample else ""))
        where = " > ".join(p for p in (t.section, t.caption) if p)
        lines.append(f"[{i}] {where or t.title} – {len(t.rows)} dòng; cột: " + "; ".join(cols))
    for names in (n for n in seen.values() if len(n) > 1):
        lines.append(f"(Bảng cùng cấu trúc có trong {len(names)} tài liệu: {', '.join(names[:12])}…)")
    return "\n".join(lines)


def planner_messages(question: str, tables: Sequence[TableRecord]) -> List[Dict[str, str]]:
    system = (
        "Bạn lập kế hoạch truy vấn bảng cho câu hỏi. Không trả lời câu hỏi, không tính toán. Trả về DUY NHẤT JSON:\n"
        '{"applicable": true, "tables": [id], "operation": "list|count|sum|avg|min|max", '
        '"conditions": [{"column": "", "op": "=|!=|>|>=|<|<=|contains|nonempty|empty", "value": ""}], '
        '"target": "", "show": []}\n'
        "- applicable=false nếu câu hỏi không lọc / đếm / liệt kê / tính trên các bảng này.\n"
        "- tables: id của bảng chứa dữ liệu cần dùng.\n"
        "- conditions: điều kiện lọc dòng theo tên cột đúng như schema; ô đánh dấu (vd '1', 'x') dùng op 'nonempty'. "
        f"Cột '{DOCUMENT_COLUMN}' lọc theo tên tài liệu chứa bảng (op 'contains') khi câu hỏi nêu một tài liệu cụ thể.\n"
        "- target: cột số khi operation là sum/avg/min/max.\n"
        "- show: các cột cần hiển thị cho mỗi dòng khi liệt kê."
    )
    user = f"SCHEMA:\n{schema_text(tables)}\n\nCÂU HỎI: {question.strip()}\n\nJSON:"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_plan(raw: str) -> Optional[TableQuery]:
    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None
    if not data.get("applicable"):
        return None
    try:
        conds = [Condition(str(c.get("column", "")), str(c.get("op", "=")), str(c.get("value", "")))
                 for c in data.get("conditions") or [] if isinstance(c, dict)]
        return TableQuery(
            table_ids=[int(x) for x in data.get("tables") or []],
            operation=str(data.get("operation") or "").lower(),
            conditions=conds,
            target=str(data.get("target") or ""),
            show=[str(s) for s in data.get("show") or []],
        )
    except (TypeError, ValueError):
        return None
