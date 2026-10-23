"""
Benchmark Orchestrator: Coordinates dataset loading, adapter execution,
standardized evaluation scoring, and audit provenance logging.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import subprocess
import time
from typing import Any, Dict, List, Optional

from ..adapters.base import RAGAdapter
from ..adapters.fixed_context import FixedContextAdapter
from ..adapters.local_rag import LocalRAGAdapter
from ..evaluators.citation import evaluate_citations
from ..evaluators.generation import evaluate_generation
from ..evaluators.llm_judge import evaluate_with_llm_judge
from ..evaluators.retrieval import evaluate_retrieval
from ..schemas.dataset import GoldenCase
from ..schemas.result import (
    EvaluationScores,
    GenerationExecution,
    RetrievalExecution,
    RetrievedChunkResult,
    RunResult,
)

logger = logging.getLogger("rag-benchmark.orchestrator")


def compute_file_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def get_git_commit() -> Optional[str]:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return "untracked"


def load_dataset(file_path: str) -> List[GoldenCase]:
    cases: List[GoldenCase] = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            case = GoldenCase.model_validate(data)
            if case.is_approved():
                cases.append(case)
    return cases


async def run_benchmark_track(
    cases: List[GoldenCase],
    track: str = "end_to_end",
    system_id: str = "local_rag_qwen1.5b",
    run_id: Optional[str] = None,
    output_dir: str = "runs",
    dataset_path: Optional[str] = None,
) -> List[RunResult]:
    run_id = run_id or f"run_{int(time.time())}"
    target_dir = os.path.join(output_dir, run_id)
    os.makedirs(target_dir, exist_ok=True)

    dataset_sha256 = compute_file_sha256(dataset_path) if dataset_path and os.path.exists(dataset_path) else None
    git_commit = get_git_commit()

    adapter: RAGAdapter
    if track == "fixed_context":
        adapter = FixedContextAdapter()
    else:
        adapter = LocalRAGAdapter()

    results: List[RunResult] = []

    print(f"\n--- [BENCHMARK RUN] ID: {run_id} | Track: {track} | Cases: {len(cases)} ---")
    if dataset_sha256:
        print(f"Dataset SHA-256: {dataset_sha256[:16]}... | Git Commit: {git_commit}")

    for idx, case in enumerate(cases, start=1):
        print(f"[{idx}/{len(cases)}] Case {case.case_id}: {case.question[:50]}...")
        retrieval_exec = None
        gen_exec = None
        scores = EvaluationScores()
        status = "success"
        error_msg = None

        try:
            if track == "fixed_context":
                context_payload = [c.model_dump() for c in case.reference_context]
                resp = await adapter.answer(case.question, context=context_payload)
            else:
                resp = await adapter.answer(case.question)

            # Map retrieved chunks
            retrieved_chunk_results = [
                RetrievedChunkResult(**c) for c in resp.retrieved_chunks
            ]
            retrieval_exec = RetrievalExecution(
                retrieved_chunks=retrieved_chunk_results,
                latency_ms=resp.latency_ms if track != "fixed_context" else 0.0,
            )

            gen_exec = GenerationExecution(
                answer=resp.answer,
                latency_ms=resp.latency_ms,
                input_tokens=resp.input_tokens,
                output_tokens=resp.output_tokens,
                citations=resp.citations,
            )

            # Evaluate Retrieval (Track B only)
            if track == "end_to_end":
                evidence_payload = [e.model_dump() for e in case.evidence]
                ret_metrics = evaluate_retrieval(
                    case_id=case.case_id,
                    retrieved_chunks=resp.retrieved_chunks,
                    evidence=evidence_payload,
                    answerable=case.answerable,
                )
                for k, v in ret_metrics.items():
                    setattr(scores, k, v)

                # Citation metrics
                cit_metrics = evaluate_citations(
                    citations=resp.citations,
                    evidence=evidence_payload,
                    answerable=case.answerable,
                )
                for k, v in cit_metrics.items():
                    setattr(scores, k, v)

            # Evaluate Generation (Track A and Track B)
            gen_metrics = evaluate_generation(
                generated_answer=resp.answer,
                expected_answer=case.expected_answer,
                required_facts=case.required_facts,
                answerable=case.answerable,
            )
            for k, v in gen_metrics.items():
                setattr(scores, k, v)

            # Assemble context for LLM Judge
            context_pieces = []
            if track == "fixed_context":
                for rc in case.reference_context:
                    txt = getattr(rc, "text", None) or getattr(rc, "quote", None) or ""
                    if txt:
                        context_pieces.append(txt)
            else:
                for chunk in resp.retrieved_chunks:
                    txt = chunk.get("excerpt") or chunk.get("text") or ""
                    if txt:
                        context_pieces.append(txt)
            context_text = "\n\n".join(context_pieces)

            # Evaluate with independent LLM Judge (Qwen2.5-7B)
            judge_metrics = await evaluate_with_llm_judge(
                question=case.question,
                retrieved_context=context_text,
                generated_answer=resp.answer,
                expected_answer=case.expected_answer,
                answerable=case.answerable,
            )
            for k, v in judge_metrics.items():
                if v is not None:
                    setattr(scores, k, v)

        except Exception as exc:
            status = "error"
            error_msg = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            logger.error("Error executing case %s: %s", case.case_id, error_msg)

        run_res = RunResult(
            run_id=run_id,
            case_id=case.case_id,
            system_id=system_id,
            track=track,
            is_answerable=case.answerable,
            git_commit=git_commit,
            dataset_sha256=dataset_sha256,
            evaluator_version="2.0.0-ranx-audited",
            retrieval=retrieval_exec,
            generation=gen_exec,
            evaluation=scores,
            status=status,
            error=error_msg,
        )
        results.append(run_res)

    # Save raw results JSONL
    out_file = os.path.join(target_dir, f"results_{track}.jsonl")
    with open(out_file, "w", encoding="utf-8") as f:
        for r in results:
            f.write(r.model_dump_json() + "\n")

    print(f"Saved raw results to: {out_file}")
    return results
