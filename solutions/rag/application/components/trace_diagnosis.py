"""
Attributes a failed turn to the pipeline stage that lost the answer, from its stored trace.

With gold evidence (evaluation: identifiers / quotes the answer must rest on) the evidence is
followed through the pipeline and the first stage where it disappears is blamed:

    ingestion   – not in any indexed chunk (parsing / chunking lost it)
    routing     – the turn never reached retrieval (classified as chit-chat / support / unclear)
    retrieval   – indexed but not among the hybrid-search candidates
    rerank      – retrieved but ranked below what the context keeps
    gate        – in the reranked pool but the evidence gate refused
    context     – passed the gate but not selected into the prompt (selection / window fitting)
    verification– the model wrote it but verification removed the sentence
    generation  – the model had the evidence and still answered wrongly / incompletely

Without gold evidence (user feedback) the decision signals of the trace are used instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .lexical_evidence import extract_identifiers, normalize_for_match

STAGE_ORDER = (
    "ingestion", "routing", "retrieval", "rerank", "gate", "context", "verification", "generation",
)
NON_RETRIEVAL_ROUTES = ("support", "clarification", "cache", "adhoc")
REFUSAL_ROUTES = ("gate_refusal", "gate_clarification", "generation_refusal", "identifier_not_found")


@dataclass
class Diagnosis:
    stage: Optional[str]  # None: no stage lost the evidence (or nothing to diagnose)
    reason: str
    found: Dict[str, List[str]] = field(default_factory=dict)  # stage -> needles present there
    missing: Dict[str, List[str]] = field(default_factory=dict)  # stage -> needles absent there
    route: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"stage": self.stage, "reason": self.reason, "found": self.found, "missing": self.missing,
                "route": self.route}


def _stages(trace: Dict[str, Any], name: str) -> List[Dict[str, Any]]:
    return [s for s in trace.get("stages") or [] if s.get("stage") == name]


def _last(trace: Dict[str, Any], name: str) -> Optional[Dict[str, Any]]:
    found = _stages(trace, name)
    return found[-1] if found else None


def final_route(trace: Dict[str, Any]) -> str:
    route = _last(trace, "route")
    return str((route or {}).get("route") or (trace.get("outcome") or {}).get("route") or "")


def _norm(text: str) -> str:
    return " ".join(normalize_for_match(text or "").split())


def needle_in_refs(needle: str, refs: Iterable[Dict[str, Any]]) -> bool:
    up = needle.strip().upper()
    norm = _norm(needle)
    for r in refs:
        if up and up in (r.get("ids") or []):
            return True
        if norm and norm in _norm(r.get("text") or ""):
            return True
    return False


def needle_in_text(needle: str, text: str) -> bool:
    return bool(needle) and (needle.strip().upper() in (text or "").upper() or _norm(needle) in _norm(text))


def context_refs(trace: Dict[str, Any]) -> List[Dict[str, Any]]:
    ctx = _last(trace, "context")
    if ctx:
        return list(ctx.get("chunks") or [])
    route = _last(trace, "route")
    return list((route or {}).get("context") or [])


def retrieval_refs(trace: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [r for s in _stages(trace, "retrieval") for r in s.get("candidates") or []]


def reranked_refs(trace: Dict[str, Any]) -> List[Dict[str, Any]]:
    rr = _last(trace, "rerank")
    return list((rr or {}).get("ranked") or [])


def rerank_keep(trace: Dict[str, Any]) -> int:
    """How deep in the rerank order the context reaches (the configured passage budget)."""
    cfg = trace.get("config") or {}
    return max(int(cfg.get("context_max_chunks") or 0), len(context_refs(trace)), 1)


def diagnose(
    trace: Optional[Dict[str, Any]],
    needles: Sequence[str] = (),
    indexed: Optional[Sequence[str]] = None,
    expect_answer: bool = True,
    answer_correct: Optional[bool] = None,
) -> Diagnosis:
    """
    `needles`: gold identifiers / quotes; `indexed`: the needles present anywhere in the index
    (None: unknown); `expect_answer`: the documents answer the question; `answer_correct`: verdict on
    the final answer when known (judge / human).
    """
    if not trace:
        return Diagnosis(stage=None, reason="no trace recorded")
    route = final_route(trace)
    outcome = trace.get("outcome") or {}
    answer = str(outcome.get("answer") or "")
    needles = [n for n in dict.fromkeys(n.strip() for n in needles) if n]

    if not expect_answer:
        # The documents do not answer it: failing here means the system answered anyway.
        if answer_correct is False and route not in REFUSAL_ROUTES:
            return Diagnosis(stage="generation", reason="answered a question the documents do not cover", route=route)
        return Diagnosis(stage=None, reason="no stage lost evidence", route=route)

    if not needles:
        return _diagnose_by_signals(trace, route, answer_correct)

    found: Dict[str, List[str]] = {}
    missing: Dict[str, List[str]] = {}

    def check(stage: str, present: List[str]) -> List[str]:
        found[stage] = present
        missing[stage] = [n for n in needles if n not in present]
        return missing[stage]

    if indexed is not None and check("ingestion", [n for n in needles if n in indexed]) == needles:
        return Diagnosis("ingestion", "gold evidence is in no indexed chunk", found, missing, route)
    if route in NON_RETRIEVAL_ROUTES or not _stages(trace, "retrieval"):
        return Diagnosis("routing", f"turn routed to '{route or 'none'}' without document retrieval",
                         found, missing, route)

    retrieved = retrieval_refs(trace)
    # Retrieval candidates are traced with identifiers only: text evidence is checked from rerank on.
    if any(r.get("text") for r in retrieved) or all(extract_identifiers(n) == [n.upper()] for n in needles):
        lost = check("retrieval", [n for n in needles if needle_in_refs(n, retrieved)])
        if len(lost) == len(needles):
            return Diagnosis("retrieval", "gold evidence not among the search candidates", found, missing, route)

    ranked = reranked_refs(trace)
    keep = rerank_keep(trace)
    in_top = [n for n in needles if needle_in_refs(n, ranked[:keep])]
    check("rerank", in_top)
    gate = _last(trace, "gate") or {}
    if gate.get("decision") in ("no_evidence", "identifier_not_found"):
        return Diagnosis("gate", f"evidence gate decided '{gate.get('decision')}' with gold evidence retrieved "
                         f"(top rerank {gate.get('top_rerank')}, lexical {gate.get('best_lexical')})",
                         found, missing, route)

    ctx = context_refs(trace)
    in_ctx = [n for n in needles if needle_in_refs(n, ctx)]
    check("context", in_ctx)
    if not in_ctx:
        if not in_top:
            return Diagnosis("rerank", f"gold evidence ranked below the top {keep} candidates", found, missing, route)
        return Diagnosis("context", "gold evidence passed rerank but was not put in the prompt", found, missing, route)

    in_answer = [n for n in needles if needle_in_text(n, answer)]
    check("answer", in_answer)
    if answer_correct is True or (answer_correct is None and len(in_answer) == len(needles)):
        return Diagnosis(None, "evidence reached the answer", found, missing, route)

    dropped = [d for s in _stages(trace, "verification") + _stages(trace, "correction") for d in s.get("dropped") or []]
    raw = " ".join(str(s.get("raw_answer") or "") for s in _stages(trace, "generation"))
    removed = [n for n in in_ctx if n not in in_answer and needle_in_text(n, raw)
               and any(needle_in_text(n, d.get("sentence", "")) for d in dropped)]
    if removed:
        return Diagnosis("verification", f"verification removed answer sentences with {', '.join(removed)}",
                         found, missing, route)
    if len(in_ctx) < len(needles) and not [n for n in in_ctx if n not in in_answer]:
        # Everything the prompt had reached the answer; the rest never reached the prompt.
        stage = "rerank" if len(in_top) < len(needles) else "context"
        return Diagnosis(stage, "part of the gold evidence never reached the prompt", found, missing, route)
    if route == "generation_refusal":
        return Diagnosis("generation", "model refused although the prompt held the evidence", found, missing, route)
    return Diagnosis("generation", "prompt held the evidence; the answer is wrong or incomplete", found, missing, route)


def _diagnose_by_signals(trace: Dict[str, Any], route: str, answer_correct: Optional[bool]) -> Diagnosis:
    if answer_correct is True:
        return Diagnosis(None, "answer judged correct", route=route)
    gate = _last(trace, "gate") or {}
    if route in NON_RETRIEVAL_ROUTES:
        return Diagnosis("routing", f"turn routed to '{route}' without document retrieval", route=route)
    if route in ("gate_refusal", "gate_clarification"):
        stage = "retrieval" if not reranked_refs(trace) or (gate.get("top_rerank") or 0) < (gate.get("min_rerank") or 0) / 2 else "gate"
        return Diagnosis(stage, f"evidence gate refused (top rerank {gate.get('top_rerank')}, "
                         f"lexical {gate.get('best_lexical')})", route=route)
    if route == "generation_refusal":
        return Diagnosis("generation", "model refused over the retrieved passages", route=route)
    corrections = _stages(trace, "correction")
    if corrections and not corrections[-1].get("accepted"):
        return Diagnosis("verification", "verification removed sentences and the correction failed", route=route)
    return Diagnosis("generation", "no retrieval-side signal; answer quality", route=route)
