"""
Deterministic answer checks: what a machine can decide without a judge.

  missing_identifiers – required codes / document numbers absent from the graded answer
  wrongly_refused     – refused or escalated although gold evidence exists in the documents
  artefacts           – formatting debris that must never reach users
  stray_identifiers   – codes in the answer body that neither the question nor the gold answer mention
                        (a review signal: often a wrong / example code, sometimes a correct extra one)
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..runtime_bridge import REFUSAL_MESSAGE, TICKET_RE, extract_identifiers, is_english_text, split_sentences

# Sections the service appends after the answer body (answer_postprocessor): sources and suggestions.
APPENDED_SECTION_RE = re.compile(r"\*\*(?:Nguồn|Gợi ý tra cứu thêm):\*\*.*?(?=【|\Z)", re.DOTALL)

ARTEFACT_PATTERNS = {
    "admonition": re.compile(r"\[!(?:IMPORTANT|NOTE|WARNING)\]"),
    "placeholder_image": re.compile(r"!\[[^\]]*\]\((?!https?://)[^)]*\)"),
    "breadcrumb": re.compile(r"\[Ngữ cảnh:"),
    "foreign_script": re.compile(r"[Ѐ-ӿ぀-ヿ一-鿿]"),
    "context_header": re.compile(r"\((?:Tài liệu|Nguồn)\s*:[^)]*Trang"),
    "broken_identifier": re.compile(r"\[\d{1,3}\]\.[A-Z0-9]"),
}
# Intents of a turn that did not answer from the documents.
REFUSAL_INTENTS = ("REFUSAL", "OUT_OF_SCOPE", "ESCALATION", "CLARIFICATION")


def is_refusal(turn: Dict[str, Any]) -> bool:
    answer = turn.get("answer") or ""
    return (
        bool(turn.get("is_refusal"))
        or str(turn.get("intent") or "") in REFUSAL_INTENTS
        or answer.startswith(REFUSAL_MESSAGE[:40])
    )


def is_declined(turn: Dict[str, Any]) -> bool:
    """Did not answer from the documents: refusal, clarification or hand-off to support (ticket)."""
    return is_refusal(turn) or bool(turn.get("escalated")) or bool(TICKET_RE.search(turn.get("answer") or ""))


def answer_body(text: str) -> str:
    """The answer without the appended sources / suggestions sections."""
    return APPENDED_SECTION_RE.sub("", text or "")


def transcript(sessions: Sequence[Sequence[Dict[str, Any]]]) -> str:
    """
    One text for a graded case, in the acceptance workbook's format (a single answer as is, otherwise
    【Lượt i】 / 【Phiên i】 Hỏi: … Trả lời: …), so human grades of earlier answers can be matched.
    """
    if len(sessions) == 1 and len(sessions[0]) == 1:
        return sessions[0][0].get("answer") or ""
    if len(sessions) > 1:
        parts = [(f"【Phiên {i}】", t) for i, s in enumerate(sessions, start=1) for t in s]
    else:
        parts = [(f"【Lượt {i}】", t) for i, t in enumerate(sessions[0], start=1)]
    return "\n\n".join(f"{tag} Hỏi: {t.get('query', '')}\nTrả lời:\n{t.get('answer') or ''}" for tag, t in parts)


TRANSCRIPT_TURN_RE = re.compile(r"【(?:Lượt|Phiên) \d+】 Hỏi: (.*?)\nTrả lời:\n(.*?)(?=\n\n【(?:Lượt|Phiên) \d+】 Hỏi: |\Z)",
                                re.DOTALL)


def parse_transcript(text: str) -> List[Dict[str, Any]]:
    """Inverse of transcript(): the turns of a workbook answer (one turn when it is a single answer)."""
    turns = [{"query": q, "answer": a} for q, a in TRANSCRIPT_TURN_RE.findall(text or "")]
    return turns or [{"query": "", "answer": text or ""}]


def stray_identifiers(answer: str, allowed: Iterable[str]) -> List[str]:
    allowed_up = {a.upper() for a in allowed}
    return [i for i in dict.fromkeys(extract_identifiers(answer_body(answer))) if i.upper() not in allowed_up]


def allowed_identifiers(case: Any, extra: Iterable[str] = ()) -> List[str]:
    """Codes a correct answer may cite: from the question(s), the gold answer and the required codes."""
    texts = [*case.conversation(), case.expected_answer, *extra]
    return list(dict.fromkeys([*case.required_identifiers, *(i for t in texts for i in extract_identifiers(t))]))


def artefacts(answer: str) -> List[str]:
    found = [name for name, rx in ARTEFACT_PATTERNS.items() if rx.search(answer or "")]
    if any(is_english_text(s) for s in split_sentences(answer or "")):
        found.append("english_sentence")
    return found


ID_POLICIES = ("all", "any")


def answer_checks(
    turn: Dict[str, Any],
    required_identifiers: Sequence[str],
    answerable: bool,
    id_policy: str = "all",
    allowed: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """
    id_policy "all": every required identifier must appear; "any": at least one of them (the answer
    cites its basis, completeness is left to the judge / human). `allowed`: codes a correct answer may
    cite (None: the stray-identifier check is skipped).
    """
    answer = (turn.get("answer") or "").upper()
    missing = [c for c in required_identifiers if c.upper() not in answer]
    if id_policy == "any" and len(missing) < len(required_identifiers):
        missing = []
    declined = is_declined(turn)
    return {
        "missing_identifiers": missing,
        "wrongly_refused": bool(declined and answerable and required_identifiers),
        "refused": is_refusal(turn),
        "declined": declined,
        "stray_identifiers": stray_identifiers(turn.get("answer") or "", allowed) if allowed is not None else [],
        "artefacts": artefacts(turn.get("answer") or ""),
        "error": turn.get("error"),
    }


def hard_failures(checks: Dict[str, Any], enabled: Sequence[str]) -> List[str]:
    reasons = []
    if checks.get("error"):
        reasons.append(f"error: {checks['error']}")
    if "missing_identifiers" in enabled and checks.get("missing_identifiers"):
        reasons.append("missing identifiers: " + ", ".join(checks["missing_identifiers"]))
    if "wrongly_refused" in enabled and checks.get("wrongly_refused"):
        reasons.append("refused although the documents answer it")
    if "artefacts" in enabled and checks.get("artefacts"):
        reasons.append("display artefacts: " + ", ".join(checks["artefacts"]))
    if "stray_identifiers" in enabled and checks.get("stray_identifiers"):
        reasons.append("codes outside the question / gold answer: " + ", ".join(checks["stray_identifiers"]))
    return reasons
