"""
Load test / load gate of the RAG chat API.

Checks that overload is refused (429 rate limit, 503 busy with Retry-After) instead of piling up on the model
host, and – with thresholds – that the service still answers enough requests fast enough and that no
container ran out of memory or restarted during the run.

    python scripts/load_test_rag.py --api http://localhost:8010 --tenant <project_id> \
        --users 12 --requests 60 [--stream] [--header "X-AIP-Runtime-Token: …"] \
        [--min-success 0.5] [--max-p95 60] [--max-ttft-p95 15] \
        [--containers aip-rag-api aip-rag-worker] [--out report.json]

Exit code 1 when a protection or a threshold did not hold:
  - a request hung past --max-latency, or a status other than 200/429/503 occurred;
  - more turns in flight than the admission limit;
  - success rate (200) below --min-success, p95 latency of answered requests above --max-p95,
    p95 time to first token above --max-ttft-p95 (streaming);
  - a watched container was OOM-killed or restarted, or its memory went above --max-mem-pct of its cap.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import subprocess
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
    "Viên chức đạt bao nhiêu điểm thì hoàn thành tốt nhiệm vụ?",
    "Liệt kê các tin tiêu cực",
]


async def health(client: httpx.AsyncClient, api: str) -> Optional[Dict[str, Any]]:
    try:
        res = await client.get(f"{api}/health", timeout=5)
        return res.json().get("load") if res.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


# ------------------------------------------------------------------ containers (docker on this host)
def _docker(*args: str) -> str:
    try:
        return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=15).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def container_state(name: str) -> Dict[str, Any]:
    raw = _docker("inspect", "-f", "{{.RestartCount}} {{.State.OOMKilled}} {{.State.Running}} {{.HostConfig.Memory}}", name)
    if not raw:
        return {}
    restarts, oom, running, cap = raw.split()
    return {"restarts": int(restarts), "oom_killed": oom == "true", "running": running == "true", "cap_bytes": int(cap)}


def _bytes(text: str) -> float:
    units = {"B": 1, "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3, "kB": 1e3, "MB": 1e6, "GB": 1e9}
    for u in sorted(units, key=len, reverse=True):
        if text.endswith(u):
            return float(text[: -len(u)]) * units[u]
    return 0.0


def container_memory(names: List[str]) -> Dict[str, float]:
    out = _docker("stats", "--no-stream", "--format", "{{.Name}} {{.MemUsage}}", *names)
    mem = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            mem[parts[0]] = _bytes(parts[1])
    return mem


# ------------------------------------------------------------------ requests
async def call(client: httpx.AsyncClient, args: argparse.Namespace, headers: Dict[str, str], i: int) -> Dict[str, Any]:
    tenant = args.tenant if args.tenants <= 1 else f"{args.tenant}-{i % args.tenants}"
    body = {"query": QUESTIONS[i % len(QUESTIONS)], "conversation_id": f"load_{i}", "stream": args.stream}
    h = {**headers, "X-Tenant-ID": tenant}
    t0 = time.perf_counter()
    ttft: Optional[float] = None
    try:
        if args.stream:
            async with client.stream("POST", f"{args.api}/v1/rag/chat/stream", json=body, headers=h) as res:
                code, retry, detail = res.status_code, res.headers.get("Retry-After"), ""
                async for chunk in res.aiter_text():
                    if ttft is None and chunk.strip():
                        ttft = time.perf_counter() - t0
                    if code != 200:
                        detail += chunk
        else:
            res = await client.post(f"{args.api}/v1/rag/chat", json=body, headers=h)
            code, retry, detail = res.status_code, res.headers.get("Retry-After"), ""
            if code != 200:
                try:
                    d = res.json().get("detail")
                    detail = (d.get("message") if isinstance(d, dict) else str(d)) or ""
                except ValueError:
                    detail = res.text[:120]
    except httpx.HTTPError as exc:
        code, retry, detail = 0, None, type(exc).__name__
    return {"i": i, "code": code, "s": time.perf_counter() - t0, "ttft": ttft, "retry": retry, "detail": detail[:100]}


def pct(values: List[float], q: float) -> Optional[float]:
    v = sorted(values)
    return v[int(q * (len(v) - 1))] if v else None


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--api", default="http://localhost:8010")
    p.add_argument("--tenant", required=True)
    p.add_argument("--tenants", type=int, default=1, help="spread requests over N tenants (per-client limits)")
    p.add_argument("--users", type=int, default=10, help="concurrent clients")
    p.add_argument("--requests", type=int, default=40, help="total requests")
    p.add_argument("--stream", action="store_true", help="use the streaming endpoint and measure time to first token")
    p.add_argument("--header", action="append", default=[])
    p.add_argument("--max-latency", type=float, default=90.0, help="a request slower than this is a failure")
    p.add_argument("--min-success", type=float, default=0.0, help="minimum share of HTTP 200")
    p.add_argument("--max-p95", type=float, default=0.0, help="max p95 latency (s) of answered requests (0 = off)")
    p.add_argument("--max-ttft-p95", type=float, default=0.0, help="max p95 time to first token (s, --stream)")
    p.add_argument("--containers", nargs="*", default=[], help="containers watched for OOM / restarts / memory")
    p.add_argument("--max-mem-pct", type=float, default=95.0, help="max memory of a watched container, %% of its cap")
    p.add_argument("--out", help="write the report as JSON")
    args = p.parse_args()

    headers = {"X-User-Role": "user"}
    for h in args.header:
        k, _, v = h.partition(":")
        headers[k.strip()] = v.strip()
    sem = asyncio.Semaphore(args.users)
    results: List[Dict[str, Any]] = []
    peak: Dict[str, Any] = {}
    mem_peak: Dict[str, float] = {}
    state_before = {c: container_state(c) for c in args.containers}

    async with httpx.AsyncClient(timeout=args.max_latency + 30) as client:
        before = await health(client, args.api)

        async def one(i: int) -> None:
            async with sem:
                results.append(await call(client, args, headers, i))

        async def sampler() -> None:
            while True:
                load = await health(client, args.api)
                if load and load.get("chat_in_flight", 0) >= peak.get("chat_in_flight", -1):
                    peak.update(load)
                if args.containers:
                    for name, used in (await asyncio.to_thread(container_memory, args.containers)).items():
                        mem_peak[name] = max(mem_peak.get(name, 0.0), used)
                await asyncio.sleep(1.0)

        sampling = asyncio.create_task(sampler())
        t_start = time.perf_counter()
        await asyncio.gather(*[one(i) for i in range(args.requests)])
        elapsed = time.perf_counter() - t_start
        sampling.cancel()
        if args.containers:  # a burst shorter than the sampling period still gets one sample
            for name, used in container_memory(args.containers).items():
                mem_peak[name] = max(mem_peak.get(name, 0.0), used)
        after = await health(client, args.api)
    state_after = {c: container_state(c) for c in args.containers}

    codes = Counter(r["code"] for r in results)
    lat = [r["s"] for r in results]
    ok_lat = [r["s"] for r in results if r["code"] == 200]
    ttfts = [r["ttft"] for r in results if r["code"] == 200 and r["ttft"] is not None]
    success = codes.get(200, 0) / max(1, len(results))
    print(f"{len(results)} requests, {args.users} concurrent, {elapsed:.1f}s, {'stream' if args.stream else 'non-stream'}")
    print("status codes:", dict(sorted(codes.items())), f"| success {success:.0%}")
    print(f"latency s (all): p50 {statistics.median(lat):.2f}  p95 {pct(lat, .95):.2f}  max {max(lat):.2f}")
    if ok_lat:
        print(f"latency s (answered): p50 {statistics.median(ok_lat):.2f}  p95 {pct(ok_lat, .95):.2f}")
    if ttfts:
        print(f"time to first token s: p50 {statistics.median(ttfts):.2f}  p95 {pct(ttfts, .95):.2f}")
    for code in sorted(c for c in codes if c != 200):
        sample = next(r for r in results if r["code"] == code)
        print(f"  {code}: Retry-After={sample['retry']}  «{sample['detail']}»")
    print("load before:", json.dumps(before, ensure_ascii=False))
    print("load at peak:", json.dumps({k: peak.get(k) for k in ("chat_in_flight", "chat_max_inflight",
                                                                "chat_rejected", "degraded")}, ensure_ascii=False))
    print("load after:", json.dumps(after, ensure_ascii=False))
    for c in args.containers:
        cap = (state_after.get(c) or {}).get("cap_bytes") or 0
        used = mem_peak.get(c, 0.0)
        print(f"container {c}: peak {used / 2**20:.0f} MiB" + (f" of {cap / 2**20:.0f} MiB ({100 * used / cap:.0f}%)" if cap else " (no cap)")
              + f" | restarts {state_before.get(c, {}).get('restarts')} -> {state_after.get(c, {}).get('restarts')}"
              + f" | oom_killed {state_after.get(c, {}).get('oom_killed')}")

    problems = []
    hung = [r for r in results if r["s"] > args.max_latency]
    other = [r for r in results if r["code"] not in (200, 429, 503)]
    if hung:
        problems.append(f"{len(hung)} request(s) took longer than {args.max_latency:.0f}s")
    if other:
        problems.append(f"{len(other)} unexpected status(es): {Counter(r['code'] for r in other)}")
    if peak.get("chat_in_flight", 0) > (peak.get("chat_max_inflight") or 10 ** 9):
        problems.append("more turns in flight than the admission limit")
    if args.min_success and success < args.min_success:
        problems.append(f"success {success:.0%} < {args.min_success:.0%}")
    if args.max_p95 and ok_lat and pct(ok_lat, .95) > args.max_p95:
        problems.append(f"p95 {pct(ok_lat, .95):.1f}s > {args.max_p95:.0f}s")
    if args.max_ttft_p95 and ttfts and pct(ttfts, .95) > args.max_ttft_p95:
        problems.append(f"TTFT p95 {pct(ttfts, .95):.1f}s > {args.max_ttft_p95:.0f}s")
    for c in args.containers:
        b, a = state_before.get(c) or {}, state_after.get(c) or {}
        if not a:
            problems.append(f"container {c} not found")
            continue
        if a.get("oom_killed") or not a.get("running"):
            problems.append(f"container {c} OOM-killed or stopped")
        if b and a.get("restarts", 0) > b.get("restarts", 0):
            problems.append(f"container {c} restarted during the run")
        if a.get("cap_bytes") and mem_peak.get(c, 0) > args.max_mem_pct / 100 * a["cap_bytes"]:
            problems.append(f"container {c} memory above {args.max_mem_pct:.0f}% of its cap")
    print("RESULT:", "PASS" if not problems else "FAIL – " + "; ".join(problems))
    if args.out:
        json.dump({"requests": len(results), "codes": dict(codes), "success": success, "elapsed_s": elapsed,
                   "p95_s": pct(ok_lat, .95), "ttft_p95_s": pct(ttfts, .95), "peak_load": peak,
                   "container_peak_mib": {k: v / 2**20 for k, v in mem_peak.items()},
                   "containers_before": state_before, "containers_after": state_after, "problems": problems},
                  open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
