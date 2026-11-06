"""Result records of the end-to-end acceptance suite (one per golden case)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

PASS, FAIL, REVIEW = "pass", "fail", "review"


class GradedSession(BaseModel):
    """One graded conversation of a case (separate-session cases have several)."""
    turns: List[Dict[str, Any]] = Field(default_factory=list)  # TurnResult.summary() per turn
    checks: Dict[str, Any] = Field(default_factory=dict)
    judge: Optional[Dict[str, Any]] = None
    stage_metrics: Optional[Dict[str, Any]] = None
    diagnosis: Optional[Dict[str, Any]] = None
    status: str = REVIEW
    reasons: List[str] = Field(default_factory=list)


class CaseResult(BaseModel):
    run_id: str
    case_id: str
    group: str = ""
    category: str = ""
    session_mode: str = "single"
    answerable: bool = True
    must_pass: bool = False
    required_identifiers: List[str] = Field(default_factory=list)
    sessions: List[GradedSession] = Field(default_factory=list)
    auto_status: str = REVIEW  # verdict of checks + judge
    human_status: Optional[str] = None  # verdict of a person (overrides auto_status)
    human_notes: str = ""
    human_source: str = ""  # "" = graded on this run; else the run / file the unchanged answer was graded in
    status: str = REVIEW
    reasons: List[str] = Field(default_factory=list)
    verdict_source: str = "auto"  # "auto" | "judge" | "checks" | "human"
    failed_stage: Optional[str] = None

    def finalize(self) -> "CaseResult":
        if self.human_status in (PASS, FAIL):
            self.status, self.verdict_source = self.human_status, "human"
        else:
            self.status = self.auto_status
        return self

    def review_reasons(self) -> List[str]:
        """Why a person should look at this case (empty: a human verdict exists or the machine is sure)."""
        if self.human_status in (PASS, FAIL):
            return []
        out = []
        if self.auto_status == REVIEW:
            out.append("chưa có kết luận")
        if any(s.judge and s.judge.get("uncertain") for s in self.sessions):
            out.append("judge model quyết")
        if any(s.checks.get("stray_identifiers") for s in self.sessions):
            out.append("có mã ngoài đáp án")
        return out

    def latencies(self) -> List[float]:
        return [t["latency_s"] for s in self.sessions for t in s.turns if t.get("latency_s") is not None]

    def ttfts(self) -> List[float]:
        return [t["ttft_s"] for s in self.sessions for t in s.turns if t.get("ttft_s") is not None]
