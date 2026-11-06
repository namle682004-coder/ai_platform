"""
CLI for the AIP RAG benchmark and go-live acceptance suite.

  # 1. Workbook -> golden JSONL (+ judge calibration examples from human-graded rows)
  python -m rag_benchmark.cli import-xlsx tests.xlsx --config configs/datasets/khung_ai.yaml --out datasets/acceptance/khung_ai.jsonl
  # 2. Core points per case (drafted by the judge model, reviewed by people in the workbook, imported back)
  python -m rag_benchmark.cli checklist --dataset datasets/acceptance/khung_ai.jsonl
  python -m rag_benchmark.cli checklist --dataset datasets/acceptance/khung_ai.jsonl --import-xlsx datasets/acceptance/khung_ai.checklist.xlsx
  # 3. Calibrate the grader against the human grades (once per judge model / grader version / checklist review)
  python -m rag_benchmark.cli calibrate --dataset datasets/acceptance/khung_ai.jsonl --examples datasets/acceptance/khung_ai.calibration.jsonl --out runs/calibration.json
  # 4. Run the suite against the API, report, and decide go-live (exit code 1 = NO-GO); human grades of
  #    unchanged answers are carried over from --grades-from
  python -m rag_benchmark.cli suite --dataset datasets/acceptance/khung_ai.jsonl --api http://localhost:8010 --tenant <t> \
      --header "X-AIP-Runtime-Token: …" --gate configs/gate.yaml --calibration runs/calibration.json --baseline runs/<prev> \
      --grades-from datasets/acceptance/khung_ai.calibration.jsonl --grades-from runs/<prev>
  # 5. Human review of what the machine could not decide (top of review.xlsx), then re-gate
  python -m rag_benchmark.cli import-grades --run runs/<id> --grades runs/<id>/review.xlsx --gate configs/gate.yaml

Legacy single-track benchmark: `run --dataset … --track end_to_end|fixed_context`, `validate --dataset …`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def _headers(items: List[str]) -> Dict[str, str]:
    out = {}
    for h in items or []:
        name, _, value = h.partition(":")
        if name.strip():
            out[name.strip()] = value.strip()
    return out


def _overrides(items: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for item in items or []:
        key, _, raw = item.partition("=")
        try:
            out[key.strip()] = json.loads(raw)
        except ValueError:
            out[key.strip()] = raw
    return out


def _results_path(run: str) -> Path:
    p = Path(run)
    return p if p.is_file() else p / "results.jsonl"


def _judge_cfg(args: argparse.Namespace):
    from .evaluators.rubric_judge import JudgeConfig

    cfg = JudgeConfig(votes=args.judge_votes, temperature=args.judge_temperature)
    if args.judge_url:
        cfg.base_url = args.judge_url
    if args.judge_model:
        cfg.model = args.judge_model
    return cfg


def _grader(args: argparse.Namespace, dataset: str, cases: Optional[List[Any]] = None):
    """The configured grader; the checklist grader warns about cases without core points."""
    from .evaluators.checklist_judge import ChecklistJudge, checklist_path_for, load_checklist
    from .evaluators.rubric_judge import RubricJudge

    if args.grader == "rubric":
        return RubricJudge(_judge_cfg(args))
    path = args.checklist or checklist_path_for(dataset)
    checklist = load_checklist(path)
    missing = [c.case_id for c in cases or [] if c.answerable and not (checklist.get(c.case_id) or {}).get("core")]
    if missing:
        print(f"WARNING: {len(missing)} answerable cases have no core points in {path} (they stay 'review'); "
              f"run: python -m rag_benchmark.cli checklist --dataset {dataset}", file=sys.stderr)
    return ChecklistJudge(_judge_cfg(args), checklist)


def _hard_checks(args: argparse.Namespace) -> List[str]:
    from .runner.suite import CHECKLIST_HARD_CHECKS, DEFAULT_HARD_CHECKS

    if args.hard_checks is not None:
        return [c for c in args.hard_checks.split(",") if c]
    return list(CHECKLIST_HARD_CHECKS if args.grader == "checklist" else DEFAULT_HARD_CHECKS)


def finish_run(
    run_dir: Path,
    baseline: Optional[str] = None,
    gate_cfg: Optional[str] = None,
    calibration: Optional[str] = None,
    dataset: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Writes summary.json, report.md, review.xlsx (and gate.json); returns the gate result."""
    from .gate import evaluate_gate, load_gate_config
    from .reporting.suite_report import render_markdown, summarize, write_review_workbook
    from .runner.suite import load_cases, load_results

    results = load_results(str(run_dir / "results.jsonl"))
    meta_path = run_dir / "run.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    base = load_results(str(_results_path(baseline))) if baseline else None
    summary = summarize(results, meta, base)
    gate = None
    if gate_cfg:
        cal = json.loads(Path(calibration).read_text(encoding="utf-8")) if calibration else None
        gate = evaluate_gate(summary, load_gate_config(gate_cfg), cal)
        (run_dir / "gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (run_dir / "report.md").write_text(render_markdown(summary, results, gate), encoding="utf-8")
    dataset = dataset or meta.get("dataset")
    cases = {c.case_id: c for c in load_cases(dataset)} if dataset and os.path.exists(dataset) else {}
    write_review_workbook(str(run_dir / "review.xlsx"), results, cases)

    pr = summary["pass_rate"]
    print(f"\nPass rate {pr['rate']:.1%} (95% CI {pr['low']:.1%}–{pr['high']:.1%}): "
          f"{summary['pass']} pass / {summary['fail']} fail / {summary['review']} review of {summary['cases']}")
    print(f"Failed stages: {summary['failed_stages']}")
    if gate is not None:
        print(f"\nGO-LIVE GATE: {gate['decision']}")
        for c in gate["checks"]:
            mark = "OK " if c["ok"] else ("FAIL" if c["blocking"] else "WARN")
            print(f"  [{mark}] {c['name']}: {c['actual']} (threshold {c['threshold']})")
    print(f"\nReport: {run_dir / 'report.md'}\nReview workbook: {run_dir / 'review.xlsx'}")
    return gate


async def _suite(args: argparse.Namespace) -> int:
    from .adapters.rag_api import RagApiClient
    from .grades import load_grades
    from .runner.suite import SuiteOptions, load_cases, run_suite

    cases = load_cases(args.dataset)
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        cases = [c for c in cases if c.case_id in wanted or c.group in wanted]
    if args.limit:
        cases = cases[: args.limit]
    headers = {"X-Tenant-ID": args.tenant, "X-User-Role": args.chat_role, **_headers(args.header)}
    admin = {"X-User-Role": "admin", **_headers(args.admin_header)}
    client = RagApiClient(args.api, headers=headers, admin_headers=admin, stream=args.stream,
                          request_overrides=_overrides(args.request))
    judge = None if args.no_judge else _grader(args, args.dataset, cases)
    run_id = args.run_id or f"suite_{time.strftime('%Y%m%d_%H%M%S')}"
    meta: Dict[str, Any] = {"grader": None if args.no_judge else args.grader, "grades_from": args.grades_from}
    if args.label:
        meta["label"] = args.label
    if getattr(judge, "checklist", None) is not None:
        from .evaluators.checklist_judge import checklist_path_for
        from .runner.provenance import compute_file_sha256

        path = args.checklist or checklist_path_for(args.dataset)
        meta["checklist"] = {"path": path, "sha256": compute_file_sha256(path) if os.path.exists(path) else None,
                             "human_reviewed": sum(1 for e in judge.checklist.values() if e.get("source") == "human")}
    opts = SuiteOptions(
        hard_checks=_hard_checks(args),
        id_policy=args.id_policy,
        concurrency=args.concurrency,
        grades=load_grades(args.grades_from),
        meta=meta,
    )
    try:
        await run_suite(cases, client, judge, args.out_dir, run_id=run_id, dataset_path=args.dataset, opts=opts)
    finally:
        await client.aclose()
        if judge is not None:
            await judge.aclose()
    gate = finish_run(Path(args.out_dir) / run_id, args.baseline, args.gate, args.calibration, args.dataset)
    return 0 if gate is None or gate["passed"] else 1


async def _regrade(args: argparse.Namespace) -> int:
    from .grades import load_grades
    from .runner.suite import SuiteOptions, load_cases, regrade_run

    src = Path(args.run)
    meta_path = src / "run.json"
    dataset = args.dataset or (json.loads(meta_path.read_text(encoding="utf-8")).get("dataset")
                               if meta_path.exists() else None)
    if not dataset or not os.path.exists(dataset):
        print("Dataset not found: pass --dataset", file=sys.stderr)
        return 2
    cases = load_cases(dataset)
    judge = _grader(args, dataset, cases)
    run_id = args.run_id or f"{src.name}-{args.grader}"
    opts = SuiteOptions(hard_checks=_hard_checks(args), id_policy=args.id_policy, concurrency=args.concurrency,
                        grades=load_grades(args.grades_from), meta={"grader": args.grader})
    try:
        await regrade_run(str(src), cases, judge, args.out_dir or str(src.parent), run_id, opts)
    finally:
        await judge.aclose()
    gate = finish_run(Path(args.out_dir or src.parent) / run_id, args.baseline, args.gate, args.calibration, dataset)
    return 0 if gate is None or gate["passed"] else 1


async def _calibrate(args: argparse.Namespace) -> int:
    from .calibration import calibrate, load_examples
    from .runner.suite import load_cases

    cases = load_cases(args.dataset)
    judge = _grader(args, args.dataset, cases)
    try:
        report = await calibrate(judge, cases, load_examples(args.examples), args.concurrency,
                                 id_policy=args.id_policy, hard_checks=_hard_checks(args))
    finally:
        await judge.aclose()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def line(name: str, s: Dict[str, Any]) -> str:
        return (f"  {name:<28} n={s['n']:<4} agreement {s['agreement']:.1%}  kappa {s['kappa']:.2f}  "
                f"false pass {s['false_pass_rate']:.1%}  false fail {s['false_fail_rate']:.1%}")

    print(f"Grader {report['judge']['rubric_version']} on {report['judge']['model']} "
          f"(hard checks: {', '.join(report['grader']['hard_checks']) or '-'}) – {report['graded']} examples -> {args.out}")
    print(line("checks + grader", report))
    print(line("grader only", report["judge_only"]))
    for name, s in report["breakdown"].items():
        print(line(name, s))
    for name, s in report["hard_check_variants"].items():
        print(line(name, s))
    return 0


async def _checklist(args: argparse.Namespace) -> int:
    from .evaluators.checklist_judge import (
        ChecklistJudge,
        build_checklist,
        checklist_path_for,
        import_checklist_workbook,
        load_checklist,
        save_checklist,
        write_checklist_workbook,
    )
    from .runner.suite import load_cases

    cases = load_cases(args.dataset)
    path = args.out or checklist_path_for(args.dataset)
    xlsx = args.xlsx or os.path.splitext(path)[0] + ".xlsx"
    entries = load_checklist(path)
    if args.import_xlsx:
        n = import_checklist_workbook(args.import_xlsx, cases, entries)
        print(f"Applied {n} reviewed rows from {args.import_xlsx}")
    else:
        judge = ChecklistJudge(_judge_cfg(args), entries)
        try:
            stats = await build_checklist(judge, cases, entries, overwrite=args.overwrite,
                                          concurrency=args.concurrency)
        finally:
            await judge.aclose()
        print(f"Core points: {stats}")
    ordered = {c.case_id: entries[c.case_id] for c in cases if c.case_id in entries}
    save_checklist(path, ordered)
    write_checklist_workbook(xlsx, cases, ordered)
    reviewed = sum(1 for e in ordered.values() if e.get("source") == "human")
    print(f"{len(ordered)} cases -> {path} ({reviewed} human-reviewed); review workbook -> {xlsx}")
    return 0


def _add_grader_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--grader", choices=["checklist", "rubric"], default="checklist",
                   help="checklist: core points checked one by one (works with a small judge model); "
                        "rubric: one holistic verdict (needs a strong judge model)")
    p.add_argument("--checklist", default=None, help="core points JSONL (default <dataset>.checklist.jsonl)")
    p.add_argument("--hard-checks", default=None,
                   help="comma-separated deterministic checks that fail a case (default per grader: checklist "
                        "'wrongly_refused,artefacts', rubric 'missing_identifiers,wrongly_refused,artefacts'; "
                        "also: stray_identifiers)")
    p.add_argument("--id-policy", choices=["all", "any"], default="all",
                   help="required identifiers: all must appear, or at least one (when missing_identifiers is on)")
    _add_judge_args(p)


def _add_judge_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--judge-url", default=None, help="OpenAI-compatible base URL (default $LLM_JUDGE_URL)")
    p.add_argument("--judge-model", default=None, help="default $LLM_JUDGE_MODEL or the server's first model")
    p.add_argument("--judge-votes", type=int, default=1, help="votes per verdict (majority, ties fail)")
    p.add_argument("--judge-temperature", type=float, default=0.0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("import-xlsx", help="Acceptance workbook -> golden JSONL (+ calibration examples)")
    p.add_argument("xlsx")
    p.add_argument("--config", required=True, help="dataset config YAML (sheet, columns, critical groups)")
    p.add_argument("--out", required=True)
    p.add_argument("--calibration-out", default=None)

    p = sub.add_parser("suite", help="Run the acceptance suite against the RAG API, report and gate")
    p.add_argument("--dataset", required=True)
    p.add_argument("--api", default="http://localhost:8010")
    p.add_argument("--tenant", required=True)
    p.add_argument("--chat-role", default="user", help="role of the simulated end user")
    p.add_argument("--header", action="append", default=[], help="'Name: value' sent on every call (repeatable)")
    p.add_argument("--admin-header", action="append", default=[], help="extra headers for trace/index calls")
    p.add_argument("--request", action="append", default=[], help="chat body override key=json (repeatable)")
    p.add_argument("--stream", action="store_true")
    p.add_argument("--no-judge", action="store_true", help="deterministic checks only; the rest goes to review")
    _add_grader_args(p)
    p.add_argument("--grades-from", action="append", default=[],
                   help="human grades to carry over to unchanged answers: calibration JSONL or a run dir (repeatable)")
    p.add_argument("--concurrency", type=int, default=1)
    p.add_argument("--only", default="", help="comma-separated case ids or groups")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--out-dir", default="benchmarks/rag/runs")
    p.add_argument("--run-id", default=None)
    p.add_argument("--label", default="")
    p.add_argument("--baseline", default=None, help="previous run dir (or results.jsonl) for the regression diff")
    p.add_argument("--gate", default=None, help="gate YAML; exit code 1 when the gate fails")
    p.add_argument("--calibration", default=None, help="judge calibration JSON (required when the judge decides)")

    p = sub.add_parser("calibrate", help="Measure judge agreement with human grades")
    p.add_argument("--dataset", required=True)
    p.add_argument("--examples", required=True, help="calibration JSONL (case_id, answer, human_pass)")
    p.add_argument("--out", required=True)
    p.add_argument("--concurrency", type=int, default=2)
    _add_grader_args(p)  # grader, checklist, hard checks and id policy must match the suite runs it gates

    p = sub.add_parser("regrade", help="Grade a finished run's stored answers again (no RAG calls), report and gate")
    p.add_argument("--run", required=True, help="run directory to re-grade")
    p.add_argument("--dataset", default=None, help="default: the dataset recorded in run.json")
    p.add_argument("--run-id", default=None, help="new run id (default <run>-<grader>)")
    p.add_argument("--out-dir", default=None, help="default: next to the source run")
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--grades-from", action="append", default=[])
    p.add_argument("--baseline", default=None)
    p.add_argument("--gate", default=None)
    p.add_argument("--calibration", default=None)
    _add_grader_args(p)

    p = sub.add_parser("checklist", help="Draft / review the core points the checklist grader checks")
    p.add_argument("--dataset", required=True)
    p.add_argument("--out", default=None, help="checklist JSONL (default <dataset>.checklist.jsonl)")
    p.add_argument("--xlsx", default=None, help="review workbook written next to it (default <out>.xlsx)")
    p.add_argument("--import-xlsx", default=None, help="apply a reviewed workbook (rows ticked 'Đã duyệt')")
    p.add_argument("--overwrite", action="store_true", help="redraft machine drafts (human-reviewed rows are kept)")
    p.add_argument("--concurrency", type=int, default=4)
    _add_judge_args(p)

    for name, help_text in (("report", "Re-render report / gate of a finished run"),
                            ("gate", "Evaluate the go-live gate of a finished run (exit 1 = NO-GO)"),
                            ("import-grades", "Apply human grades from a review workbook, then report / gate")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--run", required=True, help="run directory")
        p.add_argument("--baseline", default=None)
        p.add_argument("--gate", default=None if name == "report" else "benchmarks/rag/configs/gate.yaml")
        p.add_argument("--calibration", default=None)
        if name == "import-grades":
            p.add_argument("--grades", required=True, help="review workbook with the 'Chấm tay' column filled")

    p = sub.add_parser("run", help="Legacy single-track benchmark")
    p.add_argument("--dataset", required=True)
    p.add_argument("--track", choices=["end_to_end", "fixed_context"], default="end_to_end")
    p.add_argument("--system-id", default="local_aip_rag_v1")
    p.add_argument("--output-dir", default="runs")
    p = sub.add_parser("validate", help="Validate dataset JSONL schema")
    p.add_argument("--dataset", required=True)

    args = parser.parse_args()
    if args.command == "import-xlsx":
        from .importers.acceptance_xlsx import import_workbook, load_config, write_outputs

        cases, calibration = import_workbook(args.xlsx, load_config(args.config))
        out, cal = write_outputs(cases, calibration, args.out, args.calibration_out)
        print(f"{len(cases)} cases -> {out} ({sum(c.must_pass for c in cases)} must-pass, "
              f"{sum(not c.answerable for c in cases)} unanswerable); {len(calibration)} calibration examples -> {cal}")
    elif args.command == "suite":
        sys.exit(asyncio.run(_suite(args)))
    elif args.command == "calibrate":
        sys.exit(asyncio.run(_calibrate(args)))
    elif args.command == "checklist":
        sys.exit(asyncio.run(_checklist(args)))
    elif args.command == "regrade":
        sys.exit(asyncio.run(_regrade(args)))
    elif args.command in ("report", "gate", "import-grades"):
        run_dir = Path(args.run)
        if args.command == "import-grades":
            from .reporting.suite_report import import_grades
            from .runner.suite import load_results, write_results

            results = load_results(str(run_dir / "results.jsonl"))
            n = import_grades(args.grades, results)
            write_results(run_dir / "results.jsonl", results)
            print(f"Applied {n} human grades")
        gate = finish_run(run_dir, args.baseline, args.gate, args.calibration)
        sys.exit(0 if gate is None or gate["passed"] else 1)
    elif args.command == "validate":
        from .runner.orchestrator import load_dataset

        cases = load_dataset(args.dataset)
        print(f"SUCCESS: Validated {len(cases)} approved cases in {args.dataset}")
    elif args.command == "run":
        from .reporting.export_markdown import generate_markdown_report
        from .runner.orchestrator import load_dataset, run_benchmark_track

        cases = load_dataset(args.dataset)
        run_id = f"run_{time.strftime('%Y%m%d_%H%M%S')}"
        results = asyncio.run(run_benchmark_track(
            cases=cases, track=args.track, system_id=args.system_id, run_id=run_id,
            output_dir=args.output_dir, dataset_path=args.dataset,
        ))
        report_md = generate_markdown_report(results, run_id=run_id, track=args.track)
        report_file = os.path.join(args.output_dir, run_id, "benchmark_report.md")
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report_md)
        print(f"\nSUCCESS: Report exported to {report_file}\n\n{report_md}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
