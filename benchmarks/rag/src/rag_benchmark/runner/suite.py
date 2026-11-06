"""
End-to-end acceptance suite: runs every golden case against the live RAG API (multi-turn and
separate-session cases included), fetches the pipeline trace of each turn, grades the answer
(deterministic checks + rubric judge) and attributes failures to the stage that lost the evidence.

Outputs in <out_dir>/<run_id>/: run.json (provenance), results.jsonl (one CaseResult per case) and
traces/<case_id>/s<session>_t<turn>.json (full traces, for offline drill-down).

Human verdicts given earlier to the same answers (SuiteOptions.grades) are carried over, so people
only grade what changed.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..adapters.rag_api import RagApiClient, TurnResult
from ..evaluators.checks import allowed_identifiers, answer_checks, hard_failures
from ..evaluators.rubric_judge import JudgeClient
from ..evaluators.stage_metrics import indexed_needles, stage_metrics
from ..grades import Grade, carry_grades
from ..runtime_bridge import context_refs, diagnose
from ..schemas.dataset import GoldenCase, SessionMode
from ..schemas.suite import FAIL, PASS, REVIEW, CaseResult, GradedSession
from .provenance import compute_file_sha256, get_git_commit

DEFAULT_HARD_CHECKS = ("missing_identifiers", "wrongly_refused", "artefacts")
# The checklist grader judges content by core points; a missing code is not a failure by itself.
CHECKLIST_HARD_CHECKS = ("wrongly_refused", "artefacts")


@dataclass
class SuiteOptions:
    hard_checks: Sequence[str] = DEFAULT_HARD_CHECKS
    id_policy: str = "all"
    concurrency: int = 1
    save_traces: bool = True
    grades: Dict[str, Dict[str, Grade]] = field(default_factory=dict)  # grades.load_grades()
    meta: Dict[str, Any] = field(default_factory=dict)
    # Consecutive cases that end in an API error (after the client's busy waits) before the run stops:
    # a failing service is not evaluated further, and is given no more load.
    max_consecutive_errors: int = 5


def _errored(res: CaseResult) -> bool:
    return any(s.checks.get("error") for s in res.sessions)


def _skipped(case: GoldenCase, run_id: str, reason: str) -> CaseResult:
    return CaseResult(
        run_id=run_id, case_id=case.case_id, group=case.group, category=case.category,
        session_mode=case.session_mode.value, answerable=case.answerable, must_pass=case.must_pass,
        required_identifiers=case.required_identifiers,
        sessions=[GradedSession(checks={"error": reason}, status=REVIEW, reasons=[reason])],
        auto_status=REVIEW, reasons=[reason],
    ).finalize()


def _context_text(trace: Optional[Dict[str, Any]]) -> str:
    if not trace:
        return ""
    return "\n\n".join(
        f"[{r.get('title') or r.get('doc_id')} – {r.get('heading') or ''}]\n{r['text']}"
        for r in context_refs(trace) if r.get("text")
    )


async def grade_session(
    case: GoldenCase,
    turns: List[TurnResult],
    judge: Optional[JudgeClient],
    snapshot: Optional[Dict[str, Any]],
    opts: SuiteOptions,
) -> GradedSession:
    last = turns[-1]
    checks = answer_checks(last.summary(), case.required_identifiers, case.answerable, opts.id_policy,
                           allowed=allowed_identifiers(case, [t.query for t in turns]))
    needles = case.evidence_needles() if case.answerable else []
    indexed = indexed_needles(needles, snapshot) if needles else None
    reasons = hard_failures(checks, opts.hard_checks)

    judge_res = None
    if judge is not None and not checks.get("error"):
        judge_res = await judge.grade(case, [t.summary() for t in turns], _context_text(last.trace))
    if reasons:
        status = FAIL
    elif judge_res is not None and judge_res.verdict:
        status = PASS if judge_res.verdict == "pass" else FAIL
    else:
        status = REVIEW
    if judge_res is not None and judge_res.verdict == "fail":
        reasons.append("judge: " + (judge_res.violated or judge_res.reason or "fail"))

    diagnosis = None
    if status != PASS:
        diagnosis = diagnose(
            last.trace, needles=needles, indexed=indexed, expect_answer=case.answerable,
            answer_correct=False if status == FAIL else None,
        ).to_dict()
    return GradedSession(
        turns=[t.summary() for t in turns], checks=checks, judge=judge_res.to_dict() if judge_res else None,
        stage_metrics=stage_metrics(last.trace, needles, indexed), diagnosis=diagnosis, status=status,
        reasons=reasons,
    )


def combine(case: GoldenCase, run_id: str, sessions: List[GradedSession]) -> CaseResult:
    statuses = [s.status for s in sessions]
    auto = FAIL if FAIL in statuses else (REVIEW if REVIEW in statuses or not statuses else PASS)
    failed = next((s for s in sessions if s.status != PASS), None)
    judged = any(s.judge and s.judge.get("verdict") for s in sessions)
    checked = any(s.reasons and not (s.judge and s.judge.get("verdict") == "fail") for s in sessions)
    return CaseResult(
        run_id=run_id, case_id=case.case_id, group=case.group, category=case.category,
        session_mode=case.session_mode.value, answerable=case.answerable, must_pass=case.must_pass,
        required_identifiers=case.required_identifiers, sessions=sessions, auto_status=auto,
        reasons=[f"session {i}: {r}" if len(sessions) > 1 else r
                 for i, s in enumerate(sessions, start=1) for r in s.reasons],
        verdict_source="checks" if checked else ("judge" if judged else "auto"),
        failed_stage=(failed.diagnosis or {}).get("stage") if failed else None,
    ).finalize()


async def run_case(
    case: GoldenCase,
    client: RagApiClient,
    judge: Optional[JudgeClient],
    snapshot: Optional[Dict[str, Any]],
    run_id: str,
    opts: SuiteOptions,
    trace_dir: Optional[Path],
) -> CaseResult:
    convo = case.conversation()
    groups = [[t] for t in convo] if case.session_mode == SessionMode.SEPARATE_SESSIONS else [convo]
    sessions: List[GradedSession] = []
    for si, group in enumerate(groups, start=1):
        session_id = client.new_session()
        turns: List[TurnResult] = []
        for ti, query in enumerate(group, start=1):
            turn = await client.chat(query, session_id)
            if turn.trace_id and not turn.error:
                turn.trace = await client.fetch_trace(turn.trace_id)
            if trace_dir is not None and turn.trace is not None:
                path = trace_dir / case.case_id / f"s{si}_t{ti}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(turn.trace, ensure_ascii=False, indent=1), encoding="utf-8")
            turns.append(turn)
            if turn.error:
                break
        sessions.append(await grade_session(case, turns, judge, snapshot, opts))
    return combine(case, run_id, sessions)


async def run_suite(
    cases: List[GoldenCase],
    client: RagApiClient,
    judge: Optional[JudgeClient],
    out_dir: str,
    run_id: Optional[str] = None,
    dataset_path: Optional[str] = None,
    opts: Optional[SuiteOptions] = None,
) -> List[CaseResult]:
    opts = opts or SuiteOptions()
    run_id = run_id or f"suite_{time.strftime('%Y%m%d_%H%M%S')}"
    target = Path(out_dir) / run_id
    target.mkdir(parents=True, exist_ok=True)
    trace_dir = target / "traces" if opts.save_traces else None

    snapshot = await client.index_snapshot()
    meta = {
        "run_id": run_id,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "git_commit": get_git_commit(),
        "dataset": dataset_path,
        "dataset_sha256": compute_file_sha256(dataset_path) if dataset_path and os.path.exists(dataset_path) else None,
        "cases": len(cases),
        "api": client.base_url,
        "stream": client.stream,
        "request": client.request_overrides,
        "judge": judge.identity() if judge else None,
        "hard_checks": list(opts.hard_checks),
        "id_policy": opts.id_policy,
        "index_snapshot_chunks": (snapshot or {}).get("chunk_count"),
        **opts.meta,
    }
    if judge is not None:
        meta["judge"]["model"] = await judge.resolve_model()

    sem = asyncio.Semaphore(max(1, opts.concurrency))
    done = 0
    consecutive_errors = 0
    aborted: Optional[str] = None

    async def one(case: GoldenCase) -> CaseResult:
        nonlocal done, consecutive_errors, aborted
        async with sem:
            if aborted:
                res = _skipped(case, run_id, aborted)
            else:
                res = await run_case(case, client, judge, snapshot, run_id, opts, trace_dir)
                consecutive_errors = consecutive_errors + 1 if _errored(res) else 0
                if opts.max_consecutive_errors and consecutive_errors >= opts.max_consecutive_errors:
                    aborted = (f"not run: the service failed {consecutive_errors} cases in a row "
                               "(run stopped to protect it)")
                    print(f"!! {aborted}", flush=True)
        done += 1
        lat = max(res.latencies(), default=0.0)
        print(f"[{done}/{len(cases)}] {case.case_id:<10} {res.status.upper():<6} {lat:5.1f}s "
              f"{(res.failed_stage or '-'):<12} {('; '.join(res.reasons))[:110]}", flush=True)
        return res

    results = await asyncio.gather(*[one(c) for c in cases])
    carried = carry_grades(results, opts.grades)
    meta["human_grades_carried"] = len(carried)
    if carried:
        print(f"Carried {len(carried)} human grades of unchanged answers", flush=True)
    trace_files = sorted(trace_dir.rglob("*.json")) if trace_dir is not None and trace_dir.exists() else []
    if trace_files:
        # Settings that change answers, as the server reported them (comparable across runs).
        meta["server_config"] = json.loads(trace_files[0].read_text(encoding="utf-8")).get("config")
    meta["traced_turns"] = len(trace_files)
    meta["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    meta["aborted"] = aborted
    (target / "run.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    write_results(target / "results.jsonl", results)
    return list(results)


async def regrade_run(
    run_dir: str,
    cases: List[GoldenCase],
    judge: Optional[JudgeClient],
    out_dir: str,
    run_id: str,
    opts: Optional[SuiteOptions] = None,
) -> List[CaseResult]:
    """
    Grades the stored answers and traces of a finished run again with the current grader (the RAG
    system is not called), e.g. after a grader change or a checklist review. Human verdicts are kept.
    """
    opts = opts or SuiteOptions()
    src = Path(run_dir)
    by_id = {c.case_id: c for c in cases}
    turn_fields = set(TurnResult.__dataclass_fields__) - {"trace"}
    sem = asyncio.Semaphore(max(1, opts.concurrency))

    def turn_of(case_id: str, si: int, ti: int, summary: Dict[str, Any]) -> TurnResult:
        turn = TurnResult(**{k: v for k, v in summary.items() if k in turn_fields})
        path = src / "traces" / case_id / f"s{si}_t{ti}.json"
        turn.trace = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        return turn

    async def one(old: CaseResult) -> Optional[CaseResult]:
        case = by_id.get(old.case_id)
        if case is None:
            return None
        sessions = []
        for si, s in enumerate(old.sessions, start=1):
            turns = [turn_of(old.case_id, si, ti, t) for ti, t in enumerate(s.turns, start=1)]
            async with sem:
                graded = await grade_session(case, turns, judge, None, opts)
            # The index snapshot of the original run is not stored: keep its index recall.
            if graded.stage_metrics is not None and (s.stage_metrics or {}).get("index_recall") is not None:
                graded.stage_metrics["index_recall"] = s.stage_metrics["index_recall"]
            sessions.append(graded)
        res = combine(case, run_id, sessions)
        res.human_status, res.human_notes, res.human_source = old.human_status, old.human_notes, old.human_source
        return res.finalize()

    results = [r for r in await asyncio.gather(*[one(r) for r in load_results(str(src / "results.jsonl"))]) if r]
    carry_grades(results, opts.grades)
    target = Path(out_dir) / run_id
    target.mkdir(parents=True, exist_ok=True)
    meta_path = src / "run.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta.update({
        "run_id": run_id, "regraded_from": str(src), "regraded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "judge": {**judge.identity(), "model": await judge.resolve_model()} if judge else None,
        "hard_checks": list(opts.hard_checks), "id_policy": opts.id_policy, **opts.meta,
    })
    (target / "run.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    write_results(target / "results.jsonl", results)
    return results


def write_results(path: Path, results: Sequence[CaseResult]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(r.model_dump_json() + "\n")


def load_cases(path: str) -> List[GoldenCase]:
    with open(path, encoding="utf-8") as f:
        cases = [GoldenCase.model_validate_json(line) for line in f if line.strip()]
    return [c for c in cases if c.is_approved()]


def load_results(path: str) -> List[CaseResult]:
    with open(path, encoding="utf-8") as f:
        return [CaseResult.model_validate_json(line) for line in f if line.strip()]
