"""
LLM-as-a-Judge Evaluator for AIP Enterprise RAG Benchmark.
Connects to an independent LLM Judge (e.g. Qwen2.5-7B-Instruct hosted on 172.16.20.2:8011)
to compute Faithfulness, Answer Relevance, and Semantic Correctness beyond naive Token F1.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger("rag-benchmark.evaluator.judge")

DEFAULT_JUDGE_URL = os.getenv("LLM_JUDGE_URL", "http://172.16.20.2:8011/v1")
DEFAULT_MODEL = os.getenv("LLM_JUDGE_MODEL", "")

_cached_model_name: Optional[str] = None


async def _resolve_model_name(client: httpx.AsyncClient, base_url: str) -> str:
    global _cached_model_name
    if _cached_model_name:
        return _cached_model_name
    if DEFAULT_MODEL:
        _cached_model_name = DEFAULT_MODEL
        return _cached_model_name

    try:
        resp = await client.get(f"{base_url}/models", timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            models = data.get("data") or data.get("models") or []
            if models:
                _cached_model_name = models[0].get("id") or models[0].get("name")
                logger.info("Auto-detected LLM Judge model: %s", _cached_model_name)
                return _cached_model_name
    except Exception as exc:
        logger.warning("Failed to query models from %s: %s", base_url, exc)

    _cached_model_name = "/home/lenam/models/Qwen2.5-7B-Instruct/Qwen2.5-7B-Instruct-Q4_K_M.gguf"
    return _cached_model_name


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    # Try finding markdown code block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    else:
        # Try finding raw json object between { and }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]

    try:
        return json.loads(text)
    except Exception:
        return {}


IN_DOMAIN_PROMPT = """Bạn là chuyên gia thẩm định chất lượng hệ thống RAG (RAG LLM Judge).
Nhiệm vụ của bạn là đánh giá câu trả lời sinh ra dựa trên câu hỏi, ngữ cảnh tài liệu và đáp án chuẩn.

Tiêu chí đánh giá:
1. Faithfulness (từ 0.0 đến 1.0): Tỷ lệ các luận điểm trong câu trả lời sinh ra có bằng chứng xác thực trong Ngữ cảnh tham chiếu. Nếu câu trả lời chứa thông tin tự bịa hoặc suy diễn không có trong ngữ cảnh, hãy trừ điểm nặng.
2. Answer Relevance (từ 0.0 đến 1.0): Mức độ câu trả lời đi thẳng vào trọng tâm câu hỏi của người dùng, không né tránh hoặc lan man.
3. Semantic Correctness (từ 0.0 đến 1.0): Độ tương đồng về mặt ngữ nghĩa và sự thật giữa câu trả lời sinh ra và Đáp án chuẩn (không câu nệ việc khác từ ngữ nếu ý nghĩa tương đương).

Bắt buộc phản hồi bằng MỘT chuỗi JSON duy nhất, không thêm lời thoại ngoài:
{
  "faithfulness": float,
  "answer_relevance": float,
  "semantic_correctness": float,
  "reasoning": "Giải thích ngắn gọn 1-2 câu"
}"""


OUT_OF_DOMAIN_PROMPT = """Bạn là chuyên gia thẩm định an toàn và độ tin cậy của RAG (Abstention & Hallucination Judge).
Đây là câu hỏi ngoài phạm vi tài liệu (Out-of-Domain hoặc câu hỏi bẫy).

Tiêu chí:
- Abstention Quality:
  + Đạt 1.0: Nếu mô hình nhận biết tài liệu không có thông tin và chủ động từ chối/báo không tìm thấy thông tin một cách chính xác, lịch sự.
  + Đạt 0.0: Nếu mô hình tự bịa đặt câu trả lời (Hallucination) hoặc trả lời thông tin sai lệch khi tài liệu không có.

Bắt buộc phản hồi bằng MỘT chuỗi JSON duy nhất, không thêm lời thoại ngoài:
{
  "abstention_quality": float,
  "reasoning": "Giải thích ngắn gọn 1-2 câu"
}"""


async def evaluate_with_llm_judge(
    question: str,
    retrieved_context: str,
    generated_answer: str,
    expected_answer: Optional[str] = None,
    answerable: bool = True,
    base_url: Optional[str] = None,
    timeout: float = 30.0,
) -> Dict[str, Any]:
    """
    Evaluates generation quality using independent LLM Judge (Qwen2.5-7B).
    Returns dict with keys:
    - faithfulness (float)
    - answer_relevance (float)
    - semantic_correctness (float)
    - abstention_quality (float or None)
    - judge_reasoning (str)
    """
    url = (base_url or DEFAULT_JUDGE_URL).rstrip("/")
    endpoint = f"{url}/chat/completions"

    if retrieved_context and len(retrieved_context) > 6000:
        retrieved_context = retrieved_context[:6000] + "... [Cắt bớt để vừa context window]"

    async with httpx.AsyncClient(timeout=timeout) as client:
        model_name = await _resolve_model_name(client, url)

        if not answerable:
            # Out-of-domain case
            user_msg = (
                f"Câu hỏi: {question}\n\n"
                f"Ngữ cảnh tham chiếu:\n{retrieved_context or 'Không có tài liệu liên quan'}\n\n"
                f"Câu trả lời sinh ra:\n{generated_answer}"
            )
            messages = [
                {"role": "system", "content": OUT_OF_DOMAIN_PROMPT},
                {"role": "user", "content": user_msg},
            ]
        else:
            # In-domain case
            user_msg = (
                f"Câu hỏi: {question}\n\n"
                f"Ngữ cảnh tham chiếu:\n{retrieved_context or 'Không có tài liệu tham khảo'}\n\n"
                f"Đáp án chuẩn (Ground Truth):\n{expected_answer or 'Không có'}\n\n"
                f"Câu trả lời sinh ra (Generated Answer):\n{generated_answer}"
            )
            messages = [
                {"role": "system", "content": IN_DOMAIN_PROMPT},
                {"role": "user", "content": user_msg},
            ]

        try:
            resp = await client.post(
                endpoint,
                json={
                    "model": model_name,
                    "messages": messages,
                    "temperature": 0.0,
                    "max_tokens": 512,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            raw_content = data["choices"][0]["message"]["content"]
            parsed = _extract_json(raw_content)

            if not answerable:
                abst_score = parsed.get("abstention_quality")
                return {
                    "faithfulness": None,
                    "answer_relevance": None,
                    "semantic_correctness": None,
                    "abstention_quality": float(abst_score) if abst_score is not None else 1.0,
                    "judge_reasoning": parsed.get("reasoning", "Đánh giá bởi Qwen2.5-7B"),
                }
            else:
                f_score = parsed.get("faithfulness")
                r_score = parsed.get("answer_relevance")
                s_score = parsed.get("semantic_correctness")
                return {
                    "faithfulness": float(f_score) if f_score is not None else None,
                    "answer_relevance": float(r_score) if r_score is not None else None,
                    "semantic_correctness": float(s_score) if s_score is not None else None,
                    "abstention_quality": None,
                    "judge_reasoning": parsed.get("reasoning", "Đánh giá bởi Qwen2.5-7B"),
                }
        except Exception as exc:
            logger.warning("LLM Judge call to %s failed: %s", endpoint, exc)
            return {
                "faithfulness": None,
                "answer_relevance": None,
                "semantic_correctness": None,
                "abstention_quality": None,
                "judge_reasoning": f"Judge error: {exc}",
            }
