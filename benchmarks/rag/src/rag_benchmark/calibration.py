"""
Grader calibration: grade answers people already graded and measure how often the grader agrees.

The automatic verdict decides go-live only when its calibration (same model + grader version) shows
high agreement and, above all, few *false passes* (grader says pass, person said fail) – a grader
that waves bad answers through would let a regression ship. The report also breaks agreement down
(answerable / unanswerable, decided by matching / by the judge model) and shows what each optional
hard check would change, so the grading rules are chosen on evidence.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Sequence

from .evaluators.checks import allowed_identifiers, answer_checks, hard_failures, parse_transcript
from .evaluators.rubric_judge import JudgeClient
from .schemas.dataset import GoldenCase

OPTIONAL_HARD_CHECKS = ("missing_identifiers", "stray_identifiers", "artefacts", "wrongly_refused")


def agreement_stats(pairs: Sequence[tuple]) -> Dict[str, Any]:
    """pairs: (human_pass, judge_pass) booleans."""
    n = len(pairs)
    tp = sum(1 for h, j in pairs if h and j)
    tn = sum(1 for h, j in pairs if not h and not j)
    fp = sum(1 for h, j in pairs if not h and j)  # judge passes what a person failed
    fn = sum(1 for h, j in pairs if h and not j)
    agree = (tp + tn) / n if n else 0.0
    p_h = (tp + fn) / n if n else 0.0
    p_j = (tp + fp) / n if n else 0.0
    expected = p_h * p_j + (1 - p_h) * (1 - p_j)
    kappa = (agree - expected) / (1 - expected) if n and expected < 1 else 0.0
    human_fail = tn + fp
    return {
        "n": n, "agreement": round(agree, 4), "kappa": round(kappa, 4),
        "false_pass_rate": round(fp / human_fail, 4) if human_fail else 0.0,
        "false_fail_rate": round(fn / (tp + fn), 4) if tp + fn else 0.0,
        "confusion": {"human_pass_judge_pass": tp, "human_fail_judge_fail": tn,
                      "human_fail_judge_pass": fp, "human_pass_judge_fail": fn},
    }


def example_turns(case: GoldenCase, answer: str) -> List[Dict[str, Any]]:
    """A graded workbook answer as conversation turns (multi-turn answers are one transcript text)."""
    turns = parse_transcript(answer)
    if len(turns) == 1 and not turns[0]["query"]:
        turns[0]["query"] = " / ".join(case.conversation())
    return turns


async def calibrate(
    judge: JudgeClient,
    cases: Sequence[GoldenCase],
    examples: Sequence[Dict[str, Any]],
    concurrency: int = 2,
    id_policy: str = "all",
    hard_checks: Sequence[str] = ("missing_identifiers", "wrongly_refused", "artefacts"),
) -> Dict[str, Any]:
    """
    Calibrates the automatic verdict the suite actually uses (deterministic checks first, then the
    grader) against human grades; the grader-only agreement is reported alongside.
    """
    by_id = {c.case_id: c for c in cases}
    sem = asyncio.Semaphore(max(1, concurrency))

    async def one(ex: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        case = by_id.get(ex["case_id"])
        if case is None:
            return None
        turns = example_turns(case, ex["answer"])
        async with sem:
            res = await judge.grade(case, turns, context="")
        if res.verdict is None:
            return None
        checks = answer_checks(turns[-1], case.required_identifiers, case.answerable, id_policy,
                               allowed=allowed_identifiers(case))
        judge_pass = res.verdict == "pass"
        return {"case_id": case.case_id, "answerable": case.answerable, "human_pass": bool(ex["human_pass"]),
                "judge_pass": judge_pass, "uncertain": res.uncertain, "checks": checks,
                "hard_failures": hard_failures(checks, hard_checks),
                "judge_reason": res.reason, "items": res.items, "human_notes": ex.get("notes", "")}

    rows: List[Dict[str, Any]] = [r for r in await asyncio.gather(*[one(ex) for ex in examples]) if r is not None]
    for r in rows:
        r["auto_pass"] = r["judge_pass"] and not r["hard_failures"]

    def subset(pred) -> Dict[str, Any]:
        return agreement_stats([(r["human_pass"], r["auto_pass"]) for r in rows if pred(r)])

    variants = {}
    for check in OPTIONAL_HARD_CHECKS:
        enabled = [c for c in hard_checks if c != check] if check in hard_checks else [*hard_checks, check]
        label = ("without " if check in hard_checks else "with ") + check
        variants[label] = agreement_stats(
            [(r["human_pass"], r["judge_pass"] and not hard_failures(r["checks"], enabled)) for r in rows])
    stats = agreement_stats([(r["human_pass"], r["auto_pass"]) for r in rows])
    return {
        "judge": {**judge.identity(), "model": await judge.resolve_model()},
        "grader": {"id_policy": id_policy, "hard_checks": list(hard_checks)},
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "examples": len(examples), "graded": len(rows), **stats,
        "judge_only": agreement_stats([(r["human_pass"], r["judge_pass"]) for r in rows]),
        "breakdown": {
            "answerable": subset(lambda r: r["answerable"]),
            "unanswerable": subset(lambda r: not r["answerable"]),
            "decided_by_matching": subset(lambda r: not r["uncertain"]),
            "decided_by_judge_model": subset(lambda r: r["uncertain"]),
        },
        "hard_check_variants": variants,
        "disagreements": [{k: v for k, v in r.items() if k != "checks"} for r in rows
                          if r["human_pass"] != r["auto_pass"]],
        "rows": [{k: r[k] for k in ("case_id", "answerable", "human_pass", "judge_pass", "auto_pass", "uncertain",
                                    "items")} for r in rows],
    }


def load_examples(path: str) -> List[Dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
