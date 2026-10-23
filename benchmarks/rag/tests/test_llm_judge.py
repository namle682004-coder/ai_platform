"""
Unit Tests for LLM Judge Evaluator (Qwen2.5-7B on 172.16.20.2:8011).
"""

import pytest
from benchmarks.rag.src.rag_benchmark.evaluators.llm_judge import evaluate_with_llm_judge, _extract_json


def test_extract_json():
    # Markdown json block
    raw1 = "```json\n{\"faithfulness\": 0.9, \"reasoning\": \"ok\"}\n```"
    assert _extract_json(raw1) == {"faithfulness": 0.9, "reasoning": "ok"}

    # Raw text with braces
    raw2 = "Kết quả đánh giá:\n{\"faithfulness\": 1.0, \"reasoning\": \"hoàn hảo\"}"
    assert _extract_json(raw2) == {"faithfulness": 1.0, "reasoning": "hoàn hảo"}


@pytest.mark.anyio
async def test_llm_judge_live_connection():
    # Test with live Qwen2.5 on 172.16.20.2:8011
    res = await evaluate_with_llm_judge(
        question="Thủ quỹ làm công việc gì?",
        retrieved_context="Thủ quỹ quản lý quỹ tiền mặt của cơ quan.",
        generated_answer="Nhiệm vụ của thủ quỹ là quản lý ngân quỹ tiền mặt tại cơ quan.",
        expected_answer="Quản lý tiền mặt tại cơ quan.",
        answerable=True,
    )
    assert res["faithfulness"] is not None
    assert res["faithfulness"] >= 0.7
    assert res["answer_relevance"] is not None
    assert res["semantic_correctness"] is not None
    assert "judge_reasoning" in res

