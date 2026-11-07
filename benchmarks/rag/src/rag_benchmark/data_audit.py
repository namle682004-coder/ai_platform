"""
Data-quality gate (step 1) for the RAG ingestion layer.

Runs AIP's own parser + chunker over a folder of source documents and compares the chunks with an
independent extraction of the same files (python-docx / openpyxl / PyMuPDF). No LLM, no retrieval: what is
lost or mislabelled here cannot be recovered by any later stage.

    DQ1 content coverage   word recall of the source text in the chunks, per document
    DQ2 table labelling    every table row in a chunk has a real column name for each non-empty cell
    DQ3 scanned pages      pages without a text layer carry OCR text
    DQ4 OCR accuracy       reference lines read from the page images appear in the chunks
    DQ5 gold evidence      benchmark facts sit in ONE chunk together with their label

Usage (from benchmarks/rag/src, PYTHONPATH=../../..:../../../packages/common):
    python -m rag_benchmark.data_audit --docs <folder> [--checks <x.index_checks.json>] \
        [--gate ../configs/data_gate.yaml] [--out report.json]
Exit code 1 when a gate threshold is not met.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import yaml

SUPPORTED = (".docx", ".xlsx", ".pdf")
WORD_RE = re.compile(r"\w+", re.UNICODE)
PLACEHOLDER_COL = re.compile(r"^col\d+$", re.I)
MIN_OCR_CHARS = 200
SCAN_MAX_TEXT = 500  # signed scans carry a small text overlay (signature stamp)


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def words(text: str) -> Counter:
    return Counter(WORD_RE.findall(nfc(text).lower()))


def flat(text: str) -> str:
    """Comparison form: lower-case, markdown pipes / <br> / emphasis removed, whitespace collapsed."""
    s = nfc(text).lower().replace("<br>", " ").replace("**", "").replace("\\|", " ")
    return re.sub(r"[\s|]+", " ", s).strip()


# ---------------------------------------------------------------- independent reference extraction
def reference_text(path: str) -> Tuple[str, List[int]]:
    """(source text, 1-based numbers of scanned pages) read without AIP's parsers."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        import docx
        d = docx.Document(path)
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            seen = set()
            for row in t.rows:
                for c in row.cells:
                    if id(c._tc) not in seen:
                        seen.add(id(c._tc))
                        parts.append(c.text)
        return "\n".join(parts), []
    if ext == ".xlsx":
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
        return "\n".join(str(v) for ws in wb.worksheets for row in ws.iter_rows(values_only=True)
                         for v in row if v not in (None, "")), []
    import pymupdf
    doc = pymupdf.open(path)
    texts, scanned = [], []
    for i, page in enumerate(doc, start=1):
        t = page.get_text()
        if len(t.strip()) < SCAN_MAX_TEXT and page.get_images():
            scanned.append(i)
        else:
            texts.append(t)
    return "\n".join(texts), scanned


# ---------------------------------------------------------------- AIP pipeline
def aip_parse_and_chunk(path: str):
    from solutions.rag.application.components.chunker import DocumentChunker
    from solutions.rag.config import rag_settings as s
    from solutions.rag.infrastructure.parsers.factory import parser_factory

    chunker = DocumentChunker(
        child_chunk_size_chars=s.child_chunk_size_chars, child_overlap_chars=s.child_overlap_chars,
        parent_chunk_size_chars=s.parent_chunk_size_chars, mask_pii=False, hierarchical=True,
    )
    with open(path, "rb") as f:
        parsed = parser_factory.parse(f.read(), os.path.basename(path))
    chunks = chunker.chunk_document(parsed, "doc_audit", title=os.path.basename(path))
    return parsed, [c.text for c in chunks]


# ---------------------------------------------------------------- DQ2: table rows and their headers
def split_row(line: str) -> List[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", body)]


def table_row_issues(chunk: str) -> Tuple[int, List[str]]:
    """(table rows checked, problems) for the markdown tables of one chunk."""
    lines = chunk.split("\n")
    rows, issues, i = 0, [], 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{3,}", lines[i + 1]):
            header = split_row(lines[i])
            names = [h for h in header if h and not PLACEHOLDER_COL.match(h)]
            caption_header = len(header) > 1 and len(set(names)) < 2
            j = i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                cells = split_row(lines[j])
                rows += 1
                unlabelled = [k for k, v in enumerate(cells) if v and (
                    k >= len(header) or not header[k] or PLACEHOLDER_COL.match(header[k]))]
                if caption_header:
                    issues.append(f"caption used as header: {header[0][:60]!r}")
                elif unlabelled:
                    issues.append(f"cells without column name {unlabelled} under header {[h[:20] for h in header]}")
                j += 1
            i = j
        elif lines[i].lstrip().startswith("|"):
            # A table row with no header above it in this chunk: its cells have no column names at all.
            rows += 1
            issues.append(f"table row without header in chunk: {lines[i][:60]!r}")
            i += 1
        else:
            i += 1
    return rows, issues


# ---------------------------------------------------------------- report
@dataclass
class DocReport:
    file: str
    chunks: int = 0
    coverage: Optional[float] = None
    table_rows: int = 0
    table_rows_ok: int = 0
    scanned_pages: List[int] = field(default_factory=list)
    scanned_pages_ocr: int = 0
    issues: List[str] = field(default_factory=list)
    error: str = ""

    @property
    def table_rate(self) -> Optional[float]:
        return self.table_rows_ok / self.table_rows if self.table_rows else None


def audit_document(path: str, root: str) -> Tuple[DocReport, List[str], str]:
    rep = DocReport(file=nfc(os.path.relpath(path, root)))
    try:
        ref_text, scanned = reference_text(path)
        parsed, chunks = aip_parse_and_chunk(path)
    except Exception as exc:  # noqa: BLE001 - a document that cannot be processed is itself a finding
        rep.error = f"{type(exc).__name__}: {exc}"[:300]
        return rep, [], ""
    rep.chunks = len(chunks)
    ref = words(ref_text)
    got = words("\n".join(chunks))
    if sum(ref.values()):
        rep.coverage = sum(min(n, got[w]) for w, n in ref.items()) / sum(ref.values())
        missing = [w for w, n in ref.most_common() if got[w] < n][:12]
        if rep.coverage < 0.99:
            rep.issues.append(f"words missing from chunks (most frequent): {missing}")
    for c in chunks:
        n, problems = table_row_issues(c)
        rep.table_rows += n
        rep.table_rows_ok += n - len(problems)
        rep.issues += problems[:3]
    rep.scanned_pages = scanned
    page_text = {p.page_number: re.sub(r"!\[[^\]]*\]\([^)]*\)", "", p.text or "") for p in parsed.pages}
    rep.scanned_pages_ocr = sum(1 for n in scanned if len(page_text.get(n, "").strip()) >= MIN_OCR_CHARS)
    return rep, chunks, "\n".join(page_text.values())


def run_checks(checks: List[Dict[str, Any]], doc_chunks: Dict[str, List[str]],
               doc_texts: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Gold-evidence checks look for ONE chunk holding every term. OCR checks measure recognition only, so they
    look in the parsed text of the document (a line cut by a chunk boundary is a DQ5 matter, not OCR).
    """
    out = []
    for chk in checks:
        key = flat(chk["doc"])
        if chk.get("kind") == "ocr":
            chunks = [flat(t) for f, t in doc_texts.items() if key in flat(f)]
        else:
            chunks = [flat(c) for f, cs in doc_chunks.items() if key in flat(f) for c in cs]
        terms = [flat(t) for t in chk["terms"]]
        together = any(all(t in c for t in terms) for c in chunks)
        anywhere = all(any(t in c for c in chunks) for t in terms)
        out.append({**chk, "docs_matched": bool(chunks),
                    "status": "PASS" if together else ("SPLIT" if anywhere else "MISSING")})
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="RAG data-quality gate (step 1)")
    ap.add_argument("--docs", required=True)
    ap.add_argument("--checks")
    ap.add_argument("--gate", default=os.path.join(os.path.dirname(__file__), "../../configs/data_gate.yaml"))
    ap.add_argument("--out")
    args = ap.parse_args(argv)

    gate = yaml.safe_load(open(args.gate, encoding="utf-8"))
    files = sorted(f for f in glob.glob(os.path.join(args.docs, "**", "*"), recursive=True)
                   if f.lower().endswith(SUPPORTED) and not os.path.basename(f).startswith("~$"))
    reports, doc_chunks, doc_texts = [], {}, {}
    for f in files:
        rep, chunks, text = audit_document(f, args.docs)
        reports.append(rep)
        doc_chunks[rep.file], doc_texts[rep.file] = chunks, text

    checks = run_checks(json.load(open(args.checks, encoding="utf-8")), doc_chunks, doc_texts) if args.checks else []

    print(f"{'cover':>6} {'tables':>12} {'scan':>6} {'chunks':>6}  file")
    for r in reports:
        cov = f"{r.coverage:6.1%}" if r.coverage is not None else "   n/a"
        tab = f"{r.table_rows_ok:4}/{r.table_rows:<4}" if r.table_rows else "     -    "
        scan = f"{r.scanned_pages_ocr}/{len(r.scanned_pages)}" if r.scanned_pages else "-"
        print(f"{cov} {tab:>12} {scan:>6} {r.chunks:6}  {r.file}{'  ERROR ' + r.error if r.error else ''}")
    for c in checks:
        if c["status"] != "PASS":
            print(f"  {c['status']:7} {c['case']}: {c['terms']}")

    with_text = [r for r in reports if r.coverage is not None]
    rows = sum(r.table_rows for r in reports)
    rows_ok = sum(r.table_rows_ok for r in reports)
    scanned = sum(len(r.scanned_pages) for r in reports)
    scanned_ok = sum(r.scanned_pages_ocr for r in reports)
    ocr = [c for c in checks if c.get("kind") == "ocr"]
    gold = [c for c in checks if c.get("kind") != "ocr"]
    metrics = {
        "DQ1_min_coverage": min((r.coverage for r in with_text), default=1.0),
        "DQ1_docs_below": [r.file for r in with_text if r.coverage < gate["dq1_min_coverage"]],
        "DQ2_table_rows_ok": rows_ok / rows if rows else 1.0,
        "DQ2_tables_failing_docs": [r.file for r in reports if r.table_rows and r.table_rows_ok < r.table_rows],
        "DQ3_scanned_ocr": scanned_ok / scanned if scanned else 1.0,
        "DQ4_ocr_accuracy": sum(c["status"] == "PASS" for c in ocr) / len(ocr) if ocr else None,
        "DQ5_gold_in_one_chunk": sum(c["status"] == "PASS" for c in gold) / len(gold) if gold else None,
        "errors": [r.file for r in reports if r.error],
    }
    verdict = {
        "DQ1": not metrics["DQ1_docs_below"],
        "DQ2": metrics["DQ2_table_rows_ok"] >= gate["dq2_min_table_rows_ok"],
        "DQ3": metrics["DQ3_scanned_ocr"] >= gate["dq3_min_scanned_ocr"],
        "DQ4": metrics["DQ4_ocr_accuracy"] is None or metrics["DQ4_ocr_accuracy"] >= gate["dq4_min_ocr_accuracy"],
        "DQ5": metrics["DQ5_gold_in_one_chunk"] is None or metrics["DQ5_gold_in_one_chunk"] >= gate["dq5_min_gold"],
        "errors": not metrics["errors"],
    }
    print("\n== DATA GATE")
    for k, v in metrics.items():
        if isinstance(v, float):
            print(f"  {k:26} {v:.1%}")
        elif v:
            print(f"  {k:26} {v}")
    passed = all(verdict.values())
    print("  verdict:", "PASS" if passed else "FAIL " + str([k for k, v in verdict.items() if not v]))
    if args.out:
        json.dump({"metrics": metrics, "verdict": verdict, "documents": [asdict(r) for r in reports], "checks": checks},
                  open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
