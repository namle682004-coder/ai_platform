"""
Converts an acceptance test workbook (one row per question) into golden JSONL + a judge
calibration set.

Everything dataset-specific (sheet, column names, which reference means "not in the documents",
critical groups) lives in a dataset config YAML, not in code. Rows that were graded by people
(answer + pass/fail) become calibration examples for the LLM judge.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
import yaml

from ..schemas.dataset import GoldenCase, SessionMode
from ..runtime_bridge import extract_identifiers

DEFAULT_TURN_RE = r"^\s*Lượt\s*\d+\s*:\s*(.+)$"
DEFAULT_VARIANT_RE = r"^\s*\(\d+\)\s*(.+)$"


def load_config(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def split_turns(question: str, kind: str, cfg: Dict[str, Any]) -> Tuple[SessionMode, List[str]]:
    lines = [ln.strip() for ln in (question or "").splitlines() if ln.strip()]
    turn_re = re.compile(cfg.get("turn_regex", DEFAULT_TURN_RE))
    variant_re = re.compile(cfg.get("variant_regex", DEFAULT_VARIANT_RE))
    turns = [m.group(1).strip() for ln in lines for m in [turn_re.match(ln)] if m]
    if turns:
        return SessionMode.MULTI_TURN, turns
    variants = [m.group(1).strip() for ln in lines for m in [variant_re.match(ln)] if m]
    if variants:
        return SessionMode.SEPARATE_SESSIONS, variants
    if re.search(cfg.get("separate_sessions_kind_regex", r"(?i)phiên riêng"), kind or ""):
        body = (question or "").split(":", 1)[-1].strip()
        return SessionMode.SEPARATE_SESSIONS, [body] * int(cfg.get("separate_sessions_repeat", 3))
    return SessionMode.SINGLE, [(question or "").strip()]


def identifiers_in(text: str) -> List[str]:
    """Identifiers of `text`, with "A/B" pairs of complete codes split ("11.C5.1/11.C5.MR1" is two codes,
    "2422/QĐ-BGDĐT" is one)."""
    out: List[str] = []
    for code in extract_identifiers(text):
        parts = code.split("/")
        if len(parts) > 1 and all(extract_identifiers(p) == [p] for p in parts):
            out.extend(p for p in parts if p not in out)
        elif code not in out:
            out.append(code)
    return out


def _cell(row: Dict[str, Any], cfg_cols: Dict[str, str], key: str) -> str:
    name = cfg_cols.get(key)
    value = row.get(name) if name else None
    return "" if value is None else str(value).strip()


def import_workbook(xlsx_path: str, cfg: Dict[str, Any]) -> Tuple[List[GoldenCase], List[Dict[str, Any]]]:
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb[cfg.get("sheet") or wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    header = [str(v or "").strip() for v in rows[0]]
    cols: Dict[str, str] = cfg.get("columns") or {}
    missing = [c for c in ("case_id", "question", "expected_answer") if cols.get(c) not in header]
    if missing:
        raise ValueError(f"Columns not found in sheet: {[cols.get(c) for c in missing]} (header: {header})")

    unanswerable_re = re.compile(cfg.get("unanswerable_reference_regex", r"^\s*[—–-]?\s*$"))
    id_sources = cfg.get("required_identifiers_from", ["reference"])
    must_pass_groups = {str(g) for g in cfg.get("must_pass_groups", [])}
    overrides: Dict[str, List[str]] = cfg.get("required_identifiers_overrides") or {}
    pass_values = {v.lower() for v in cfg.get("human_pass_values", ["Đạt", "Pass"])}
    fail_values = {v.lower() for v in cfg.get("human_fail_values", ["Không đạt", "Fail"])}

    cases: List[GoldenCase] = []
    calibration: List[Dict[str, Any]] = []
    for values in rows[1:]:
        row = dict(zip(header, values, strict=False))  # trailing empty cells may be cut
        case_id = _cell(row, cols, "case_id")
        question = _cell(row, cols, "question")
        if not case_id or not question:
            continue
        reference = _cell(row, cols, "reference")
        expected = _cell(row, cols, "expected_answer")
        mode, turns = split_turns(question, _cell(row, cols, "kind"), cfg)
        sources = {"reference": reference, "expected_answer": expected}
        identifiers: List[str] = []
        for src in id_sources:
            for code in identifiers_in(sources.get(src, "")):
                if code not in identifiers:
                    identifiers.append(code)
        if case_id in overrides:
            identifiers = [str(c).upper() for c in overrides[case_id] or []]
        group = _cell(row, cols, "group")
        answerable = not unanswerable_re.search(reference)
        cases.append(GoldenCase(
            case_id=case_id,
            dataset_version=str(cfg.get("dataset_version", "1.0.0")),
            source_dataset=Path(xlsx_path).name,
            domain=str(cfg.get("domain", "general")),
            question=turns[-1],
            answerable=answerable,
            expected_answer=expected or "(không có đáp án mẫu)",
            required_facts=[],
            tags=[t for t in (group, mode.value) if t],
            group=group,
            category=_cell(row, cols, "category"),
            session_mode=mode,
            turns=turns if mode != SessionMode.SINGLE else [],
            required_identifiers=identifiers if answerable else [],
            fail_conditions=_cell(row, cols, "fail_conditions"),
            must_pass=group in must_pass_groups or case_id in must_pass_groups,
        ))
        human = _cell(row, cols, "human_result").lower()
        answer = _cell(row, cols, "human_answer")
        if answer and human in pass_values | fail_values:
            calibration.append({
                "case_id": case_id, "answer": answer, "human_pass": human in pass_values,
                "notes": _cell(row, cols, "human_notes"),
            })
    return cases, calibration


def write_outputs(
    cases: List[GoldenCase], calibration: List[Dict[str, Any]], out_path: str, calibration_path: Optional[str] = None
) -> Tuple[str, Optional[str]]:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for c in cases:
            f.write(c.model_dump_json() + "\n")
    cal_out = None
    if calibration:
        cal_out = calibration_path or str(out.with_suffix("")) + ".calibration.jsonl"
        with open(cal_out, "w", encoding="utf-8") as f:
            for item in calibration:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return str(out), cal_out
