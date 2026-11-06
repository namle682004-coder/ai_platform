"""
Acceptance-suite reporting: summary metrics (pass rate with Wilson CI, per group, per failing
stage, per-stage retrieval recall, judge scores, latency), regression diff against a baseline run,
a markdown report and a review workbook for human grading (imported back with import_grades).
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

from ..schemas.suite import FAIL, PASS, REVIEW, CaseResult

HUMAN_PASS = ("đạt", "pass", "ok", "1", "x")
HUMAN_FAIL = ("không đạt", "khong dat", "fail", "0")
STAGE_METRICS = ("index_recall", "retrieval_recall", "rerank_recall_at_k", "rerank_mrr", "context_recall",
                 "context_precision", "answer_recall")


def wilson(successes: int, total: int, z: float = 1.959964) -> Dict[str, float]:
    if total == 0:
        return {"rate": 0.0, "low": 0.0, "high": 0.0}
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return {"rate": round(p, 4), "low": round(max(0.0, centre - half), 4), "high": round(min(1.0, centre + half), 4)}


def percentile(values: Sequence[float], q: float) -> Optional[float]:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    k = (len(vals) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return round(vals[lo] + (vals[hi] - vals[lo]) * (k - lo), 3)


TTFT_TARGET_S = 3.0
# Failure kinds of the "main limitations" section: label, where to look first.
LIMITATION_KINDS = {
    "missing_points": ("Thiếu ý chính của đáp án", "context (căn cứ có vào prompt không) rồi generation"),
    "contradicts": ("Nói ngược / sai so với đáp án (sai mã, sai lớp, sai số)", "generation, structured listing"),
    "wrongly_declined": ("Từ chối hoặc chuyển hỗ trợ dù tài liệu có đáp án", "routing, gate"),
    "answered_unanswerable": ("Trả lời dù tài liệu không có thông tin", "gate, prompt từ chối"),
    "artefacts": ("Lỗi hiển thị (ký tự lạ, câu tiếng Anh, header thô)", "answer_postprocessor"),
    "stray_identifiers": ("Có mã không thuộc câu hỏi / đáp án (dễ là mã sai, mã ví dụ)", "context, generation"),
    "errors": ("Lỗi gọi API", "log dịch vụ"),
}


def limitations(results: Sequence[CaseResult]) -> Dict[str, Dict[str, Any]]:
    """Failed cases grouped by what went wrong (one case can have several kinds)."""
    found: Dict[str, Dict[str, List[str]]] = {k: {} for k in LIMITATION_KINDS}

    def add(kind: str, case_id: str, detail: str = "") -> None:
        found[kind].setdefault(case_id, [])
        if detail and detail not in found[kind][case_id]:
            found[kind][case_id].append(detail)

    for r in results:
        failed = r.status != PASS
        for s in r.sessions:
            judge = s.judge or {}
            if s.checks.get("stray_identifiers"):
                add("stray_identifiers", r.case_id, ", ".join(s.checks["stray_identifiers"]))
            if s.checks.get("error"):
                add("errors", r.case_id)
            if not failed:
                continue
            if s.checks.get("artefacts"):
                add("artefacts", r.case_id, ", ".join(s.checks["artefacts"]))
            if s.checks.get("wrongly_refused") or "declined although" in str(judge.get("violated") or ""):
                add("wrongly_declined", r.case_id)
            for item in judge.get("items") or []:
                if item.get("verdict") == "no":
                    add("missing_points", r.case_id, item.get("point", ""))
                elif item.get("verdict") == "contradicts":
                    add("contradicts", r.case_id, item.get("point", ""))
        if failed and not r.answerable:
            add("answered_unanswerable", r.case_id)
    return {k: {"cases": len(v), "examples": v} for k, v in found.items() if v}


def _mean(values: List[float]) -> Optional[float]:
    return round(sum(values) / len(values), 4) if values else None


def summarize(results: Sequence[CaseResult], meta: Optional[Dict[str, Any]] = None,
              baseline: Optional[Sequence[CaseResult]] = None) -> Dict[str, Any]:
    n = len(results)
    status = Counter(r.status for r in results)
    groups: Dict[str, Dict[str, Any]] = {}
    for r in results:
        g = groups.setdefault(r.group or "-", {"category": r.category, "n": 0, "pass": 0, "fail": 0, "review": 0})
        g["n"] += 1
        g[r.status] += 1
    for g in groups.values():
        g["rate"] = round(g["pass"] / g["n"], 4) if g["n"] else 0.0

    sessions = [s for r in results for s in r.sessions]
    metrics = [s.stage_metrics for s in sessions if s.stage_metrics]
    judged = [s.judge for s in sessions if s.judge and s.judge.get("verdict")]
    latencies = [v for r in results for v in r.latencies()]
    ttfts = [v for r in results for v in r.ttfts()]

    summary: Dict[str, Any] = {
        "run": meta or {},
        "cases": n,
        "pass": status[PASS], "fail": status[FAIL], "review": status[REVIEW],
        "pass_rate": wilson(status[PASS], n),
        "by_group": dict(sorted(groups.items())),
        "must_pass": {
            "cases": sum(1 for r in results if r.must_pass),
            "not_passed": [r.case_id for r in results if r.must_pass and r.status != PASS],
        },
        "errors": [r.case_id for r in results if any(s.checks.get("error") for s in r.sessions)],
        "unanswerable_failed": [r.case_id for r in results if not r.answerable and r.status == FAIL],
        "wrongly_refused": [r.case_id for r in results if any(s.checks.get("wrongly_refused") for s in r.sessions)],
        "failed_stages": dict(Counter(r.failed_stage or "undiagnosed" for r in results if r.status != PASS).most_common()),
        "retrieval": {k: _mean([m[k] for m in metrics if m.get(k) is not None]) for k in STAGE_METRICS},
        "retrieval_cases": len(metrics),
        "judge": {
            "judged_sessions": len(judged),
            **{k: _mean([j[k] for j in judged if j.get(k) is not None])
               for k in ("correctness", "completeness", "faithfulness")},
        },
        "verdict_sources": dict(Counter(r.verdict_source for r in results)),
        "human_carried": sum(1 for r in results if r.verdict_source == "human" and r.human_source),
        "needs_review": [r.case_id for r in results if r.review_reasons()],
        "limitations": limitations(results),
        "ttft_over_target": {"target_s": TTFT_TARGET_S, "turns": sum(1 for v in ttfts if v > TTFT_TARGET_S),
                             "of": len(ttfts)},
        "latency_s": {"p50": percentile(latencies, 0.5), "p95": percentile(latencies, 0.95),
                      "max": max(latencies) if latencies else None},
        "ttft_s": {"p50": percentile(ttfts, 0.5), "p95": percentile(ttfts, 0.95)},
    }
    if baseline is not None:
        before = {r.case_id: r.status for r in baseline}
        summary["baseline"] = {
            "run_id": baseline[0].run_id if baseline else None,
            "pass_rate": wilson(sum(1 for r in baseline if r.status == PASS), len(baseline))["rate"],
            "regressions": [r.case_id for r in results if before.get(r.case_id) == PASS and r.status != PASS],
            "fixed": [r.case_id for r in results if before.get(r.case_id) not in (None, PASS) and r.status == PASS],
        }
    return summary


def _pct(v: Optional[float]) -> str:
    return "–" if v is None else f"{v * 100:.1f}%"


def _limitations_section(summary: Dict[str, Any]) -> List[str]:
    lim = summary.get("limitations") or {}
    lines = ["", "## Hạn chế chính", "", "| Hạn chế | Số câu | Ví dụ | Xem trước ở |", "|---|---|---|---|"]
    for kind, v in sorted(lim.items(), key=lambda kv: -kv[1]["cases"]):
        label, where = LIMITATION_KINDS[kind]
        examples = "; ".join(f"{cid}" + (f" ({', '.join(d)[:60]})" if d else "")
                             for cid, d in list(v["examples"].items())[:4]).replace("|", "/")
        lines.append(f"| {label} | {v['cases']} | {examples} | {where} |")
    weak = [(g, x) for g, x in summary["by_group"].items() if x["n"] and x["rate"] < 0.8]
    if weak:
        weak.sort(key=lambda gx: gx[1]["rate"])
        lines.append("| Nhóm câu yếu (< 80%) | " + str(len(weak)) + " nhóm | "
                     + "; ".join(f"{g} {x['category'][:30]} {_pct(x['rate'])}" for g, x in weak[:5]).replace("|", "/")
                     + " | bảng theo nhóm |")
    slow = summary.get("ttft_over_target") or {}
    if slow.get("turns"):
        lines.append(f"| Ra chữ đầu chậm hơn {slow['target_s']:g}s | {slow['turns']}/{slow['of']} lượt | "
                     f"p95 {summary['ttft_s']['p95']}s | streaming, verifier giữ chữ |")
    if len(lines) == 5:
        lines.append("| – | 0 | | |")
    return lines


def render_markdown(summary: Dict[str, Any], results: Sequence[CaseResult], gate: Optional[Dict[str, Any]] = None) -> str:
    run = summary.get("run") or {}
    pr = summary["pass_rate"]
    lines = [
        f"# Báo cáo nghiệm thu RAG – {run.get('run_id', '')}",
        "",
        f"- Commit: `{run.get('git_commit')}` · Dataset: `{run.get('dataset')}` (sha256 `{str(run.get('dataset_sha256'))[:12]}`)",
        f"- API: `{run.get('api')}` · stream={run.get('stream')} · judge: `{(run.get('judge') or {}).get('model')}` "
        f"({(run.get('judge') or {}).get('rubric_version')})",
        f"- Tổng {summary['cases']} câu: **{summary['pass']} đạt**, {summary['fail']} không đạt, {summary['review']} cần chấm tay",
        f"- **Tỷ lệ đạt: {_pct(pr['rate'])}** (KTC 95%: {_pct(pr['low'])} – {_pct(pr['high'])})",
    ]
    if gate is not None:
        lines += ["", f"## Cổng go-live: {'✅ ĐẠT' if gate['passed'] else '❌ CHƯA ĐẠT'}", "",
                  "| Tiêu chí | Kết quả | Ngưỡng | Chặn | Đạt |", "|---|---|---|---|---|"]
        for c in gate["checks"]:
            lines.append(f"| {c['name']} | {c['actual']} | {c['threshold']} | {'có' if c['blocking'] else 'cảnh báo'} | "
                         f"{'✅' if c['ok'] else '❌'} |")
    base = summary.get("baseline")
    if base:
        lines += ["", f"## So với lần chạy trước ({base['run_id']}, đạt {_pct(base['pass_rate'])})",
                  f"- Hồi quy (trước đạt, nay không): {', '.join(base['regressions']) or 'không có'}",
                  f"- Đã sửa (trước không đạt, nay đạt): {', '.join(base['fixed']) or 'không có'}"]
    lines += _limitations_section(summary)
    lines += ["", "## Lỗi nằm ở bước nào (các câu chưa đạt)", "", "| Bước | Số câu |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in summary["failed_stages"].items()] or ["| – | 0 |"]
    rt = summary["retrieval"]
    lines += ["", f"## Truy xuất theo từng bước ({summary['retrieval_cases']} lượt có căn cứ vàng)", "",
              "| Index | Retrieval | Rerank@k | MRR rerank | Context | Context precision | Answer |",
              "|---|---|---|---|---|---|---|",
              "| " + " | ".join(_pct(rt.get(k)) if k != "rerank_mrr" else (f"{rt[k]:.3f}" if rt.get(k) is not None else "–")
                             for k in STAGE_METRICS) + " |"]
    jd = summary["judge"]
    lines += ["", f"## Chấm bởi judge ({jd['judged_sessions']} phiên)",
              f"- Đúng (correctness): {_pct(jd.get('correctness'))} · Đầy đủ: {_pct(jd.get('completeness'))} · "
              f"Bám tài liệu (faithfulness): {_pct(jd.get('faithfulness'))}",
              f"- Nguồn kết luận: {summary['verdict_sources']} (giữ điểm chấm tay của câu trả lời không đổi: "
              f"{summary.get('human_carried', 0)})",
              f"- **Cần người chấm: {len(summary.get('needs_review', []))} câu** (máy chưa chắc / câu trả lời mới) – "
              f"xếp đầu file review.xlsx",
              "", "## Độ trễ",
              f"- Tổng: p50 {summary['latency_s']['p50']}s · p95 {summary['latency_s']['p95']}s · max {summary['latency_s']['max']}s",
              f"- Chữ đầu tiên: p50 {summary['ttft_s']['p50']}s · p95 {summary['ttft_s']['p95']}s",
              "", "## Theo nhóm", "", "| Nhóm | Tên | Số câu | Đạt | Tỷ lệ |", "|---|---|---|---|---|"]
    for g, v in summary["by_group"].items():
        lines.append(f"| {g} | {v['category']} | {v['n']} | {v['pass']} | {_pct(v['rate'])} |")
    bad = [r for r in results if r.status != PASS]
    if bad:
        lines += ["", "## Chi tiết câu chưa đạt", "", "| Mã | Nhóm | Bắt buộc | Kết luận | Bước lỗi | Lý do | Trace |",
                  "|---|---|---|---|---|---|---|"]
        for r in bad:
            traces = ", ".join(t["trace_id"] for s in r.sessions for t in s.turns if t.get("trace_id"))
            reason = "; ".join(r.reasons).replace("|", "/")[:220] or "chờ chấm tay"
            lines.append(f"| {r.case_id} | {r.group} | {'có' if r.must_pass else ''} | {r.status} | "
                         f"{r.failed_stage or '–'} | {reason} | {traces} |")
    return "\n".join(lines) + "\n"


REVIEW_COLUMNS = ["Mã câu", "Nhóm", "Bắt buộc", "Hội thoại (câu hỏi → trả lời)", "Mã bắt buộc", "Kết luận tự động",
                  "Lý do", "Judge", "Bước lỗi", "Trace", "Chấm tay", "Ghi chú chấm tay", "Cần người chấm"]


def _judge_text(judge: Dict[str, Any]) -> str:
    items = judge.get("items") or []
    if not items:
        return f"{judge.get('verdict')}: {judge.get('reason')}"
    marks = {"yes": "✓", "no": "✗", "contradicts": "≠"}
    return f"{judge.get('verdict')}: " + "; ".join(
        f"{marks.get(i.get('verdict'), '?')} {i.get('point')}{' (judge)' if i.get('by') == 'judge' else ''}"
        for i in items)


def write_review_workbook(path: str, results: Sequence[CaseResult], cases_by_id: Dict[str, Any]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Chấm"
    ws.append(REVIEW_COLUMNS + ["Đáp án kỳ vọng", "FAIL nếu"])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    colors = {PASS: "C6EFCE", FAIL: "FFC7CE", REVIEW: "FFEB9C"}
    # Cases a person must look at first; then the rest (already human-graded or machine-certain).
    ordered = sorted(results, key=lambda r: not r.review_reasons())
    for r in ordered:
        case = cases_by_id.get(r.case_id)
        convo = "\n\n".join(
            (f"── Phiên {i} ──\n" if len(r.sessions) > 1 else "")
            + "\n".join(f"❓ {t['query']}\n💬 {t['answer']}" for t in s.turns)
            for i, s in enumerate(r.sessions, start=1)
        )
        judge = " | ".join(_judge_text(s.judge) for s in r.sessions if s.judge)
        notes = r.human_notes + (f" [giữ điểm từ {r.human_source}]" if r.human_source else "")
        ws.append([
            r.case_id, r.group, "x" if r.must_pass else "", convo[:32000], ", ".join(r.required_identifiers),
            r.auto_status, "; ".join(r.reasons), judge, r.failed_stage or "",
            ", ".join(t["trace_id"] for s in r.sessions for t in s.turns if t.get("trace_id")),
            {PASS: "Đạt", FAIL: "Không đạt"}.get(r.human_status or "", ""), notes,
            ", ".join(r.review_reasons()),
            getattr(case, "expected_answer", ""), getattr(case, "fail_conditions", ""),
        ])
        ws.cell(ws.max_row, 6).fill = PatternFill("solid", fgColor=colors.get(r.auto_status, "FFFFFF"))
    widths = [10, 7, 8, 90, 22, 12, 40, 50, 12, 28, 12, 30, 18, 50, 40]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "B2"
    wb.save(path)


def import_grades(path: str, results: Sequence[CaseResult]) -> int:
    """Applies the 'Chấm tay' column of a review workbook; returns how many cases got a human verdict."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    header = [str(c.value or "").strip() for c in ws[1]]
    i_id, i_grade, i_notes = header.index("Mã câu"), header.index("Chấm tay"), header.index("Ghi chú chấm tay")
    grades: Dict[str, tuple] = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        grade = str(row[i_grade] or "").strip().lower()
        if row[i_id] and grade:
            status = PASS if grade in HUMAN_PASS else FAIL if grade in HUMAN_FAIL else None
            if status:
                grades[str(row[i_id]).strip()] = (status, str(row[i_notes] or ""))
    for r in results:
        if r.case_id in grades:
            r.human_status, r.human_notes = grades[r.case_id]
            r.human_source = ""
            r.finalize()
    return sum(1 for r in results if r.case_id in grades)
