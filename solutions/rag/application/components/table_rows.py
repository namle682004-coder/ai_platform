"""
Structured view of tabular documents for listing / comparison questions (self-query retrieval).

Chunks of a document that contain markdown tables are parsed back into rows (column names come from
each table's own header row, the section from the chunk heading) and every identifier-bearing cell is
split into items ("<identifier>. <text>"). An LLM receives only the schema of what exists (sections,
group values, sample identifiers) and returns a filter plan as JSON; the filter is applied in code and
the answer is rendered deterministically, so a listing can neither drop a row nor invent one.

Nothing here knows the vocabulary of a particular document: column names, section names, identifier
shapes and group values are all read from the tenant's own tables.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .context_selector import chunk_order_key, payload_of
from .lexical_evidence import IDENTIFIER_RE, candidate_heading, candidate_text, normalize_for_match, unique_in_order
from .prompt_builder import strip_breadcrumb

logger = logging.getLogger("aip-rag.table-rows")

PLANNER_MARKER = "[TABLE_PLANNER]"
_DELIMITER_ROW_RE = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_SAFE_REGEX_RE = re.compile(r"^[\w\s.\\^$*+?()\[\]{}|\-]{1,80}$")
_ITEM_HEAD_RE = re.compile(r"\.\s+[^\W\d_]", re.UNICODE)
SCHEMA_MAX_GROUPS = 60
SCHEMA_SAMPLE_IDS = 12


@dataclass
class TableRow:
    doc_id: str
    title: str
    section: str
    order: Tuple[int, int]  # (chunk_index, row position) – document order
    columns: List[str]
    cells: List[str]
    source: Any = None  # the chunk the row comes from (for citations)


@dataclass
class RowItem:
    identifier: str
    text: str  # "<identifier>. <requirement text>" exactly as written in the cell
    row: TableRow
    column: int  # index of the cell holding the item

    def context_cells(self) -> List[Tuple[str, str]]:
        """(column name, value) of the other, non-identifier cells of the row (group, content name…)."""
        out = []
        for i, (name, value) in enumerate(zip(self.row.columns, self.row.cells, strict=False)):
            if i != self.column and value and not IDENTIFIER_RE.search(value):
                out.append((name, value))
        return out

    def search_text(self) -> str:
        return " ".join([self.text, *(v for _, v in self.context_cells()), self.row.section])


def _split_cells(line: str) -> List[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [_BR_RE.sub(" ", c).strip() for c in body.split("|")]


def parse_table_rows(chunks: Sequence[Any]) -> List[TableRow]:
    """Rows of every markdown table in `chunks`, in document order; empty leading cells are filled down."""
    rows: List[TableRow] = []
    for chunk in sorted(chunks, key=chunk_order_key):
        p = payload_of(chunk)
        text = strip_breadcrumb(candidate_text(chunk))
        if "|" not in text:
            continue
        section = (candidate_heading(chunk) or "").strip()
        lines = text.splitlines()
        header: Optional[List[str]] = None
        previous: Optional[List[str]] = None
        for i, line in enumerate(lines):
            if not line.strip().startswith("|"):
                header, previous = None, None
                continue
            if _DELIMITER_ROW_RE.match(line.strip()):
                continue
            cells = _split_cells(line)
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if header is None and _DELIMITER_ROW_RE.match(nxt):
                header = cells
                continue
            if header is None:
                header = [f"Cột {k + 1}" for k in range(len(cells))]
            cells = (cells + [""] * len(header))[: len(header)]
            if previous and any(IDENTIFIER_RE.search(c) for c in cells):
                # Rowspan style: an empty leading cell repeats the value above it.
                for k, value in enumerate(cells):
                    if value:
                        break
                    cells[k] = previous[k]
            previous = cells
            rows.append(TableRow(
                doc_id=str(p.get("doc_id") or ""), title=str(p.get("title") or ""), section=section,
                order=(int(p.get("chunk_index", 0) or 0), i), columns=header, cells=cells, source=chunk,
            ))
    return rows


def row_items(rows: Sequence[TableRow]) -> List[RowItem]:
    """Every identifier of a row as its own item: the cell text from the identifier to the next one."""
    items: List[RowItem] = []
    seen = set()
    for row in rows:
        for col, cell in enumerate(row.cells):
            matches = list(IDENTIFIER_RE.finditer(cell))
            # Identifiers mentioned inside running text (not at an item start) are references, not items.
            # An item starts the cell, follows the end of the previous item, or heads its own text
            # ("<id>. <text>", also after an ellipsis or a closing bracket).
            starts = [m for m in matches if m.start() == 0
                      or cell[max(0, m.start() - 2):m.start()].strip() in ("", ".", ";", "…", ")")
                      or _ITEM_HEAD_RE.match(cell, m.end())]
            for k, m in enumerate(starts):
                end = starts[k + 1].start() if k + 1 < len(starts) else len(cell)
                ident = m.group(1).upper().rstrip(".-/")
                key = (row.doc_id, ident)
                if key in seen:
                    continue
                seen.add(key)
                items.append(RowItem(identifier=ident, text=cell[m.start():end].strip(" ;"), row=row, column=col))
    return items


def text_items(chunks: Sequence[Any]) -> List[Tuple[str, str, Any]]:
    """(identifier, line, chunk) for identifier-led lines outside tables (bullet lists, numbered clauses)."""
    out = []
    for chunk in chunks:
        for line in strip_breadcrumb(candidate_text(chunk)).splitlines():
            s = line.strip().lstrip("-*•+ ").strip()
            if not s or s.startswith("|"):
                continue
            m = IDENTIFIER_RE.match(s)
            if m:
                out.append((m.group(1).upper().rstrip(".-/"), s, chunk))
    return out


# ------------------------------------------------------------------ schema & planning
@dataclass
class TableSchema:
    sections: List[str]
    group_column: str
    groups: List[str]
    sample_identifiers: List[str]
    columns: List[str] = field(default_factory=list)

    def to_prompt(self) -> str:
        return json.dumps(
            {
                "sections": self.sections,
                "columns": self.columns,
                "group_column": self.group_column,
                "groups": self.groups[:SCHEMA_MAX_GROUPS],
                "sample_identifiers": self.sample_identifiers,
            },
            ensure_ascii=False,
        )


def build_schema(items: Sequence[RowItem]) -> Optional[TableSchema]:
    if not items:
        return None
    columns = items[0].row.columns
    # Group column: the first non-identifier column with repeated values (the hierarchy level above items).
    group_col = ""
    for name, _ in items[0].context_cells():
        group_col = name
        break
    groups = unique_in_order(dict(it.context_cells()).get(group_col, "") for it in items) if group_col else []
    return TableSchema(
        sections=unique_in_order(it.row.section for it in items),
        group_column=group_col,
        groups=[g for g in groups if g],
        sample_identifiers=unique_in_order(it.identifier for it in items)[:SCHEMA_SAMPLE_IDS],
        columns=list(columns),
    )


def planner_messages(question: str, schema: TableSchema, convention_text: str = "") -> List[Dict[str, str]]:
    system = (
        f"{PLANNER_MARKER} Bạn lập bộ lọc để liệt kê các mục trong bảng của tài liệu. Chỉ dùng các giá trị có trong LƯỢC ĐỒ.\n"
        "Trả về DUY NHẤT JSON:\n"
        '{"applicable": true, "level": "items|groups", "sections": [], "groups": [], "terms": [], "identifier_regex": "", '
        '"group_by": "section|group"}\n'
        "- level: 'groups' khi người dùng chỉ hỏi tên các nhóm (giá trị của group_column), 'items' khi hỏi các mục/yêu cầu cụ thể.\n"
        "- applicable: true khi câu hỏi được trả lời bằng cách liệt kê/so sánh các mục của bảng; false nếu không.\n"
        "- sections: các phần (section) cần lấy, chép đúng từ LƯỢC ĐỒ; rỗng = mọi phần.\n"
        "- groups: các nhóm cần lấy, chép đúng từ LƯỢC ĐỒ; rỗng = mọi nhóm.\n"
        "- terms: từ khoá nội dung mục phải chứa (thuật ngữ người dùng hỏi), rỗng nếu lấy hết mục của phần/nhóm.\n"
        "- identifier_regex: biểu thức chính quy (Python) trên mã mục khi người dùng chỉ hỏi một loại mục; suy ra từ "
        "QUY ƯỚC và mã mẫu; rỗng nếu lấy mọi loại.\n"
        "- group_by: 'section' khi so sánh giữa các phần, ngược lại 'group'."
    )
    user = f"LƯỢC ĐỒ: {schema.to_prompt()}\n"
    if convention_text:
        user += f"QUY ƯỚC CỦA TÀI LIỆU: {convention_text[:1200]}\n"
    user += f"CÂU HỎI: {question}\n\nJSON:"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


@dataclass
class TablePlan:
    applicable: bool
    sections: List[str]
    groups: List[str]
    terms: List[str]
    identifier_regex: Optional[re.Pattern]
    group_by: str
    level: str = "items"  # "items" | "groups"

    @property
    def has_filter(self) -> bool:
        return bool(self.sections or self.groups or self.terms or self.identifier_regex is not None)


_GROUP_CODE_RE = re.compile(r"^\s*([A-Za-z]{1,3}\d{0,3})[.)]\s")
_BARE_CODE_RE = re.compile(r"^([A-Za-z]{1,3}\d{1,3})\.?$")


def mentioned_in(value: str, question: str) -> bool:
    """
    The question names this group: by its code ("A2." or a bare "A2") or by most of the words of its name.
    A small planner tends to enumerate the groups it remembers instead of leaving the filter empty;
    groups the question does not name are not a filter the user asked for.
    """
    q = f" {normalize_for_match(question)} "
    m = _GROUP_CODE_RE.match(value or "") or _BARE_CODE_RE.match((value or "").strip())
    if m and f" {normalize_for_match(m.group(1))} " in q:
        return True
    name = normalize_for_match(_GROUP_CODE_RE.sub("", value or "", count=1))
    tokens = [t for t in dict.fromkeys(name.split()) if len(t) >= 2]
    if not tokens:
        return False
    hits = sum(1 for t in tokens if f" {t} " in q)
    return hits >= 2 and hits * 2 >= len(tokens)


def names_value(value: str, question: str) -> bool:
    """The question names this schema value (a group, a section or a column header), even a one-word one."""
    if mentioned_in(value, question):
        return True
    tokens = normalize_for_match(_GROUP_CODE_RE.sub("", value or "", count=1)).split()
    q = f" {normalize_for_match(question)} "
    return bool(tokens) and all(f" {t} " in q for t in tokens)


def counts_column(unit: str, column: str) -> bool:
    """The counted unit is this column's noun: every word of the unit is in the header ("yêu cầu" -> "Yêu cầu cần đạt")."""
    u = normalize_for_match(unit).split()
    c = set(normalize_for_match(column).split())
    return bool(u) and all(w in c for w in u)


def refine_plan(plan: "TablePlan", question: str, schema: Optional["TableSchema"] = None) -> "TablePlan":
    """
    Keeps only the group filter the question asks for. A content term asks for the items themselves,
    not for the names of the groups they are in. Every section of the document, none of them named,
    is no section filter at all (the planner copied the schema).
    """
    if plan.groups and not any(mentioned_in(g, question) for g in plan.groups):
        logger.info("Structured plan: dropping groups not named in the question: %s", plan.groups)
        plan.groups = []
    if (schema is not None and plan.sections and len(plan.sections) >= len(schema.sections) > 1
            and not any(names_value(s, question) for s in plan.sections)):
        logger.info("Structured plan: dropping a section filter that is every section: %s", plan.sections)
        plan.sections = []
    if plan.level == "groups" and plan.terms:
        plan.level = "items"
    return plan


# Codes typed in capitals in the question: a strand letter ("chủ đề C") or an item-kind prefix ("MR").
_UPPER_TOKEN_RE = re.compile(r"(?<![\w.])([A-Z]{1,4})(?![\w.])")


@dataclass
class QuestionFilters:
    """Filters read from the question against the schema, in code: what the user named is not guessed."""

    sections: List[str] = field(default_factory=list)
    groups: List[str] = field(default_factory=list)
    segment: str = ""  # alphabetic prefix of the last identifier segment ("MR" in 10.A2.MR1)

    @property
    def any(self) -> bool:
        return bool(self.sections or self.groups or self.segment)

    def segment_regex(self) -> Optional[re.Pattern]:
        return re.compile(rf"(?:^|\.){re.escape(self.segment)}\d*$", re.IGNORECASE) if self.segment else None


def _group_code(value: str) -> str:
    m = _GROUP_CODE_RE.match(value or "")
    return m.group(1).upper() if m else ""


def _last_segment_kind(identifier: str) -> str:
    return re.sub(r"\d+", "", (identifier or "").rsplit(".", 1)[-1]).upper()


def question_filters(question: str, items: Sequence[RowItem], schema: TableSchema) -> QuestionFilters:
    """
    Sections, groups and item kind the question names, matched against the document's own schema:
    a section by its words ("lớp 10"), a group by its code or name ("C5", "chủ đề A2"), all groups of a
    strand by its capital letter ("chủ đề C" -> C2, C3, C4…), an item kind by the letters that prefix the
    last segment of some identifiers ("MR" -> 10.A2.MR1). Nothing here knows a particular document.
    """
    out = QuestionFilters()
    out.sections = [s for s in schema.sections if s and names_value(s, question)]
    out.groups = [g for g in schema.groups if mentioned_in(g, question)]
    tokens = set(_UPPER_TOKEN_RE.findall(question or ""))
    if not out.groups:
        codes = {g: _group_code(g) for g in schema.groups}
        letters = {t for t in tokens if len(t) == 1}
        out.groups = [g for g, c in codes.items() if c and c[0] in letters and c != c[0]]
    kinds: Dict[str, int] = {}
    for it in items:
        k = _last_segment_kind(it.identifier)
        if k:
            kinds[k] = kinds.get(k, 0) + 1
    named = [t for t in tokens if len(t) >= 2 and 0 < kinds.get(t, 0) < len(items)]
    if len(named) == 1:
        out.segment = named[0]
    return out


def reconcile_plan(
    plan: "TablePlan", wanted: QuestionFilters, items: Sequence[RowItem], schema: TableSchema, max_items: int
) -> Tuple["TablePlan", List[RowItem]]:
    """
    The filters the question names override the planner's; a planner filter that leaves nothing
    selected (a regex of the wrong shape, a word that is not in the items) is dropped, not obeyed.
    """
    if wanted.sections:
        plan.sections = list(wanted.sections)
    if wanted.groups:
        plan.groups = list(wanted.groups)
    if wanted.segment:
        plan.identifier_regex = wanted.segment_regex()
    selected = apply_plan(items, plan, schema, max_items)
    relaxations = [("terms", [])]
    if not wanted.segment:
        relaxations.append(("identifier_regex", None))
    if not wanted.groups:
        relaxations.append(("groups", []))
    for attr, empty in relaxations:
        if selected:
            break
        if getattr(plan, attr):
            logger.info("Structured plan: %s %r selects nothing; dropped", attr, getattr(plan, attr))
            setattr(plan, attr, empty)
            selected = apply_plan(items, plan, schema, max_items)
    return plan, selected


def _match_any(value: str, wanted: Sequence[str]) -> bool:
    nv = normalize_for_match(value)
    for w in wanted:
        nw = normalize_for_match(w)
        if nw and (nv == nw or nv.startswith(nw + " ") or nw.startswith(nv + " ")):
            return True
    return False


def parse_plan(raw: str, schema: TableSchema) -> Optional[TablePlan]:
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

    def as_list(v: Any) -> List[str]:
        return [str(x).strip() for x in v if str(x).strip()] if isinstance(v, list) else []

    regex = None
    pattern = str(data.get("identifier_regex") or "").strip()
    if pattern and _SAFE_REGEX_RE.match(pattern):
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
            # A plan regex must select some but not all sample identifiers to be meaningful.
            hits = [i for i in schema.sample_identifiers if compiled.search(i)]
            if hits:
                regex = compiled
        except re.error:
            regex = None
    sections = [x for x in as_list(data.get("sections")) if _match_any(x, schema.sections)]
    groups = [x for x in as_list(data.get("groups")) if _match_any(x, schema.groups)]
    return TablePlan(
        applicable=bool(data.get("applicable", False)) if not isinstance(data.get("applicable"), str)
        else data["applicable"].strip().lower() == "true",
        sections=sections,
        groups=groups,
        terms=as_list(data.get("terms"))[:6],
        identifier_regex=regex,
        group_by="section" if str(data.get("group_by") or "").lower().startswith("section") else "group",
        level="groups" if str(data.get("level") or "").lower().startswith("group") and schema.group_column else "items",
    )


def apply_plan(items: Sequence[RowItem], plan: TablePlan, schema: TableSchema, max_items: int) -> List[RowItem]:
    out = []
    norm_terms = [normalize_for_match(t) for t in plan.terms if normalize_for_match(t)]
    for it in items:
        if plan.sections and not _match_any(it.row.section, plan.sections):
            continue
        group_value = dict(it.context_cells()).get(schema.group_column, "")
        if plan.groups and not _match_any(group_value, plan.groups):
            continue
        if plan.identifier_regex is not None and not plan.identifier_regex.search(it.identifier):
            continue
        if norm_terms:
            # Matched in the item and its own cells, not in the group name: a term that only names a group
            # ("đạo đức" in "B3. Nguyên tắc đạo đức …") would pull in every item of that group.
            own = [v for k, v in it.context_cells() if k != schema.group_column]
            hay = f" {normalize_for_match(' '.join([it.text, *own, it.row.section]))} "
            if not any(f" {t} " in hay for t in norm_terms):
                continue
        out.append(it)
    return out[:max_items]


def _render_groups(ordered: Sequence[RowItem], schema: TableSchema, bullet: str) -> str:
    """One line per group value (with the identifiers it contains), per section."""
    lines: List[str] = []
    sections = unique_in_order(it.row.section for it in ordered)
    with_sections = len([s for s in sections if s]) > 1
    for section in sections:
        if with_sections and section:
            lines.append(f"\n**{section}**")
        groups: Dict[str, List[str]] = {}
        for it in ordered:
            if it.row.section == section:
                groups.setdefault(dict(it.context_cells()).get(schema.group_column, ""), []).append(it.identifier)
        for group, ids in groups.items():
            if group:
                lines.append(f"{bullet}{group} ({', '.join(ids)})")
    return "\n".join(lines).strip()


def render_items(
    items: Sequence[RowItem], schema: TableSchema, group_by: str, answer_format: str, level: str = "items"
) -> str:
    """Deterministic rendering in document order, grouped by section then by group value."""
    ordered = sorted(items, key=lambda it: (it.row.doc_id, it.row.order))
    if level == "groups" and answer_format != "table":
        return _render_groups(ordered, schema, "☐ " if answer_format == "checklist" else "- ")
    if answer_format == "table":
        cols = ["Phần", schema.group_column or "Nhóm", "Mục"]
        lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
        for it in ordered:
            group = dict(it.context_cells()).get(schema.group_column, "")
            lines.append(f"| {it.row.section} | {group} | {it.text} |")
        return "\n".join(lines)
    bullet = "☐ " if answer_format == "checklist" else "- "
    lines: List[str] = []
    with_sections = any(it.row.section for it in ordered)
    current_section, current_group = None, None
    for it in ordered:
        group = dict(it.context_cells()).get(schema.group_column, "")
        if with_sections and it.row.section != current_section:
            current_section, current_group = it.row.section, None
            lines.append(f"\n**{it.row.section}**")
        if group and group != current_group:
            current_group = group
            lines.append(f"\n*{group}*" if with_sections else f"\n**{group}**")
        lines.append(f"{bullet}{it.text}")
    return "\n".join(lines).strip()


def listing_summary(items: Sequence[RowItem], schema: TableSchema, level: str, truncated: bool = False) -> str:
    """
    The count the question usually asks for alongside the list ("Lớp 10 có 10 chủ đề"), in the
    document's own words: section names and the header of the counted column. '' when unknown.
    """
    if not items or truncated:
        return ""
    if level == "groups" and schema.group_column:
        noun = schema.group_column.lower()
        counted = [(section, len([g for g in unique_in_order(dict(it.context_cells()).get(schema.group_column, "")
                                                             for it in items if it.row.section == section) if g]))
                   for section in unique_in_order(it.row.section for it in items)]
    else:
        first = items[0]
        noun = (first.row.columns[first.column] if first.column < len(first.row.columns) else "").lower() or "mục"
        counted = [(section, sum(1 for it in items if it.row.section == section))
                   for section in unique_in_order(it.row.section for it in items)]
    counted = [(s, n) for s, n in counted if n]
    if not counted:
        return ""
    if len(counted) == 1 and not counted[0][0]:
        return f"Có {counted[0][1]} {noun}."
    return "; ".join(f"{s or 'Khác'} có {n} {noun}" for s, n in counted) + "."
