"""
Run a chatbot acceptance test set (xlsx) against the RAG API and auto-check what a machine can check.

Input sheet columns (names configurable): question, test type, expected identifiers ("căn cứ").
Multi-turn questions are written as "Lượt 1: … / Lượt 2: …" and run in one session; "3 phiên riêng"
questions list variants as "(1) … (2) …" and each runs in a fresh session.

Automatic checks per answer (manual grading still decides semantic correctness):
  - refusal / escalation flag and ticket id,
  - required identifiers from the expected column present in the answer,
  - formatting artefacts that must never reach users,
  - latency (total and time-to-first-token for streaming).

Usage:
  python scripts/eval_rag_testset.py tests.xlsx --api http://localhost:8010 --tenant <tenant> \
      --out results.xlsx [--sheet "Bộ câu hỏi"] [--stream] [--threshold 0.65] [--header "X-AIP-Runtime-Token: …"]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

import httpx
import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from solutions.rag.application.components.answer_verifier import is_english_text, split_sentences  # noqa: E402
from solutions.rag.application.components.lexical_evidence import extract_identifiers  # noqa: E402
from solutions.rag.application.components.prompt_builder import REFUSAL_MESSAGE  # noqa: E402

ARTEFACT_PATTERNS = {
    "admonition": re.compile(r"\[!(?:IMPORTANT|NOTE|WARNING)\]"),
    "placeholder_image": re.compile(r"!\[[^\]]*\]\((?!https?://)[^)]*\)"),
    "breadcrumb": re.compile(r"\[Ngữ cảnh:"),
    "foreign_script": re.compile(r"[Ѐ-ӿ぀-ヿ一-鿿]"),
    "context_header": re.compile(r"\((?:Tài liệu|Nguồn)\s*:[^)]*Trang"),
    "broken_identifier": re.compile(r"\[\d{1,3}\]\.[A-Z0-9]"),
}


def has_english_sentence(answer: str) -> bool:
    return any(is_english_text(s) for s in split_sentences(answer or ""))
TURN_RE = re.compile(r"Lượt\s*\d+\s*:\s*(.+)")
VARIANT_RE = re.compile(r"\(\d+\)\s*(.+)")


def split_turns(question: str, kind: str) -> Tuple[str, List[str]]:
    lines = [ln.strip() for ln in (question or "").splitlines() if ln.strip()]
    turns = [m.group(1).strip() for ln in lines for m in [TURN_RE.match(ln)] if m]
    if turns:
        return "multi_turn", turns
    variants = [m.group(1).strip() for ln in lines for m in [VARIANT_RE.match(ln)] if m]
    if variants:
        return "separate_sessions", variants
    if "phiên" in (kind or "").lower():
        body = question.split(":", 1)[-1].strip()
        return "separate_sessions", [body] * 3
    return "single", [question.strip()]


def call_chat(client: httpx.Client, api: str, query: str, session_id: str, args: argparse.Namespace) -> Dict[str, Any]:
    body = {
        "query": query,
        "conversation_id": session_id,
        "model": args.model,
        "top_k": args.top_k,
        "similarity_threshold": args.threshold,
        "temperature": args.temperature,
    }
    if getattr(args, "analyzer_model", None):
        body["analyzer_model"] = args.analyzer_model
    t0 = time.time()
    if not args.stream:
        res = client.post(f"{api}/v1/rag/chat", json=body)
        res.raise_for_status()
        data = res.json()
        data["_total_s"] = time.time() - t0
        data["_ttft_s"] = None
        return data
    answer, ttft, done = [], None, {}
    with client.stream("POST", f"{api}/v1/rag/chat/stream", json=body) as res:
        res.raise_for_status()
        for line in res.iter_lines():
            if not line.startswith("data: "):
                continue
            payload = json.loads(line[6:])
            if "token" in payload:
                if ttft is None:
                    ttft = time.time() - t0
                answer.append(payload["token"])
            if payload.get("done"):
                done = payload
    done["answer"] = "".join(answer)
    done["_total_s"] = time.time() - t0
    done["_ttft_s"] = ttft
    return done


def auto_checks(answer: str, expected_ref: str, response: Dict[str, Any]) -> Dict[str, Any]:
    required = extract_identifiers(expected_ref or "")
    missing = [code for code in required if code not in (answer or "").upper()]
    artefacts = [name for name, rx in ARTEFACT_PATTERNS.items() if rx.search(answer or "")]
    if has_english_sentence(answer):
        artefacts.append("english_sentence")
    refused = bool(response.get("is_refusal")) or (answer or "").startswith(REFUSAL_MESSAGE[:40])
    return {
        "refused": refused,
        "intent": response.get("intent"),
        "missing_codes": ", ".join(missing),
        "artefacts": ", ".join(artefacts),
        "ticket": (response.get("escalation") or {}).get("escalation_data", {}).get("ticket_id", ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("xlsx")
    parser.add_argument("--out", required=True)
    parser.add_argument("--api", default="http://localhost:8010")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--sheet", default="Bộ câu hỏi")
    parser.add_argument("--col-id", default="Mã câu")
    parser.add_argument("--col-question", default="Câu hỏi nhập vào bot")
    parser.add_argument("--col-type", default="Loại")
    parser.add_argument("--col-ref", default="Căn cứ (mã YCCĐ)")
    parser.add_argument("--model", default="chat-general-standard")
    parser.add_argument("--analyzer-model", default=None, help="Optional model alias for intent analysis and query rewriting")
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--threshold", type=float, default=0.65)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--header", action="append", default=[], help="Extra header 'Name: value' (repeatable)")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    wb = openpyxl.load_workbook(args.xlsx, data_only=True)
    ws = wb[args.sheet]
    header = [str(c.value or "").strip() for c in ws[1]]
    col = {name: header.index(name) for name in (args.col_id, args.col_question, args.col_type, args.col_ref)}

    headers = {"X-Tenant-ID": args.tenant}
    for h in args.header:
        name, _, value = h.partition(":")
        headers[name.strip()] = value.strip()

    out_wb = openpyxl.Workbook()
    out = out_wb.active
    out.title = "Kết quả"
    out.append(["Mã câu", "Lượt", "Câu hỏi", "Câu trả lời", "Intent", "Từ chối", "Ticket", "Thiếu mã bắt buộc",
                "Lỗi hiển thị", "Tổng (s)", "Chữ đầu (s)", "Session"])

    rows = list(ws.iter_rows(min_row=2, values_only=True))
    if args.limit:
        rows = rows[: args.limit]
    with httpx.Client(headers=headers, timeout=180.0) as client:
        for row in rows:
            qid = row[col[args.col_id]]
            if not qid:
                continue
            mode, turns = split_turns(str(row[col[args.col_question]] or ""), str(row[col[args.col_type]] or ""))
            expected = str(row[col[args.col_ref]] or "")
            session = f"eval_{uuid.uuid4().hex[:10]}"
            for i, turn in enumerate(turns, start=1):
                if mode == "separate_sessions":
                    session = f"eval_{uuid.uuid4().hex[:10]}"
                try:
                    resp = call_chat(client, args.api, turn, session, args)
                except httpx.HTTPError as exc:
                    out.append([qid, i, turn, f"HTTP ERROR: {exc}"])
                    continue
                answer = resp.get("answer", "")
                is_last = i == len(turns) or mode == "separate_sessions"
                checks = auto_checks(answer, expected if is_last else "", resp)
                out.append([
                    qid, i, turn, answer, checks["intent"], "x" if checks["refused"] else "", checks["ticket"],
                    checks["missing_codes"], checks["artefacts"], round(resp["_total_s"], 2),
                    round(resp["_ttft_s"], 2) if resp.get("_ttft_s") is not None else "", session,
                ])
                print(f"{qid} [{i}/{len(turns)}] {resp['_total_s']:.1f}s refused={checks['refused']} missing={checks['missing_codes'] or '-'}")
    out_wb.save(args.out)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
