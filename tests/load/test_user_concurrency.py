"""
Enterprise Load Testing Suite - Tier 1: User Concurrency & High RPS Load
Simulates virtual users (VUs), concurrent HTTP requests, latency percentiles (P95/P99),
and multi-tenant rate limiting (HTTP 429) against AIP Control Plane Gateway.
"""

import asyncio
import time
import statistics
from typing import List, Dict, Any
import httpx
import pytest

from src.main import app

class LoadTestReport:
    def __init__(self, name: str):
        self.name = name
        self.durations: List[float] = []
        self.status_codes: Dict[int, int] = {}
        self.errors: List[str] = []
        self.start_time: float = 0.0
        self.end_time: float = 0.0

    def record(self, status_code: int, duration_ms: float):
        self.durations.append(duration_ms)
        self.status_codes[status_code] = self.status_codes.get(status_code, 0) + 1

    def record_error(self, err_msg: str):
        self.errors.append(err_msg)

    def summary(self) -> Dict[str, Any]:
        total_reqs = len(self.durations) + len(self.errors)
        total_time = self.end_time - self.start_time
        rps = (total_reqs / total_time) if total_time > 0 else 0.0
        sorted_dur = sorted(self.durations) if self.durations else [0.0]

        return {
            "name": self.name,
            "total_requests": total_reqs,
            "successful_200": self.status_codes.get(200, 0),
            "rate_limited_429": self.status_codes.get(429, 0),
            "other_status_codes": {k: v for k, v in self.status_codes.items() if k not in (200, 429)},
            "network_errors": len(self.errors),
            "throughput_rps": round(rps, 2),
            "latency_p50_ms": round(sorted_dur[int(len(sorted_dur) * 0.50)], 2),
            "latency_p95_ms": round(sorted_dur[min(int(len(sorted_dur) * 0.95), len(sorted_dur) - 1)], 2),
            "latency_p99_ms": round(sorted_dur[min(int(len(sorted_dur) * 0.99), len(sorted_dur) - 1)], 2),
            "latency_avg_ms": round(statistics.mean(sorted_dur), 2) if sorted_dur else 0.0,
            "duration_total_sec": round(total_time, 2)
        }


async def _worker_task(
    client: httpx.AsyncClient,
    url: str,
    headers: Dict[str, str],
    report: LoadTestReport,
    semaphore: asyncio.Semaphore
):
    async with semaphore:
        t0 = time.perf_counter()
        try:
            resp = await client.get(url, headers=headers)
            t1 = time.perf_counter()
            report.record(resp.status_code, (t1 - t0) * 1000.0)
        except Exception as exc:
            report.record_error(str(exc))


async def run_concurrent_load_test(
    app_instance,
    endpoint: str,
    concurrency: int,
    total_requests: int,
    headers: Dict[str, str] = None,
    scenario_name: str = "Concurrent Load Test"
) -> LoadTestReport:
    """Run an async load test using httpx ASGI in-memory transport or remote URL."""
    report = LoadTestReport(scenario_name)
    headers = headers or {}
    semaphore = asyncio.Semaphore(concurrency)

    transport = httpx.ASGITransport(app=app_instance)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        report.start_time = time.perf_counter()
        tasks = [
            _worker_task(client, endpoint, headers, report, semaphore)
            for _ in range(total_requests)
        ]
        await asyncio.gather(*tasks)
        report.end_time = time.perf_counter()

    return report


@pytest.mark.asyncio
async def test_high_concurrency_gateway_health():
    """Scenario 1: 50 concurrent users blasting health probes without degradation."""
    concurrency = 50
    total_requests = 200

    report = await run_concurrent_load_test(
        app_instance=app,
        endpoint="/health/live",
        concurrency=concurrency,
        total_requests=total_requests,
        scenario_name="50 Concurrency Health Probe"
    )

    stats = report.summary()
    print("\n--- LOAD TEST RESULTS: 50 CONCURRENCY HEALTH ---")
    print(stats)

    assert stats["total_requests"] == total_requests
    assert stats["successful_200"] == total_requests
    assert stats["network_errors"] == 0
    assert stats["latency_p95_ms"] < 200.0, f"P95 latency too high: {stats['latency_p95_ms']}ms"


@pytest.mark.asyncio
async def test_multi_user_api_catalog_concurrency():
    """Scenario 2: Concurrent Virtual Users querying project APIs catalog."""
    concurrency = 40
    total_requests = 160

    report = await run_concurrent_load_test(
        app_instance=app,
        endpoint="/project/f40b6a70-ea64-4d01-90dc-53a2d7a81395/apis",
        concurrency=concurrency,
        total_requests=total_requests,
        scenario_name="40 Concurrency API Catalog"
    )

    stats = report.summary()
    print("\n--- LOAD TEST RESULTS: 40 CONCURRENCY CATALOG ---")
    print(stats)

    assert stats["total_requests"] == total_requests
    assert stats["successful_200"] == total_requests
    assert stats["latency_p95_ms"] < 300.0


if __name__ == "__main__":
    async def main():
        print("Starting Local In-Memory Concurrency Benchmark...")
        r1 = await run_concurrent_load_test(app, "/health/live", 50, 200, scenario_name="50 VUs Health")
        print("\nResult 1:", r1.summary())

        r2 = await run_concurrent_load_test(app, "/project/f40b6a70-ea64-4d01-90dc-53a2d7a81395/apis", 40, 160, scenario_name="40 VUs Catalog")
        print("\nResult 2:", r2.summary())

    asyncio.run(main())
