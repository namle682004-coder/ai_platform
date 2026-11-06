"""
Rubric LLM judge for the acceptance suite.

The judge grades against what the acceptance team wrote for the case (expected answer + FAIL
conditions) and against the passages the system actually used (from the trace), returning a
pass/fail verdict plus RAG-triad style scores. Several votes can be taken (majority verdict) to
reduce the variance of a small judge model. A judge is only trusted for the go-live gate after
calibration against human grades (see calibration.py).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

RUBRIC_PROMPT = """Bạn là giám khảo nghiệm thu chatbot tra cứu tài liệu nội bộ. Chấm CÂU TRẢ LỜI của chatbot theo ĐÁP ÁN KỲ VỌNG và ĐIỀU KIỆN FAIL do người nghiệm thu viết.

Quy tắc chấm:
1. "fail" nếu câu trả lời vi phạm BẤT KỲ điều kiện FAIL nào.
2. "fail" nếu thiếu ý bắt buộc của đáp án kỳ vọng, hoặc có thông tin mâu thuẫn với đáp án kỳ vọng (sai mã, sai số, sai tên, sai lớp/mục).
3. "fail" nếu khẳng định thông tin không có trong NGỮ CẢNH TÀI LIỆU (bịa). Nếu ngữ cảnh ghi "(không có)", bỏ qua quy tắc này.
4. KHÔNG trừ điểm khi: diễn đạt khác nhưng cùng nghĩa, thêm chi tiết đúng theo tài liệu, thêm gợi ý liên quan, có phần nguồn trích dẫn.
5. Khi TÀI LIỆU CÓ THÔNG TIN = không: "pass" khi chatbot nói rõ tài liệu không có thông tin (có thể kèm chuyển hỗ trợ) và không bịa.
6. Hội thoại nhiều lượt: chấm cả hội thoại theo đáp án kỳ vọng (từng lượt phải đúng như mô tả).

Trả về DUY NHẤT một JSON, không giải thích ngoài JSON:
{"verdict": "pass" hoặc "fail", "correctness": số 0..1, "completeness": số 0..1, "faithfulness": số 0..1, "violated": "điều kiện FAIL bị vi phạm, rỗng nếu không", "reason": "1-2 câu"}"""

RUBRIC_VERSION = "rubric-v1-" + hashlib.sha256(RUBRIC_PROMPT.encode("utf-8")).hexdigest()[:8]
CONTEXT_CHARS = 9000


@dataclass
class JudgeConfig:
    base_url: str = field(default_factory=lambda: os.getenv("LLM_JUDGE_URL", "http://172.16.20.2:8011/v1"))
    model: str = field(default_factory=lambda: os.getenv("LLM_JUDGE_MODEL", ""))
    api_key: str = field(default_factory=lambda: os.getenv("LLM_JUDGE_API_KEY", ""))
    votes: int = 1
    temperature: float = 0.0
    timeout: float = 120.0
    max_tokens: int = 400

    def identity(self) -> Dict[str, Any]:
        return {"model": self.model, "votes": self.votes, "temperature": self.temperature}


@dataclass
class JudgeResult:
    verdict: Optional[str]  # "pass" | "fail" | None (judge unavailable)
    correctness: Optional[float] = None
    completeness: Optional[float] = None
    faithfulness: Optional[float] = None
    violated: str = ""
    reason: str = ""
    votes: List[Dict[str, Any]] = field(default_factory=list)
    items: List[Dict[str, Any]] = field(default_factory=list)  # checklist grader: verdict per core point
    uncertain: bool = False  # the verdict rests on the judge model, not on deterministic matching

    def to_dict(self) -> Dict[str, Any]:
        return {"verdict": self.verdict, "correctness": self.correctness, "completeness": self.completeness,
                "faithfulness": self.faithfulness, "violated": self.violated, "reason": self.reason,
                "votes": self.votes, "items": self.items, "uncertain": self.uncertain}


def extract_json(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start:end + 1]
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _score(v: Any) -> Optional[float]:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return None


def build_messages(
    conversation: Sequence[Tuple[str, str]],
    expected_answer: str,
    fail_conditions: str,
    answerable: bool,
    context: str,
) -> List[Dict[str, str]]:
    if len(conversation) == 1:
        dialogue = f"CÂU HỎI: {conversation[0][0]}\n\nCÂU TRẢ LỜI CỦA CHATBOT:\n{conversation[0][1]}"
    else:
        dialogue = "HỘI THOẠI:\n" + "\n\n".join(
            f"[Lượt {i}] Người dùng: {q}\n[Lượt {i}] Chatbot: {a}" for i, (q, a) in enumerate(conversation, start=1)
        )
    ctx = (context or "").strip()
    if len(ctx) > CONTEXT_CHARS:
        ctx = ctx[:CONTEXT_CHARS] + " …"
    user = (
        f"ĐÁP ÁN KỲ VỌNG: {expected_answer or '(không có)'}\n"
        f"ĐIỀU KIỆN FAIL: {fail_conditions or '(không có)'}\n"
        f"TÀI LIỆU CÓ THÔNG TIN: {'có' if answerable else 'không'}\n\n"
        f"NGỮ CẢNH TÀI LIỆU:\n{ctx or '(không có)'}\n\n{dialogue}\n\nJSON:"
    )
    return [{"role": "system", "content": RUBRIC_PROMPT}, {"role": "user", "content": user}]


class JudgeClient:
    """OpenAI-compatible chat client shared by the graders."""

    version = ""

    def __init__(self, cfg: JudgeConfig, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self.cfg = cfg
        self._client = httpx.AsyncClient(timeout=cfg.timeout, transport=transport)

    async def aclose(self) -> None:
        await self._client.aclose()

    def identity(self) -> Dict[str, Any]:
        return {**self.cfg.identity(), "rubric_version": self.version}

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.cfg.api_key}"} if self.cfg.api_key else {}

    async def resolve_model(self) -> str:
        if not self.cfg.model:
            try:
                res = await self._client.get(f"{self.cfg.base_url.rstrip('/')}/models", headers=self._headers())
                models = (res.json().get("data") or []) if res.status_code == 200 else []
                self.cfg.model = str(models[0].get("id")) if models else "default"
            except (httpx.HTTPError, ValueError):
                self.cfg.model = "default"
        return self.cfg.model

    async def complete(self, messages: List[Dict[str, str]], max_tokens: Optional[int] = None) -> Optional[str]:
        body = {"model": await self.resolve_model(), "messages": messages, "temperature": self.cfg.temperature,
                "max_tokens": max_tokens or self.cfg.max_tokens}
        try:
            res = await self._client.post(
                f"{self.cfg.base_url.rstrip('/')}/chat/completions", json=body, headers=self._headers()
            )
            res.raise_for_status()
            return str(res.json()["choices"][0]["message"]["content"])
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError):
            return None


class RubricJudge(JudgeClient):
    """Holistic verdict against the expected answer and FAIL conditions (reliable only with a strong model)."""

    version = RUBRIC_VERSION

    async def grade(self, case: Any, turns: Sequence[Dict[str, Any]], context: str = "") -> JudgeResult:
        return await self.judge([(t.get("query", ""), t.get("answer", "")) for t in turns], case.expected_answer,
                                case.fail_conditions, case.answerable, context)

    async def _vote(self, messages: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        content = await self.complete(messages)
        if content is None:
            return None
        data = extract_json(content)
        verdict = str(data.get("verdict") or "").strip().lower()
        if verdict not in ("pass", "fail"):
            return None
        return {
            "verdict": verdict, "correctness": _score(data.get("correctness")),
            "completeness": _score(data.get("completeness")), "faithfulness": _score(data.get("faithfulness")),
            "violated": str(data.get("violated") or ""), "reason": str(data.get("reason") or ""),
        }

    async def judge(
        self,
        conversation: Sequence[Tuple[str, str]],
        expected_answer: str,
        fail_conditions: str = "",
        answerable: bool = True,
        context: str = "",
    ) -> JudgeResult:
        messages = build_messages(conversation, expected_answer, fail_conditions, answerable, context)
        votes = [v for v in await asyncio.gather(*[self._vote(messages) for _ in range(max(1, self.cfg.votes))]) if v]
        if not votes:
            return JudgeResult(verdict=None, reason="judge unavailable or unparsable")
        fails = sum(1 for v in votes if v["verdict"] == "fail")
        # Ties fail: the gate must not pass on an undecided judge.
        verdict = "fail" if fails * 2 >= len(votes) else "pass"
        main = next(v for v in votes if v["verdict"] == verdict)

        def mean(key: str) -> Optional[float]:
            vals = [v[key] for v in votes if v[key] is not None]
            return round(sum(vals) / len(vals), 4) if vals else None

        return JudgeResult(
            verdict=verdict, correctness=mean("correctness"), completeness=mean("completeness"),
            faithfulness=mean("faithfulness"), violated=main["violated"], reason=main["reason"], votes=votes,
        )
