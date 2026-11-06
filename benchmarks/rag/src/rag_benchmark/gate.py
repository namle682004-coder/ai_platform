"""
Go-live quality gate: turns a suite summary into a GO / NO-GO decision with explicit criteria.

Every criterion is reported (actual vs threshold); blocking criteria decide the exit code, so CI or
the deploy script can refuse to ship. Thresholds live in configs/gate.yaml.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import yaml

DEFAULTS: Dict[str, Any] = {
    "min_cases": 100,
    "min_pass_rate": 0.95,
    "min_pass_rate_ci_low": None,
    "min_group_pass_rate": 0.8,
    "must_pass_all": True,
    "max_review": 0,
    "max_errors": 0,
    "max_unanswerable_failed": 0,
    "max_wrongly_refused": None,
    "max_regressions": 0,
    "judge": {"require_calibration": True, "min_agreement": 0.85, "max_false_pass_rate": 0.1, "min_examples": 30},
    "latency": {"enforce": False, "p95_total_s": 8.0, "p95_ttft_s": 3.0},
}


def load_gate_config(path: Optional[str]) -> Dict[str, Any]:
    cfg = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
    if path:
        with open(path, encoding="utf-8") as f:
            user = yaml.safe_load(f) or {}
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg


def _check(checks: List[Dict[str, Any]], name: str, ok: bool, actual: Any, threshold: Any, blocking: bool = True) -> None:
    checks.append({"name": name, "ok": bool(ok), "actual": actual, "threshold": threshold, "blocking": blocking})


def evaluate_gate(
    summary: Dict[str, Any], cfg: Dict[str, Any], calibration: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    n = summary["cases"]
    rate = summary["pass_rate"]["rate"]

    _check(checks, "Số câu kiểm thử", n >= cfg["min_cases"], n, f">= {cfg['min_cases']}")
    _check(checks, "Tỷ lệ đạt toàn bộ", rate >= cfg["min_pass_rate"], f"{rate:.1%}", f">= {cfg['min_pass_rate']:.0%}")
    if cfg.get("min_pass_rate_ci_low") is not None:
        low = summary["pass_rate"]["low"]
        _check(checks, "Cận dưới KTC 95% tỷ lệ đạt", low >= cfg["min_pass_rate_ci_low"], f"{low:.1%}",
               f">= {cfg['min_pass_rate_ci_low']:.0%}")
    weak = {g: v["rate"] for g, v in summary["by_group"].items() if v["rate"] < cfg["min_group_pass_rate"]}
    _check(checks, "Mỗi nhóm đạt tối thiểu", not weak,
           ", ".join(f"{g} {r:.0%}" for g, r in weak.items()) or "tất cả đạt", f">= {cfg['min_group_pass_rate']:.0%}")
    if cfg["must_pass_all"]:
        bad = summary["must_pass"]["not_passed"]
        _check(checks, "Câu bắt buộc (an toàn, trích dẫn) đạt 100%", not bad,
               ", ".join(bad) or f"{summary['must_pass']['cases']}/{summary['must_pass']['cases']}", "100%")
    _check(checks, "Câu chưa có kết luận (cần chấm tay)", summary["review"] <= cfg["max_review"], summary["review"],
           f"<= {cfg['max_review']}")
    _check(checks, "Lỗi gọi API", len(summary["errors"]) <= cfg["max_errors"], len(summary["errors"]),
           f"<= {cfg['max_errors']}")
    _check(checks, "Bịa khi tài liệu không có thông tin", len(summary["unanswerable_failed"]) <= cfg["max_unanswerable_failed"],
           ", ".join(summary["unanswerable_failed"]) or 0, f"<= {cfg['max_unanswerable_failed']}")
    if cfg.get("max_wrongly_refused") is not None:
        _check(checks, "Từ chối sai khi tài liệu có đáp án", len(summary["wrongly_refused"]) <= cfg["max_wrongly_refused"],
               len(summary["wrongly_refused"]), f"<= {cfg['max_wrongly_refused']}")
    base = summary.get("baseline")
    if base is not None:
        _check(checks, "Hồi quy so với lần chạy trước", len(base["regressions"]) <= cfg["max_regressions"],
               ", ".join(base["regressions"]) or 0, f"<= {cfg['max_regressions']}")

    jcfg = cfg["judge"]
    judge_decided = summary["verdict_sources"].get("judge", 0)
    if judge_decided and jcfg.get("require_calibration"):
        run_judge = (summary.get("run") or {}).get("judge") or {}
        if not calibration:
            _check(checks, "Judge đã hiệu chỉnh với chấm tay", False, "chưa có calibration", "bắt buộc")
        else:
            run = summary.get("run") or {}
            grader = calibration.get("grader") or {}
            run_policy, cal_policy = run.get("id_policy", "all"), grader.get("id_policy", "all")
            run_hard, cal_hard = sorted(run.get("hard_checks") or []), sorted(grader.get("hard_checks") or [])
            same = all(calibration["judge"].get(k) == run_judge.get(k) for k in ("model", "rubric_version"))
            same = same and cal_policy == run_policy and (not cal_hard or cal_hard == run_hard)
            _check(checks, "Calibration cùng model + cách chấm + kiểm tra cứng với lần chạy", same,
                   f"{calibration['judge'].get('model')} / {calibration['judge'].get('rubric_version')} / "
                   f"{cal_policy} / {','.join(cal_hard)}",
                   f"{run_judge.get('model')} / {run_judge.get('rubric_version')} / {run_policy} / {','.join(run_hard)}")
            _check(checks, "Số mẫu hiệu chỉnh judge", calibration["graded"] >= jcfg["min_examples"],
                   calibration["graded"], f">= {jcfg['min_examples']}")
            _check(checks, "Judge khớp chấm tay", calibration["agreement"] >= jcfg["min_agreement"],
                   f"{calibration['agreement']:.1%} (kappa {calibration['kappa']:.2f})", f">= {jcfg['min_agreement']:.0%}")
            _check(checks, "Judge cho đạt sai (người chấm không đạt)",
                   calibration["false_pass_rate"] <= jcfg["max_false_pass_rate"],
                   f"{calibration['false_pass_rate']:.1%}", f"<= {jcfg['max_false_pass_rate']:.0%}")

    lcfg = cfg["latency"]
    p95, ttft = summary["latency_s"]["p95"], summary["ttft_s"]["p95"]
    if p95 is not None:
        _check(checks, "Độ trễ p95 (giây)", p95 <= lcfg["p95_total_s"], p95, f"<= {lcfg['p95_total_s']}",
               blocking=bool(lcfg["enforce"]))
    if ttft is not None:
        _check(checks, "Thời gian ra chữ đầu p95 (giây)", ttft <= lcfg["p95_ttft_s"], ttft, f"<= {lcfg['p95_ttft_s']}",
               blocking=bool(lcfg["enforce"]))

    passed = all(c["ok"] for c in checks if c["blocking"])
    return {"passed": passed, "decision": "GO" if passed else "NO-GO", "checks": checks,
            "warnings": [c["name"] for c in checks if not c["ok"] and not c["blocking"]]}
