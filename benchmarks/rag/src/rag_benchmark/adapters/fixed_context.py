"""
Fixed Context Adapter for Track A (Generation-only Evaluation).
Supplies the exact Gold Reference Context directly to the model, bypassing retrieval.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional
import httpx

from .base import NormalizedResponse, RAGAdapter


class FixedContextAdapter:
    """Invokes neural LLM directly with isolated gold-standard reference context."""

    def __init__(
        self,
        vllm_url: Optional[str] = None,
        model: Optional[str] = None,
        api_key: str = "aip_live_valid_test_key_12345",
        timeout: float = 30.0,
    ) -> None:
        self.vllm_url = (vllm_url or os.getenv("VLLM_SERVER_URL", "http://172.16.20.2:8011/v1")).rstrip("/")
        self.model = model or os.getenv("VLLM_MODEL", "/home/lenam/models/Qwen2.5-7B-Instruct/Qwen2.5-7B-Instruct-Q4_K_M.gguf")
        self.api_key = api_key
        self.timeout = timeout

    async def answer(
        self,
        question: str,
        *,
        context: Optional[List[Dict[str, Any]]] = None,
        top_k: int = 5,
    ) -> NormalizedResponse:
        start_t = time.time()
        context_blocks = []
        if context:
            for idx, c in enumerate(context, start=1):
                txt = c.get("text") or c.get("quote") or ""
                doc_title = c.get("document_id") or "Tài liệu"
                context_blocks.append(f"[{idx}] (Tài liệu: {doc_title})\n{txt}")

        context_str = "\n\n".join(context_blocks) if context_blocks else "Không có tài liệu tham khảo nào."
        if len(context_str) > 8000:
            context_str = context_str[:8000] + "... [Trích đoạn cắt gọn để vừa context window]"

        messages = [
            {
                "role": "system",
                "content": (
                    "Bạn là trợ lý AI chuyên nghiệp của nền tảng AIP.\n"
                    "Hãy trả lời câu hỏi CHÍNH XÁC và HOÀN TOÀN dựa vào tài liệu tham khảo sau:\n\n"
                    f"--- TÀI LIỆU NỘI BỘ THAM KHẢO ---\n{context_str}\n---------------------------------\n"
                    "Nguyên tắc: Luôn trích dẫn [1], [2] ở cuối câu. "
                    "Nếu không có thông tin trong tài liệu, hãy thông báo rõ ràng."
                ),
            },
            {"role": "user", "content": question},
        ]

        endpoint = f"{self.vllm_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": 1024,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(endpoint, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        latency_ms = (time.time() - start_t) * 1000
        choice = data["choices"][0]
        answer_text = choice["message"]["content"]
        usage = data.get("usage", {})

        return NormalizedResponse(
            answer=answer_text,
            retrieved_chunks=[],
            citations=[],
            latency_ms=round(latency_ms, 2),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            usage=usage,
        )
