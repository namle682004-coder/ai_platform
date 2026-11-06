"""
Human grade store: a person's verdict on an answer stays valid while the system gives that same
answer to that same case. Carrying those verdicts into new runs leaves people to grade only the
answers that changed – the machine verdict is a triage signal, the human verdict the reference.

Sources: calibration / workbook JSONL rows {case_id, answer, human_pass, notes} and finished runs
(results.jsonl with human verdicts).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .evaluators.checks import transcript
from .runtime_bridge import TICKET_RE
from .schemas.suite import FAIL, PASS, CaseResult

Grade = Tuple[str, str, str]  # status, notes, source


def answer_key(text: str) -> str:
    """The answer with whitespace and per-run values (ticket ids) neutralized."""
    return " ".join(TICKET_RE.sub("#", text or "").split())


def result_text(result: CaseResult) -> str:
    return transcript([s.turns for s in result.sessions])


def load_grades(paths: Sequence[str]) -> Dict[str, Dict[str, Grade]]:
    """case_id -> {answer key -> grade}; later sources win."""
    store: Dict[str, Dict[str, Grade]] = {}
    for raw in paths or []:
        p = Path(raw)
        if p.is_dir() or p.name == "results.jsonl":
            path = p / "results.jsonl" if p.is_dir() else p
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                r = CaseResult.model_validate_json(line)
                if r.human_status in (PASS, FAIL):
                    store.setdefault(r.case_id, {})[answer_key(result_text(r))] = (
                        r.human_status, r.human_notes, r.human_source or r.run_id)
        else:
            for line in p.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if "human_pass" in row and row.get("answer"):
                    store.setdefault(row["case_id"], {})[answer_key(row["answer"])] = (
                        PASS if row["human_pass"] else FAIL, str(row.get("notes") or ""), p.name)
    return store


def carry_grades(results: Sequence[CaseResult], store: Dict[str, Dict[str, Grade]]) -> List[str]:
    """Applies stored human verdicts to unchanged answers; returns the case ids that got one."""
    carried = []
    for r in results:
        if r.human_status in (PASS, FAIL):
            continue
        grade: Optional[Grade] = store.get(r.case_id, {}).get(answer_key(result_text(r)))
        if grade:
            r.human_status, r.human_notes, r.human_source = grade
            r.finalize()
            carried.append(r.case_id)
    return carried
