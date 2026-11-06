"""
Client of the RAG chat API for the acceptance suite: conversation sessions, streaming or not, and
retrieval of the per-turn pipeline trace by the trace id the API returns.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

# A busy service is asked again after the wait it requests (bounded), at most this many times per turn.
BUSY_RETRIES = 3
BUSY_MIN_WAIT_S = 10.0
BUSY_MAX_WAIT_S = 120.0


def _retry_after(value: Optional[str]) -> float:
    try:
        return max(0.0, float(value)) if value else BUSY_MIN_WAIT_S
    except ValueError:
        return BUSY_MIN_WAIT_S


@dataclass
class TurnResult:
    query: str
    session_id: str
    answer: str = ""
    intent: Optional[str] = None
    status: Optional[str] = None
    is_refusal: bool = False
    escalated: bool = False
    citations: List[Dict[str, Any]] = field(default_factory=list)
    trace_id: Optional[str] = None
    latency_s: Optional[float] = None
    ttft_s: Optional[float] = None
    error: Optional[str] = None
    trace: Optional[Dict[str, Any]] = None
    retry_after: Optional[float] = None  # set when the service refused the turn as busy

    def summary(self) -> Dict[str, Any]:
        return {
            "query": self.query, "session_id": self.session_id, "answer": self.answer, "intent": self.intent,
            "status": self.status, "is_refusal": self.is_refusal, "escalated": self.escalated,
            "citations": self.citations, "trace_id": self.trace_id, "latency_s": self.latency_s,
            "ttft_s": self.ttft_s, "error": self.error,
        }


class RagApiClient:
    def __init__(
        self,
        base_url: str,
        headers: Optional[Dict[str, str]] = None,
        admin_headers: Optional[Dict[str, str]] = None,
        stream: bool = False,
        timeout: float = 180.0,
        request_overrides: Optional[Dict[str, Any]] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = dict(headers or {})
        self.admin_headers = {**self.headers, **(admin_headers or {})}
        self.stream = stream
        self.request_overrides = dict(request_overrides or {})
        self._client = httpx.AsyncClient(timeout=timeout, transport=transport)

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def new_session() -> str:
        return f"eval_{uuid.uuid4().hex[:12]}"

    async def chat(self, query: str, session_id: str) -> TurnResult:
        """
        One turn. A busy service (429 / 503 / stream status 'busy') is waited for as it asks (Retry-After)
        and asked again, a bounded number of times: the evaluation must never add load to a saturated host.
        """
        for attempt in range(BUSY_RETRIES + 1):
            result = await self._chat_once(query, session_id)
            if result.retry_after is None or attempt == BUSY_RETRIES:
                return result
            wait = min(max(result.retry_after, BUSY_MIN_WAIT_S), BUSY_MAX_WAIT_S)
            print(f"  service busy ({result.error or result.status}); waiting {wait:.0f}s before asking again",
                  flush=True)
            await asyncio.sleep(wait)
        return result

    async def _chat_once(self, query: str, session_id: str) -> TurnResult:
        body = {"query": query, "conversation_id": session_id, **self.request_overrides}
        result = TurnResult(query=query, session_id=session_id)
        t0 = time.perf_counter()
        try:
            if self.stream:
                await self._chat_stream(body, result, t0)
            else:
                res = await self._client.post(f"{self.base_url}/v1/rag/chat", json=body, headers=self.headers)
                res.raise_for_status()
                self._apply(result, res.json())
                result.trace_id = result.trace_id or res.headers.get("X-Trace-ID")
        except httpx.HTTPStatusError as exc:
            result.error = f"{type(exc).__name__}: {exc}"
            if exc.response.status_code in (429, 503):
                result.retry_after = _retry_after(exc.response.headers.get("Retry-After"))
        except (httpx.HTTPError, ValueError) as exc:
            result.error = f"{type(exc).__name__}: {exc}"
        if result.status == "busy" and result.retry_after is None:
            result.retry_after = BUSY_MIN_WAIT_S
        if result.status in ("busy", "service_unavailable") and not result.error:
            result.error = f"service {result.status}"
        result.latency_s = round(time.perf_counter() - t0, 3)
        return result

    async def _chat_stream(self, body: Dict[str, Any], result: TurnResult, t0: float) -> None:
        parts: List[str] = []
        async with self._client.stream(
            "POST", f"{self.base_url}/v1/rag/chat/stream", json=body, headers=self.headers
        ) as res:
            res.raise_for_status()
            result.trace_id = res.headers.get("X-Trace-ID")
            async for line in res.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = json.loads(line[6:])
                if payload.get("reset"):
                    parts.clear()  # the server is generating the answer again: drop the partial text
                if "token" in payload:
                    if result.ttft_s is None:
                        result.ttft_s = round(time.perf_counter() - t0, 3)
                    parts.append(str(payload["token"]))
                if payload.get("done"):
                    self._apply(result, payload)
        result.answer = "".join(parts)

    @staticmethod
    def _apply(result: TurnResult, data: Dict[str, Any]) -> None:
        if "answer" in data:
            result.answer = data.get("answer") or ""
        result.intent = data.get("intent")
        result.status = data.get("status")
        result.is_refusal = bool(data.get("is_refusal"))
        result.escalated = bool(data.get("escalation"))
        result.citations = list(data.get("citations") or [])
        result.trace_id = data.get("trace_id") or (data.get("telemetry") or {}).get("trace_id") or result.trace_id
        if data.get("retry_after") is not None:
            result.retry_after = _retry_after(str(data.get("retry_after")))

    async def fetch_trace(self, trace_id: str, attempts: int = 6, delay_s: float = 0.25) -> Optional[Dict[str, Any]]:
        """Traces are written asynchronously after the response: retry briefly."""
        for i in range(attempts):
            try:
                res = await self._client.get(f"{self.base_url}/v1/rag/traces/{trace_id}", headers=self.admin_headers)
            except httpx.HTTPError:
                return None
            if res.status_code == 200:
                return res.json()
            if res.status_code in (401, 403):
                return None
            await asyncio.sleep(delay_s * (i + 1))
        return None

    async def index_snapshot(self) -> Optional[Dict[str, Any]]:
        try:
            res = await self._client.get(f"{self.base_url}/v1/rag/eval/index-snapshot", headers=self.admin_headers)
        except httpx.HTTPError:
            return None
        return res.json() if res.status_code == 200 else None
