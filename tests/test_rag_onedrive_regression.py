"""
Automated RAG Regression Test Suite on Multi-Entity OneDrive Position Documents.
Ensures algorithm robustness against Entity Collisions, Section Code Confusion,
and Cross-Document Entity Hallucination on real docx datasets.
"""

import asyncio
import pytest
from typing import Any, Dict

from solutions.rag.interfaces.api.chat_router import chat_use_case
from solutions.rag.application.dtos import RagChatRequestDTO

REGRESSION_CASES = [
    {
        "id": "TC01",
        "category": "Trưởng phòng - Mục 2.1 (Anti Entity Collision vs Hiệu trưởng)",
        "query": "Nhiệm vụ cụ thể mục 2.1 của Trưởng phòng gồm những công việc gì?",
        "expected_facts": [
            "kế hoạch", "phòng", "viên chức", "người lao động", "chuyên môn", "phối hợp"
        ],
        "forbidden_facts": [
            "Phó Hiệu trưởng thực hiện", "cuộc họp của lãnh đạo trường"
        ],
    },
    {
        "id": "TC02",
        "category": "Phó Hiệu trưởng - Mục 2.1",
        "query": "Nhiệm vụ cụ thể mục 2.1 của vị trí Phó Hiệu trưởng gồm những công việc gì?",
        "expected_facts": [
            "Giúp Hiệu trưởng", "quản lý", "đào tạo", "bồi dưỡng", "tài sản"
        ],
        "forbidden_facts": [
            "hoạt động của phòng theo chức năng"
        ],
    },
    {
        "id": "TC03",
        "category": "Trưởng khoa - Quan hệ quản lý bên trong 3.1",
        "query": "Trưởng khoa chịu sự quản lý trực tiếp và kiểm duyệt kết quả bởi ai?",
        "expected_facts": [
            "Lãnh đạo trường"
        ],
        "forbidden_facts": [
            "Bộ Nội vụ"
        ],
    },
    {
        "id": "TC04",
        "category": "Thủ quỹ - Mục tiêu vị trí việc làm",
        "query": "Mục tiêu vị trí việc làm của vị trí Thủ quỹ là gì?",
        "expected_facts": [
            "thu, chi", "quỹ tiền mặt"
        ],
        "forbidden_facts": [
            "11 văn kiện", "Trung tâm dữ liệu"
        ],
    },
    {
        "id": "TC05",
        "category": "Thủ quỹ - Quan hệ quản lý trực tiếp",
        "query": "Thủ quỹ chịu sự quản lý trực tiếp và kiểm duyệt kết quả bởi ai?",
        "expected_facts": [
            "Trưởng phòng", "lãnh đạo phòng"
        ],
        "forbidden_facts": [
            "Tỉnh ủy"
        ],
    },
    {
        "id": "TC06",
        "category": "Phụ trách kế toán - Tiêu chuẩn trình độ đào tạo",
        "query": "Yêu cầu về trình độ đào tạo chuyên môn của vị trí Phụ trách kế toán là gì?",
        "expected_facts": [
            "Đại học", "kế toán", "tài chính"
        ],
        "forbidden_facts": [
            "tiến sĩ"
        ],
    },
    {
        "id": "TC07",
        "category": "Phó trưởng phòng - Phạm vi quyền hạn",
        "query": "Phó trưởng phòng có những quyền hạn cụ thể nào theo quy định?",
        "expected_facts": [
            "phương pháp", "thông tin", "Trưởng phòng"
        ],
        "forbidden_facts": [],
    },
    {
        "id": "TC08",
        "category": "So sánh chéo 2 thực thể - Hiệu trưởng vs Trưởng phòng",
        "query": "So sánh yêu cầu kinh nghiệm công tác giữa vị trí Hiệu trưởng và Trưởng phòng?",
        "expected_facts": [
            "Hiệu trưởng", "01 năm|1 năm", "Phó Hiệu trưởng", "Trưởng phòng", "2 năm|02 năm", "Phó Trưởng phòng"
        ],
        "forbidden_facts": [],
    },
    {
        "id": "TC09",
        "category": "So sánh chéo 2 thực thể - Trưởng khoa vs Trưởng phòng",
        "query": "So sánh đối tượng quản lý trực tiếp giữa Trưởng khoa và Trưởng phòng?",
        "expected_facts": [
            "Trưởng khoa", "Phó trưởng khoa", "giảng viên", "Trưởng phòng", "viên chức"
        ],
        "forbidden_facts": [],
    },
    {
        "id": "TC10",
        "category": "Bẫy ngoài thẩm quyền / Ngoài tài liệu (Anti-Hallucination)",
        "query": "Thủ quỹ có quyền tự ý ký lệnh chi và chuyển tiền từ tài khoản của Trường Chính trị Hoàng Đình Giong không?",
        "expected_facts": [
            "không"
        ],
        "forbidden_facts": [
            "được quyền tự ý"
        ],
    },
]


@pytest.mark.usefixtures("requires_embedding_runtime")
@pytest.mark.parametrize("case", REGRESSION_CASES, ids=[c["id"] for c in REGRESSION_CASES])
def test_onedrive_position_regression_case(case: Dict[str, Any]):
    query = case["query"]
    expected_facts = case["expected_facts"]
    forbidden_facts = case.get("forbidden_facts", [])

    req = RagChatRequestDTO(
        query=query,
        conversation_id=f"regression_{case['id']}",
        max_tokens=768,
        temperature=0.1,
    )

    res = asyncio.run(
        chat_use_case.execute(
            request=req,
            tenant_id="proj_default",
            user_id="regression_runner",
            user_role="user",
        )
    )

    ans = res.answer or ""
    ans_lower = ans.lower()

    # 1. Zero Entity Collision Assertion
    for fb in forbidden_facts:
        assert fb.lower() not in ans_lower, (
            f"[{case['id']}] Entity Collision Detected! Found forbidden fact '{fb}' in answer:\n{ans}"
        )

    # 2. Fact Coverage Check
    matched = []
    missing = []
    for f in expected_facts:
        opts = [opt.strip().lower() for opt in f.split("|")]
        if any(opt in ans_lower for opt in opts):
            matched.append(f)
        else:
            missing.append(f)

    coverage = len(matched) / len(expected_facts) if expected_facts else 1.0
    # Every case must achieve at least 65% coverage on its own
    assert coverage >= 0.65, (
        f"[{case['id']}] Low coverage ({coverage*100:.1f}%). Missing: {missing}\nAnswer:\n{ans}"
    )

    # 3. Grounded Citation Assertion for Non-Refusal Answers
    if not res.is_refusal:
        assert len(res.citations) >= 1, (
            f"[{case['id']}] Answer is non-refusal but has 0 citations!"
        )
