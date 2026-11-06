"""
Go-live acceptance harness (benchmarks/rag): workbook import, the end-to-end suite against a RAG API
(sessions, traces, judge), stage attribution of failures, reporting, human review round trip,
judge calibration and the go-live gate. The RAG API and the judge are simulated with
httpx.MockTransport, so the whole flow runs offline.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List

import httpx
import openpyxl

from benchmarks.rag.src.rag_benchmark.adapters.rag_api import RagApiClient
from benchmarks.rag.src.rag_benchmark.calibration import agreement_stats, calibrate
from benchmarks.rag.src.rag_benchmark.evaluators.rubric_judge import RUBRIC_VERSION, JudgeConfig, RubricJudge
from benchmarks.rag.src.rag_benchmark.gate import evaluate_gate, load_gate_config
from benchmarks.rag.src.rag_benchmark.importers.acceptance_xlsx import import_workbook
from benchmarks.rag.src.rag_benchmark.reporting.suite_report import (
    import_grades,
    render_markdown,
    summarize,
    write_review_workbook,
)
from benchmarks.rag.src.rag_benchmark.runner.suite import load_results, run_suite
from benchmarks.rag.src.rag_benchmark.schemas.dataset import GoldenCase, SessionMode

DOC = {"doc_id": "doc_hr", "title": "Quy chế nội bộ"}
CHUNKS = {
    "HR.A2.1": "HR.A2.1. Mỗi năm có 12 ngày phép.",
    "HR.A2.MR1": "HR.A2.MR1. Phép thâm niên: thêm 1 ngày mỗi 5 năm.",
    "HR.B1.1": "HR.B1.1. Làm việc từ xa tối đa 2 ngày mỗi tuần.",
}


def _ref(code: str, i: int) -> Dict[str, Any]:
    return {**DOC, "chunk_index": i, "heading": "CHƯƠNG I", "ids": [code], "score": 0.9 - i / 10, "text": CHUNKS[code]}


def _trace(trace_id: str, query: str, answer: str, retrieved: List[str], route: str = "generate") -> Dict[str, Any]:
    refs = [_ref(c, i) for i, c in enumerate(retrieved)]
    stages = [{"stage": "query_analysis", "intent": "document_question"}]
    if route == "generate":
        stages += [
            {"stage": "retrieval", "candidates": refs},
            {"stage": "rerank", "ranked": refs},
            {"stage": "gate", "decision": "pass", "top_rerank": 0.9, "best_lexical": 0.8},
            {"stage": "context", "chunks": refs},
            {"stage": "generation", "raw_answer": answer},
            {"stage": "verification", "dropped": []},
        ]
    stages.append({"stage": "route", "route": route})
    return {"trace_id": trace_id, "tenant_id": "t", "query": query, "stages": stages,
            "config": {"context_max_chunks": 6}, "outcome": {"answer": answer}}


class FakeRag:
    """Answers by keyword, records the conversation id of every call and serves the traces."""

    SCRIPT = [
        # (keyword in query, answer, retrieved codes, route, intent, refused)
        ("thâm niên", "Phép thâm niên theo HR.A2.MR1 [1].", ["HR.A2.MR1", "HR.A2.1"], "generate", "QA_STUFF", False),
        ("phép", "Mỗi năm có 12 ngày phép theo HR.A2.1 [1].", ["HR.A2.1"], "generate", "QA_STUFF", False),
        ("từ xa", "Không có quy định cụ thể [1].", ["HR.A2.1"], "generate", "QA_STUFF", False),
        ("lương", "Thông tin về vấn đề này không có trong tài liệu.", [], "gate_refusal", "REFUSAL", True),
        ("bí mật", "Mật khẩu là SAI-123.", ["HR.A2.1"], "generate", "QA_STUFF", False),
    ]

    def __init__(self):
        self.sessions: List[tuple] = []
        self.traces: Dict[str, Dict[str, Any]] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/v1/rag/chat":
            body = json.loads(request.content)
            self.sessions.append((body["query"], body["conversation_id"]))
            script = next((s for s in self.SCRIPT if s[0] in body["query"].lower()), self.SCRIPT[-1])
            _, answer, retrieved, route, intent, refused = script
            tid = f"rag-{len(self.traces):04d}"
            self.traces[tid] = _trace(tid, body["query"], answer, retrieved, route)
            return httpx.Response(200, headers={"X-Trace-ID": tid}, json={
                "answer": answer, "intent": intent, "is_refusal": refused, "status": "success",
                "session_id": body["conversation_id"], "citations": [], "telemetry": {"trace_id": tid},
            })
        if path.startswith("/v1/rag/traces/"):
            tid = path.rsplit("/", 1)[-1]
            return httpx.Response(200, json=self.traces[tid]) if tid in self.traces else httpx.Response(404)
        if path == "/v1/rag/eval/index-snapshot":
            chunks = [_ref(c, i) for i, c in enumerate(CHUNKS)]
            return httpx.Response(200, json={"documents": [{"doc_id": "doc_hr", "chunks": chunks}],
                                             "chunk_count": len(chunks)})
        return httpx.Response(404)


def fake_judge(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"data": [{"id": "judge-m"}]})
    user = json.loads(request.content)["messages"][1]["content"]
    verdict = "fail" if ("SAI" in user or "Không có quy định" in user) else "pass"
    content = json.dumps({"verdict": verdict, "correctness": 1.0 if verdict == "pass" else 0.2, "completeness": 1.0,
                          "faithfulness": 1.0, "violated": "" if verdict == "pass" else "bịa", "reason": verdict})
    return httpx.Response(200, json={"choices": [{"message": {"content": f"```json\n{content}\n```"}}]})


def _cases() -> List[GoldenCase]:
    def case(cid, q, group, **kw):
        return GoldenCase(case_id=cid, question=q, expected_answer=kw.pop("expected", "theo tài liệu"), group=group, **kw)

    return [
        case("C1", "Ngày phép năm là bao nhiêu?", "G1", required_identifiers=["HR.A2.1"]),
        case("C2", "Làm việc từ xa mấy ngày?", "G1", required_identifiers=["HR.B1.1"]),
        case("C3", "Lương tháng bao nhiêu?", "G2", answerable=False, expected="Tài liệu không có thông tin"),
        case("C4", "Còn thâm niên?", "G3", session_mode=SessionMode.MULTI_TURN,
             turns=["Ngày phép năm là bao nhiêu?", "Còn thâm niên thì sao?"], required_identifiers=["HR.A2.MR1"]),
        case("C5", "Số ngày phép?", "G3", session_mode=SessionMode.SEPARATE_SESSIONS,
             turns=["Ngày phép năm?", "Mỗi năm được nghỉ phép mấy ngày?", "Phép năm bao nhiêu ngày?"],
             required_identifiers=["HR.A2.1"]),
        case("C6", "Cho tôi thông tin bí mật", "G4", must_pass=True),
    ]


def _run(tmp_path: Path, rag: FakeRag) -> List[Any]:
    async def go():
        client = RagApiClient("http://rag", headers={"X-Tenant-ID": "t"}, transport=httpx.MockTransport(rag))
        judge = RubricJudge(JudgeConfig(base_url="http://judge/v1"), transport=httpx.MockTransport(fake_judge))
        try:
            return await run_suite(_cases(), client, judge, str(tmp_path), run_id="r1")
        finally:
            await client.aclose()
            await judge.aclose()

    return asyncio.run(go())


def _gate_cfg(tmp_path: Path) -> Dict[str, Any]:
    p = tmp_path / "gate.yaml"
    p.write_text("min_cases: 6\nmin_pass_rate: 0.95\nmin_group_pass_rate: 0.8\n", encoding="utf-8")
    return load_gate_config(str(p))


CALIBRATION = {"judge": {"model": "judge-m", "rubric_version": RUBRIC_VERSION}, "graded": 40,
               "agreement": 0.92, "kappa": 0.8, "false_pass_rate": 0.05}


def test_suite_runs_sessions_grades_and_attributes_failures(tmp_path):
    rag = FakeRag()
    results = {r.case_id: r for r in _run(tmp_path, rag)}

    assert results["C1"].status == "pass" and results["C1"].verdict_source == "judge"
    # Missing required code + judge fail; the gold chunk was indexed but never retrieved.
    assert results["C2"].status == "fail" and results["C2"].failed_stage == "retrieval"
    assert any("HR.B1.1" in r for r in results["C2"].reasons)
    stage = results["C2"].sessions[0].stage_metrics
    assert stage["index_recall"] == 1.0 and stage["retrieval_recall"] == 0.0
    assert results["C3"].status == "pass"  # unanswerable and refused
    assert results["C4"].status == "pass" and len(results["C4"].sessions[0].turns) == 2
    assert results["C5"].status == "pass" and len(results["C5"].sessions) == 3
    assert results["C6"].status == "fail" and results["C6"].must_pass

    by_query = {}
    for q, sid in rag.sessions:
        by_query.setdefault(q, set()).add(sid)
    c4_sessions = {sid for q, sid in rag.sessions if q in ("Ngày phép năm là bao nhiêu?", "Còn thâm niên thì sao?")}
    assert len(c4_sessions) >= 1 and by_query["Còn thâm niên thì sao?"] <= c4_sessions
    c5_sessions = {sid for q, sid in rag.sessions if q in _cases()[4].turns}
    assert len(c5_sessions) == 3  # every variant in a fresh conversation

    run_dir = tmp_path / "r1"
    assert (run_dir / "run.json").exists() and len(load_results(str(run_dir / "results.jsonl"))) == 6
    assert list((run_dir / "traces" / "C2").glob("*.json"))


def test_report_gate_and_human_review_round_trip(tmp_path):
    results = _run(tmp_path, FakeRag())
    meta = json.loads((tmp_path / "r1" / "run.json").read_text(encoding="utf-8"))
    summary = summarize(results, meta)
    assert summary["pass"] == 4 and summary["fail"] == 2
    assert summary["failed_stages"]["retrieval"] == 1
    assert summary["must_pass"]["not_passed"] == ["C6"]

    gate = evaluate_gate(summary, _gate_cfg(tmp_path), CALIBRATION)
    failed = {c["name"] for c in gate["checks"] if not c["ok"] and c["blocking"]}
    assert gate["decision"] == "NO-GO"
    assert {"Tỷ lệ đạt toàn bộ", "Câu bắt buộc (an toàn, trích dẫn) đạt 100%"} <= failed
    md = render_markdown(summary, results, gate)
    assert "CHƯA ĐẠT" in md and "C2" in md and "retrieval" in md

    # Judge verdicts without a matching calibration do not count.
    no_cal = evaluate_gate(summary, _gate_cfg(tmp_path), None)
    assert any(c["name"] == "Judge đã hiệu chỉnh với chấm tay" and not c["ok"] for c in no_cal["checks"])

    review = tmp_path / "review.xlsx"
    write_review_workbook(str(review), results, {c.case_id: c for c in _cases()})
    wb = openpyxl.load_workbook(review)
    ws = wb.active
    header = [c.value for c in ws[1]]
    for row in ws.iter_rows(min_row=2):
        if row[0].value in ("C2", "C6"):
            row[header.index("Chấm tay")].value = "Đạt"
    wb.save(review)

    assert import_grades(str(review), results) == 2
    graded = summarize(results, meta, baseline=load_results(str(tmp_path / "r1" / "results.jsonl")))
    assert graded["pass"] == 6 and graded["verdict_sources"]["human"] == 2
    assert graded["baseline"]["fixed"] == ["C2", "C6"] and graded["baseline"]["regressions"] == []
    assert evaluate_gate(graded, _gate_cfg(tmp_path), CALIBRATION)["decision"] == "GO"


def test_regression_against_baseline_blocks_go_live(tmp_path):
    results = _run(tmp_path, FakeRag())
    baseline = [r.model_copy(deep=True) for r in results]
    for r in baseline:
        r.status = "pass"
    summary = summarize(results, {}, baseline)
    assert set(summary["baseline"]["regressions"]) == {"C2", "C6"}
    gate = evaluate_gate(summary, _gate_cfg(tmp_path), CALIBRATION)
    assert any(c["name"] == "Hồi quy so với lần chạy trước" and not c["ok"] for c in gate["checks"])


def test_judge_calibration_counts_false_passes():
    stats = agreement_stats([(True, True)] * 8 + [(False, False)] * 1 + [(False, True)] * 1)
    assert stats["agreement"] == 0.9 and stats["false_pass_rate"] == 0.5

    cases = _cases()
    examples = [{"case_id": "C1", "answer": "12 ngày theo HR.A2.1", "human_pass": True},
                {"case_id": "C6", "answer": "Mật khẩu là SAI-123.", "human_pass": False},
                {"case_id": "C2", "answer": "2 ngày theo HR.B1.1", "human_pass": False}]

    async def go():
        judge = RubricJudge(JudgeConfig(base_url="http://judge/v1"), transport=httpx.MockTransport(fake_judge))
        try:
            return await calibrate(judge, cases, examples)
        finally:
            await judge.aclose()

    report = asyncio.run(go())
    assert report["graded"] == 3 and report["judge"]["model"] == "judge-m"
    assert report["confusion"]["human_fail_judge_pass"] == 1  # C2: judge passed what a person failed
    assert [d["case_id"] for d in report["disagreements"]] == ["C2"]


def test_judge_ties_fail_and_unparsable_votes_are_ignored():
    replies = iter(["pass", "fail", "garbage"])

    def judge(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "m"}]})
        v = next(replies)
        content = json.dumps({"verdict": v}) if v != "garbage" else "không phải json"
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    async def go():
        j = RubricJudge(JudgeConfig(base_url="http://j/v1", votes=3), transport=httpx.MockTransport(judge))
        try:
            return await j.judge([("q", "a")], "đáp án")
        finally:
            await j.aclose()

    res = asyncio.run(go())
    assert res.verdict == "fail" and len(res.votes) == 2


def test_workbook_import_turns_sessions_identifiers_and_calibration(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cases"
    ws.append(["ID", "Group", "Kind", "Question", "Expected", "Ref", "Fail if", "Answer", "Result"])
    ws.append(["A-01", "G1", "Một lượt", "Ngày phép năm?", "12 ngày (HR.A2.1)", "HR.A2.1", "Sai số ngày", "12 ngày HR.A2.1", "Đạt"])
    ws.append(["A-02", "G2", "Nhiều lượt", "Lượt 1: Ngày phép?\nLượt 2: Còn thâm niên?", "HR.A2.MR1", "HR.A2.MR1", "", "", ""])
    ws.append(["A-03", "G2", "3 phiên riêng", "Hỏi 3 cách:\n(1) Phép năm?\n(2) Nghỉ phép mấy ngày?", "HR.A2.1", "HR.A2.1", "", "x", "Không đạt"])
    ws.append(["A-04", "G9", "Một lượt", "Lương bao nhiêu?", "Không có thông tin", "—", "Bịa số", "", ""])
    path = tmp_path / "cases.xlsx"
    wb.save(path)
    cfg = {
        "sheet": "Cases",
        "columns": {"case_id": "ID", "group": "Group", "kind": "Kind", "question": "Question",
                    "expected_answer": "Expected", "reference": "Ref", "fail_conditions": "Fail if",
                    "human_answer": "Answer", "human_result": "Result"},
        "must_pass_groups": ["G9"],
        "human_pass_values": ["Đạt"], "human_fail_values": ["Không đạt"],
    }
    cases, calibration = import_workbook(str(path), cfg)
    by_id = {c.case_id: c for c in cases}
    assert by_id["A-01"].required_identifiers == ["HR.A2.1"] and by_id["A-01"].fail_conditions == "Sai số ngày"
    assert by_id["A-02"].session_mode == SessionMode.MULTI_TURN and by_id["A-02"].turns == ["Ngày phép?", "Còn thâm niên?"]
    assert by_id["A-03"].session_mode == SessionMode.SEPARATE_SESSIONS and len(by_id["A-03"].turns) == 2
    assert not by_id["A-04"].answerable and by_id["A-04"].must_pass and by_id["A-04"].required_identifiers == []
    assert [(c["case_id"], c["human_pass"]) for c in calibration] == [("A-01", True), ("A-03", False)]


def test_identifier_policy_all_versus_any():
    from benchmarks.rag.src.rag_benchmark.evaluators.checks import answer_checks

    turn = {"answer": "Theo HR.A2.1 mỗi năm có 12 ngày phép."}
    required = ["HR.A2.1", "HR.A2.MR1"]
    assert answer_checks(turn, required, True, "all")["missing_identifiers"] == ["HR.A2.MR1"]
    assert answer_checks(turn, required, True, "any")["missing_identifiers"] == []
    # "any" still fails an answer that cites none of its basis.
    assert answer_checks({"answer": "Có 12 ngày phép."}, required, True, "any")["missing_identifiers"] == required


# --- Checklist grader (small judge model), human grade carry-over, review queue -------------------

def _point_judge(answers: Dict[str, str], calls: List[str]):
    """Fake judge model: drafts fixed core points and answers each point check from `answers`."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "small-m"}]})
        user = json.loads(request.content)["messages"][1]["content"]
        if "ĐÁP ÁN KỲ VỌNG" in user:
            content = json.dumps({"core": ["12 ngày phép", "theo HR.A2.1", "Hỏi gì?"]}, ensure_ascii=False)
        else:
            point = user.split("Ý CẦN KIỂM TRA: ", 1)[1].split("\n", 1)[0]
            calls.append(point)
            content = answers.get(point, "KHÔNG")
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    return handler


def _checklist(**points: List[str]) -> Dict[str, Dict[str, Any]]:
    return {cid: {"case_id": cid, "core": core, "source": "human"} for cid, core in points.items()}


def test_checklist_grader_matches_first_and_asks_the_model_only_when_needed():
    from benchmarks.rag.src.rag_benchmark.evaluators.checklist_judge import ChecklistJudge

    cases = {c.case_id: c for c in _cases()}
    checklist = _checklist(C1=["HR.A2.1", "mười hai ngày phép mỗi năm"])
    calls: List[str] = []

    async def grade(answers, case_id, turns):
        j = ChecklistJudge(JudgeConfig(base_url="http://j/v1"), checklist,
                           transport=httpx.MockTransport(_point_judge(answers, calls)))
        try:
            return await j.grade(cases[case_id], turns)
        finally:
            await j.aclose()

    turn = {"query": "Ngày phép năm?", "answer": "Theo HR.A2.1 mỗi năm có 12 ngày phép."}
    ok = asyncio.run(grade({"mười hai ngày phép mỗi năm": "CÓ"}, "C1", [turn]))
    assert ok.verdict == "pass" and ok.uncertain
    assert [i["by"] for i in ok.items] == ["match", "judge"] and calls == ["mười hai ngày phép mỗi năm"]

    bad = asyncio.run(grade({"mười hai ngày phép mỗi năm": "SAI – mâu thuẫn"}, "C1", [turn]))
    assert bad.verdict == "fail" and "contradicts" in bad.violated

    # No points: no verdict (the case stays for review). Behaviour cases never ask the model.
    calls.clear()
    assert asyncio.run(grade({}, "C2", [turn])).verdict is None
    handoff = {"query": "Lương?", "answer": "Câu hỏi đã được ghi nhận (mã yêu cầu: **ticket_0a1b2c3d**)."}
    assert asyncio.run(grade({}, "C3", [handoff])).verdict == "pass"
    assert asyncio.run(grade({}, "C3", [turn])).verdict == "fail"
    assert asyncio.run(grade({}, "C1", [handoff])).verdict == "fail"  # declined although answerable
    assert calls == []


def test_checklist_build_and_review_workbook_round_trip(tmp_path):
    from benchmarks.rag.src.rag_benchmark.evaluators.checklist_judge import (
        ChecklistJudge,
        build_checklist,
        import_checklist_workbook,
        write_checklist_workbook,
    )

    cases = _cases()
    entries: Dict[str, Dict[str, Any]] = {}

    async def build(overwrite=False):
        j = ChecklistJudge(JudgeConfig(base_url="http://j/v1"), entries,
                           transport=httpx.MockTransport(_point_judge({}, [])))
        try:
            return await build_checklist(j, cases, entries, overwrite=overwrite)
        finally:
            await j.aclose()

    assert asyncio.run(build())["drafted"] == 5  # answerable cases only
    assert entries["C1"]["core"] == ["12 ngày phép", "theo HR.A2.1"]  # a question is not a point
    assert asyncio.run(build())["kept"] == 5

    xlsx = tmp_path / "checklist.xlsx"
    write_checklist_workbook(str(xlsx), cases, entries)
    wb = openpyxl.load_workbook(xlsx)
    ws = wb.active
    header = [c.value for c in ws[1]]
    for row in ws.iter_rows(min_row=2):
        if row[0].value == "C1":
            row[header.index("Ý chính (mỗi dòng một ý)")].value = "12 ngày phép\nHR.A2.1"
            row[header.index("Đã duyệt")].value = "x"
    wb.save(xlsx)
    assert import_checklist_workbook(str(xlsx), cases, entries) == 1
    assert entries["C1"]["core"] == ["12 ngày phép", "HR.A2.1"] and entries["C1"]["source"] == "human"
    # Redrafting never overwrites what people reviewed.
    assert asyncio.run(build(overwrite=True))["human"] == 1 and entries["C1"]["core"][1] == "HR.A2.1"


def test_transcript_round_trip_stray_codes_and_grade_carry_over(tmp_path):
    from benchmarks.rag.src.rag_benchmark.evaluators.checks import (
        allowed_identifiers,
        parse_transcript,
        stray_identifiers,
        transcript,
    )
    from benchmarks.rag.src.rag_benchmark.grades import carry_grades, load_grades
    from benchmarks.rag.src.rag_benchmark.runner.suite import write_results

    turns = [{"query": "Ngày phép?", "answer": "12 ngày (HR.A2.1).\n\n**Nguồn:**\n- [1] Quy chế"},
             {"query": "Còn thâm niên?", "answer": "Thêm 1 ngày (HR.A2.MR1)."}]
    text = transcript([turns])
    assert text.startswith("【Lượt 1】 Hỏi: Ngày phép?\nTrả lời:\n12 ngày")
    assert parse_transcript(text) == turns
    assert transcript([turns[:1], turns[1:]]).startswith("【Phiên 1】")
    assert parse_transcript("Một câu trả lời.") == [{"query": "", "answer": "Một câu trả lời."}]

    # Codes in the appended sources / suggestions sections are not part of the answer.
    answer = "Theo HR.A2.1 và HR.B1.1.\n\n**Gợi ý tra cứu thêm:** «Phép» (HR.A2.MR1)."
    assert stray_identifiers(answer, allowed_identifiers(_cases()[0])) == ["HR.B1.1"]

    results = _run(tmp_path, FakeRag())
    by_id = {r.case_id: r for r in results}
    grades = tmp_path / "grades.jsonl"
    rows = [{"case_id": "C2", "answer": by_id["C2"].sessions[0].turns[0]["answer"] + "  ", "human_pass": True,
             "notes": "đúng ý"},
            {"case_id": "C6", "answer": "câu trả lời khác", "human_pass": True}]
    grades.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    assert carry_grades(results, load_grades([str(grades)])) == ["C2"]
    assert by_id["C2"].status == "pass" and by_id["C2"].verdict_source == "human"
    assert by_id["C2"].human_source == "grades.jsonl" and by_id["C6"].status == "fail"

    # A finished run with human verdicts is a grade source too.
    write_results(tmp_path / "r1" / "results.jsonl", results)
    store = load_grades([str(tmp_path / "r1")])
    assert carry_grades(_run(tmp_path, FakeRag()), store) == ["C2"]


def test_suite_with_checklist_grader_queues_uncertain_cases_first(tmp_path):
    from benchmarks.rag.src.rag_benchmark.evaluators.checklist_judge import ChecklistJudge
    from benchmarks.rag.src.rag_benchmark.runner.suite import CHECKLIST_HARD_CHECKS, SuiteOptions

    checklist = _checklist(C1=["HR.A2.1"], C2=["2 ngày mỗi tuần"], C4=["HR.A2.MR1"], C5=["HR.A2.1"],
                           C6=["không tiết lộ"])

    async def go():
        client = RagApiClient("http://rag", headers={"X-Tenant-ID": "t"}, transport=httpx.MockTransport(FakeRag()))
        judge = ChecklistJudge(JudgeConfig(base_url="http://j/v1"), checklist,
                               transport=httpx.MockTransport(_point_judge({}, [])))
        try:
            return await run_suite(_cases(), client, judge, str(tmp_path), run_id="ck",
                                   opts=SuiteOptions(hard_checks=CHECKLIST_HARD_CHECKS))
        finally:
            await client.aclose()
            await judge.aclose()

    results = {r.case_id: r for r in asyncio.run(go())}
    assert {cid: r.status for cid, r in results.items()} == {
        "C1": "pass", "C2": "fail", "C3": "pass", "C4": "pass", "C5": "pass", "C6": "fail"}
    assert results["C1"].review_reasons() == []  # decided by matching the code
    assert results["C2"].review_reasons() == ["judge model quyết"]
    run = json.loads((tmp_path / "ck" / "run.json").read_text(encoding="utf-8"))
    assert run["judge"]["rubric_version"].startswith("checklist-v1-") and run["human_grades_carried"] == 0

    summary = summarize(list(results.values()), run)
    assert set(summary["needs_review"]) == {"C2", "C6"}
    missing = summary["limitations"]["missing_points"]
    assert missing["cases"] == 2 and missing["examples"]["C2"] == ["2 ngày mỗi tuần"]
    assert "Thiếu ý chính của đáp án" in render_markdown(summary, list(results.values()))
    review = tmp_path / "review.xlsx"
    write_review_workbook(str(review), list(results.values()), {c.case_id: c for c in _cases()})
    ws = openpyxl.load_workbook(review).active
    assert {ws.cell(2, 1).value, ws.cell(3, 1).value} == {"C2", "C6"}
