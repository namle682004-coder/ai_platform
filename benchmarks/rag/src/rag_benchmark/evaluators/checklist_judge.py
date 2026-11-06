"""
Checklist grader: decomposed grading that a small judge model can do reliably.

The gold answer of each case is reduced to a few CORE POINTS – what an answer must state to answer
the question (class, code, yes/no, number, kind). The judge model drafts them once; people review
them (checklist JSONL / workbook), so the human graders and the machine apply the same standard.

Each core point is then checked on its own: deterministic matching first (its codes present, its
normalized text contained in the answer body) and, only when that cannot decide, one yes / no
question to the judge model. Cases whose documents have no answer are decided without the model:
the bot must decline (refuse, or hand off to support with a ticket).

Measured on the KHUNG AI set with Qwen2.5-7B: 76% agreement with human grades (kappa 0.54, held-out
halves), against 53% (kappa 0.03) for one holistic rubric verdict of the same model.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence

import openpyxl
from openpyxl.styles import Alignment, Font

from ..runtime_bridge import REFUSAL_MESSAGE, extract_identifiers, normalize_for_match
from .checks import answer_body, is_declined, transcript
from .rubric_judge import JudgeClient, JudgeConfig, JudgeResult, extract_json

DECOMPOSE_PROMPT = """Bạn tách ĐÁP ÁN KỲ VỌNG của một câu hỏi thành các Ý CHÍNH ngắn.
Ý chính = điều tối thiểu câu trả lời phải nói đúng để trả lời được câu hỏi (ví dụ: lớp nào, mã nào, có hay không, con số, loại gì). Bỏ các chi tiết diễn giải phụ.
Tối đa 3 ý, mỗi ý dưới 20 từ, là một khẳng định (không phải câu hỏi), giữ nguyên mã/số/tên riêng.
Trả về DUY NHẤT JSON: {"core": ["ý 1", "ý 2"]}"""

ITEM_PROMPT = """Bạn kiểm tra một câu trả lời của chatbot. Chỉ xét MỘT Ý duy nhất được đưa ra.
Trả lời đúng một từ:
CÓ – câu trả lời nêu ý này (diễn đạt khác cùng nghĩa vẫn tính là có)
KHÔNG – câu trả lời không nêu ý này
SAI – câu trả lời nói điều mâu thuẫn với ý này"""

MAX_CORE_POINTS = 3
ANSWER_CHARS = 6000
MIN_MATCH_WORDS = 2
# Calibrations are valid only for the same prompts and matching rule.
CHECKLIST_VERSION = "checklist-v1-" + hashlib.sha256(
    f"{DECOMPOSE_PROMPT}{ITEM_PROMPT}{MIN_MATCH_WORDS}".encode("utf-8")).hexdigest()[:8]
ITEM_WORDS = (("KHÔNG", "no"), ("SAI", "contradicts"), ("CÓ", "yes"))
YES, NO, CONTRADICTS = "yes", "no", "contradicts"


# ---------------------------------------------------------------------------------------------
# Checklist file: one JSON line per case {case_id, core, source: llm|human, expected_sha}
# ---------------------------------------------------------------------------------------------

def checklist_path_for(dataset_path: str) -> str:
    root, _ = os.path.splitext(dataset_path)
    return root + ".checklist.jsonl"


def expected_sha(case: Any) -> str:
    """Changes when the question or the gold answer changes (the drafted points are then stale)."""
    text = "\n".join([*case.conversation(), case.expected_answer])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def load_checklist(path: Optional[str]) -> Dict[str, Dict[str, Any]]:
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return {e["case_id"]: e for e in (json.loads(line) for line in f if line.strip())}


def save_checklist(path: str, entries: Dict[str, Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries.values():
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def clean_points(points: Sequence[Any]) -> List[str]:
    out = [" ".join(str(p).split()) for p in points or []]
    return [p for p in dict.fromkeys(out) if p and not p.endswith("?")][:MAX_CORE_POINTS]


REVIEW_HEADER = ["Mã câu", "Nhóm", "Câu hỏi", "Đáp án kỳ vọng", "Ý chính (mỗi dòng một ý)", "Nguồn", "Đã duyệt"]


def write_checklist_workbook(path: str, cases: Sequence[Any], entries: Dict[str, Dict[str, Any]]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ý chính"
    ws.append(REVIEW_HEADER)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for case in cases:
        if not case.answerable:
            continue
        e = entries.get(case.case_id) or {}
        ws.append([case.case_id, case.group, "\n".join(case.conversation()), case.expected_answer,
                   "\n".join(e.get("core") or []), {"human": "người", "llm": "máy"}.get(e.get("source", ""), ""),
                   "x" if e.get("source") == "human" else ""])
    for i, w in enumerate((10, 7, 45, 60, 60, 8, 9), start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "B2"
    wb.save(path)


def import_checklist_workbook(path: str, cases: Sequence[Any], entries: Dict[str, Dict[str, Any]]) -> int:
    """Rows ticked 'Đã duyệt' become human-reviewed points; returns how many were applied."""
    by_id = {c.case_id: c for c in cases}
    ws = openpyxl.load_workbook(path, data_only=True).active
    header = [str(c.value or "").strip() for c in ws[1]]
    i_id, i_core, i_ok = (header.index(h) for h in ("Mã câu", "Ý chính (mỗi dòng một ý)", "Đã duyệt"))
    n = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        case = by_id.get(str(row[i_id] or "").strip())
        if case is None or not str(row[i_ok] or "").strip():
            continue
        points = clean_points(str(row[i_core] or "").splitlines())
        entries[case.case_id] = {"case_id": case.case_id, "core": points, "source": "human",
                                 "expected_sha": expected_sha(case)}
        n += 1
    return n


# ---------------------------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------------------------

def _norm(text: str) -> str:
    return " ".join(normalize_for_match(text or "").split())


def matches(point: str, body: str) -> bool:
    """
    Deterministic 'the answer states this point': all its codes present, or its words contained as
    whole words. A one-word point ("Có", "C3") would match almost any answer, so the model decides it.
    """
    ids = extract_identifiers(point)
    if ids and all(i.upper() in body.upper() for i in ids):
        return True
    norm = _norm(point)
    return len(norm.split()) >= MIN_MATCH_WORDS and f" {norm} " in f" {_norm(body)} "


def parse_item(text: Optional[str]) -> Optional[str]:
    head = (text or "").strip().upper()
    return next((v for w, v in ITEM_WORDS if head.startswith(w)), None)


def _declined(turns: Sequence[Dict[str, Any]]) -> bool:
    if any(is_declined(t) for t in turns):
        return True
    # A workbook transcript: one refusal reply among the turns counts.
    marker = REFUSAL_MESSAGE[:40]
    return any(seg.lstrip().startswith(marker) for t in turns for seg in (t.get("answer") or "").split("Trả lời:\n"))


class ChecklistJudge(JudgeClient):
    """Core-point checklist grader (see module docstring)."""

    version = CHECKLIST_VERSION

    def __init__(self, cfg: JudgeConfig, checklist: Optional[Dict[str, Dict[str, Any]]] = None,
                 transport: Any = None) -> None:
        super().__init__(cfg, transport)
        self.checklist = checklist or {}

    def points(self, case_id: str) -> List[str]:
        return list((self.checklist.get(case_id) or {}).get("core") or [])

    async def decompose(self, case: Any) -> Optional[List[str]]:
        question = " / ".join(case.conversation())
        content = await self.complete([
            {"role": "system", "content": DECOMPOSE_PROMPT},
            {"role": "user", "content": f"CÂU HỎI: {question}\nĐÁP ÁN KỲ VỌNG: {case.expected_answer}\nJSON:"},
        ], max_tokens=300)
        if content is None:
            return None
        return clean_points(extract_json(content).get("core") or [])

    async def check_point(self, question: str, point: str, answer: str) -> Optional[str]:
        messages = [
            {"role": "system", "content": ITEM_PROMPT},
            {"role": "user", "content": f"CÂU HỎI: {question}\nÝ CẦN KIỂM TRA: {point}\n\n"
                                        f"CÂU TRẢ LỜI CỦA CHATBOT:\n{answer[:ANSWER_CHARS]}\n\nTrả lời (CÓ/KHÔNG/SAI):"},
        ]
        votes = [v for v in await asyncio.gather(*[self.complete(messages, max_tokens=8)
                                                  for _ in range(max(1, self.cfg.votes))])]
        parsed = [p for p in (parse_item(v) for v in votes) if p]
        if not parsed:
            return None
        top, count = Counter(parsed).most_common(1)[0]
        # No majority: the point is not established.
        return top if count * 2 > len(parsed) else NO

    async def grade(self, case: Any, turns: Sequence[Dict[str, Any]], context: str = "") -> JudgeResult:
        if not case.answerable:
            if _declined(turns):
                return JudgeResult(verdict="pass", reason="declined: the documents have no answer")
            return JudgeResult(verdict="fail", violated="answered although the documents have no answer",
                               reason="answered although the documents have no answer")
        if turns and is_declined(turns[-1]):
            return JudgeResult(verdict="fail", violated="declined although the documents answer it",
                               reason="declined although the documents answer it")
        points = self.points(case.case_id)
        if not points:
            return JudgeResult(verdict=None, reason="no checklist for this case (run the checklist command)")

        question = " / ".join(t.get("query", "") for t in turns) or " / ".join(case.conversation())
        body = answer_body(transcript([list(turns)]))
        items: List[Dict[str, Any]] = []
        for point in points:
            if matches(point, body):
                items.append({"point": point, "verdict": YES, "by": "match"})
            else:
                items.append({"point": point, "verdict": await self.check_point(question, point, body), "by": "judge"})
        if any(i["verdict"] is None for i in items):
            return JudgeResult(verdict=None, reason="judge unavailable or unparsable", items=items, uncertain=True)

        bad = [i["point"] for i in items if i["verdict"] == CONTRADICTS]
        missing = [i["point"] for i in items if i["verdict"] == NO]
        covered = sum(1 for i in items if i["verdict"] == YES) / len(items)
        verdict = "fail" if bad or missing else "pass"
        violated = "; ".join([*(f"contradicts: {p}" for p in bad), *(f"missing: {p}" for p in missing)])
        return JudgeResult(
            verdict=verdict, completeness=round(covered, 4), violated=violated,
            reason=violated or "all core points stated", items=items,
            uncertain=any(i["by"] == "judge" for i in items),
        )


async def build_checklist(
    judge: ChecklistJudge,
    cases: Sequence[Any],
    entries: Dict[str, Dict[str, Any]],
    overwrite: bool = False,
    concurrency: int = 4,
) -> Dict[str, int]:
    """Drafts core points for answerable cases that have none (or a stale draft); human entries are kept."""
    sem = asyncio.Semaphore(max(1, concurrency))
    stats = Counter()

    async def one(case: Any) -> None:
        current = entries.get(case.case_id)
        if current and current.get("source") == "human":
            stats["human"] += 1
            if current.get("expected_sha") != expected_sha(case):
                stats["human_stale"] += 1
            return
        if current and not overwrite and current.get("expected_sha") == expected_sha(case):
            stats["kept"] += 1
            return
        async with sem:
            points = await judge.decompose(case)
        if points is None:
            stats["failed"] += 1
            return
        entries[case.case_id] = {"case_id": case.case_id, "core": points, "source": "llm",
                                 "expected_sha": expected_sha(case)}
        stats["drafted"] += 1

    await asyncio.gather(*[one(c) for c in cases if c.answerable])
    return dict(stats)
