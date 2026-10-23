"""
CLI Runner for AIP Enterprise RAG Benchmark.
Usage:
    python -m rag_benchmark.cli run --dataset <path> --track <end_to_end|fixed_context>
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time

from .runner.orchestrator import load_dataset, run_benchmark_track
from .reporting.export_markdown import generate_markdown_report


def main():
    parser = argparse.ArgumentParser(description="AIP Enterprise RAG Benchmark CLI")
    subparsers = parser.add_subparsers(dest="command")

    # Command: run
    run_parser = subparsers.add_parser("run", help="Run benchmark on dataset")
    run_parser.add_argument("--dataset", required=True, help="Path to normalized JSONL dataset")
    run_parser.add_argument("--track", choices=["end_to_end", "fixed_context"], default="end_to_end")
    run_parser.add_argument("--system-id", default="local_aip_rag_v1")
    run_parser.add_argument("--output-dir", default="runs")

    # Command: validate
    val_parser = subparsers.add_parser("validate", help="Validate dataset JSONL schema")
    val_parser.add_argument("--dataset", required=True, help="Path to JSONL dataset")

    args = parser.parse_args()

    if args.command == "validate":
        cases = load_dataset(args.dataset)
        print(f"SUCCESS: Validated {len(cases)} approved cases in {args.dataset}")

    elif args.command == "run":
        cases = load_dataset(args.dataset)
        run_id = f"run_{time.strftime('%Y%m%d_%H%M%S')}"
        results = asyncio.run(
            run_benchmark_track(
                cases=cases,
                track=args.track,
                system_id=args.system_id,
                run_id=run_id,
                output_dir=args.output_dir,
                dataset_path=args.dataset,
            )
        )
        report_md = generate_markdown_report(results, run_id=run_id, track=args.track)
        report_file = os.path.join(args.output_dir, run_id, "benchmark_report.md")
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report_md)
        print(f"\nSUCCESS: Report exported to {report_file}")
        print("\n" + report_md)


if __name__ == "__main__":
    main()
