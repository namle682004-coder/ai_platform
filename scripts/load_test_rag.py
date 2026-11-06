"""
Load test of the RAG chat API: checks that overload is refused (429 rate limit, 503 busy with
Retry-After) instead of piling up on the model host.

    python scripts/load_test_rag.py --api http://localhost:8010 --tenant <project_id> \
        --users 12 --requests 60 [--header "X-AIP-Runtime-Token: …"]

Prints the status codes, latencies and Retry-After values, and the service's /health "load"
section (in-flight turns, runtime breakers) during and after the burst. Exit code 1 when a
protection did not hold: a request hung past --max-latency, or an error other than 429/503 occurred.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from collections import Counter
from typing import Any, Dict, List, Optional

import httpx

QUESTIONS = [
    "Lớp 10 học những chủ đề nào?",
    "RAG học ở lớp mấy?",
    "Có mấy nguyên tắc đạo đức trong thiết kế AI?",
    "Teachable Machine có trong khung nội dung không?",
]


async def health(client: httpx.AsyncClient, api: str) -> Optional[Dict[str, Any]]:
    try:
        res = await client.get(f"{api}/health", timeout=5)
        return res.json().get("load") if res.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--api", default="http://localhost:8010")
    p.add_argument("--tenant", required=True)
    p.add_argument("--tenants", type=int, default=1, help="spread requests over N tenants (per-client limits)")
    p.add_argument("--users", type=int, default=10, help="concurrent clients")
    p.add_argument("--requests", type=int, default=40, help="total requests")
    p.add_argument("--header", action="append", default=[])
    p.add_argument("--max-latency", type=float, default=90.0, help="a request slower than this is a failure")
    args = p.parse_args()

    headers = {"X-User-Role": "user"}
    for h in args.header:
        k, _, v = h.partition(":")
        headers[k.strip()] = v.strip()
    sem = asyncio.Semaphore(args.users)
    results: List[Dict[str, Any]] = []
    peak: Dict[str, Any] = {}

    async with httpx.AsyncClient(timeout=args.max_latency + 30) as client:
        before = await health(client, args.api)

        async def one(i: int) -> None:
            tenant = args.tenant if args.tenants <= 1 else f"{args.tenant}-{i % args.tenants}"
            body = {"query": QUESTIONS[i % len(QUESTIONS)], "conversation_id": f"load_{i}", "stream": False}
            async with sem:
                t0 = time.perf_counter()
                try:
                    res = await client.post(f"{args.api}/v1/rag/chat", json=body,
                                            headers={**headers, "X-Tenant-ID": tenant})
                    code, retry = res.status_code, res.headers.get("Retry-After")
                    detail = ""
                    if code != 200:
                        try:
                            d = res.json().get("detail")
                            detail = (d.get("message") if isinstance(d, dict) else str(d)) or ""
                        except ValueError:
                            detail = res.text[:120]
                except httpx.HTTPError as exc:
                    code, retry, detail = 0, None, type(exc).__name__
                results.append({"i": i, "code": code, "s": time.perf_counter() - t0, "retry": retry,
                                "detail": detail[:100]})

        async def sampler() -> None:
            while True:
                load = await health(client, args.api)
                if load and load.get("chat_in_flight", 0) >= peak.get("chat_in_flight", -1):
                    peak.update(load)
                await asyncio.sleep(0.5)

        sampling = asyncio.create_task(sampler())
        t_start = time.perf_counter()
        await asyncio.gather(*[one(i) for i in range(args.requests)])
        elapsed = time.perf_counter() - t_start
        sampling.cancel()
        after = await health(client, args.api)

    codes = Counter(r["code"] for r in results)
    lat = sorted(r["s"] for r in results)
    print(f"{len(results)} requests, {args.users} concurrent, {elapsed:.1f}s")
    print("status codes:", dict(sorted(codes.items())))
    print(f"latency s: p50 {statistics.median(lat):.2f}  p95 {lat[int(0.95 * (len(lat) - 1))]:.2f}  max {lat[-1]:.2f}")
    for code in sorted(c for c in codes if c != 200):
        sample = next(r for r in results if r["code"] == code)
        print(f"  {code}: Retry-After={sample['retry']}  «{sample['detail']}»")
    print("load before:", json.dumps(before, ensure_ascii=False))
    print("load at peak:", json.dumps({k: peak.get(k) for k in ("chat_in_flight", "chat_max_inflight",
                                                                "chat_rejected", "degraded")}, ensure_ascii=False))
    print("load after:", json.dumps(after, ensure_ascii=False))

    hung = [r for r in results if r["s"] > args.max_latency]
    other = [r for r in results if r["code"] not in (200, 429, 503)]
    problems = []
    if hung:
        problems.append(f"{len(hung)} request(s) took longer than {args.max_latency:.0f}s")
    if other:
        problems.append(f"{len(other)} unexpected status(es): {Counter(r['code'] for r in other)}")
    if peak.get("chat_in_flight", 0) > (peak.get("chat_max_inflight") or 10 ** 9):
        problems.append("more turns in flight than the admission limit")
    print("RESULT:", "PROTECTED" if not problems else "NOT PROTECTED – " + "; ".join(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
