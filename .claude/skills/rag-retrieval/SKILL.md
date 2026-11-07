---
name: rag-retrieval
description: Retrieval quality for AIP RAG — query analysis/rewriting, Vietnamese diacritic restoration, hybrid dense+BM25 search with RRF in Qdrant, HyDE, multi-hop decomposition, cross-encoder reranking, evidence gate, adaptive context selection and window fitting. Use when the right passage exists in the index but is not retrieved, ranked low, gated out, or dropped from the prompt, or when lists come back incomplete.
---

# RAG Retrieval Optimization

Phạm vi: từ câu người dùng gõ đến tập passage đưa vào prompt. Chỉ dùng skill này sau khi đã xác nhận căn cứ **có trong index** (xem `rag-debugging`).

## Pipeline (chat_use_case.py `_plan_turn` → `_plan_document_turn`)

1. `_reaccented_query`: câu gõ không dấu được khôi phục dấu dựa trên từ vựng của chính corpus (`restore_diacritics_from_corpus`).
2. `query_analyzer.analyze`: một lần gọi LLM trả JSON gồm `standalone_query`, `intent`, `focus_terms`, `scope_terms`, các cờ (`new_topic`, `wants_list`, `aggregate`, `count_unit`, `compare`…).
3. `query_rewriter.rewrite_advanced` tạo text và `sparse_query`. `query_decomposer` xử lý câu multi-hop.
4. Hybrid search: `qdrant_adapter.search` (dense + sparse BM25, fusion bằng RRF, tham số `RAG_RRF_K`), filter theo tenant, role, thời hiệu. HyDE tùy chọn (`RAG_HYDE_AUTO_ENABLED`).
5. Rerank: cross-encoder qua alias `rerank-standard` (`RAG_RERANKER_BACKEND=remote`). Backend `local` dùng FlashRank tiếng Anh, chỉ dành cho dev, **không** dùng để đánh giá tiếng Việt.
6. Mở rộng toàn tài liệu cho các tài liệu tốt nhất (`doc_expansion_*`).
7. Evidence gate: chỉ từ chối khi cả reranker lẫn độ phủ từ khóa theo IDF (`lexical_evidence.py`) đều không tìm thấy hỗ trợ. Có `RAG_CONFIDENCE_GATE_THRESHOLD`.
8. `context_selector.select_adaptive_context`: lấy các passage gần với passage tốt nhất, trong giới hạn budget, giữ thứ tự trong tài liệu.

Mọi tham số đều nằm trong `solutions/rag/config.py` (prefix env `RAG_`). Ưu tiên chỉnh tham số trước khi viết logic mới.

## Cách chẩn đoán theo recall từng bước

Đo recall@k của chunk căn cứ qua các bước: index → candidates → rerank@k → context. Chỗ recall tụt mạnh nhất là chỗ cần sửa.
- Rớt ở **candidates**: sai query (rewrite, mất dấu), BM25 tokenize, filter quá chặt, top_k quá nhỏ.
- Rớt ở **rerank**: reranker không hợp với văn bản dạng bảng hoặc mã. Thử truy xuất theo focus terms, hoặc đưa heading/breadcrumb vào text đem rerank.
- Rớt ở **gate**: ngưỡng gate, hoặc focus terms quá chung chung (`specific_focus_terms`).
- Rớt ở **context**: budget hoặc fit window, passage gần trùng chiếm chỗ (do tài liệu upload trùng, xem `rag-data-engineering`).

Script mẫu đo vị trí chunk trong kết quả dense và sparse: `scripts/diagnose_tc01.py`. Hãy copy ra scratch và đổi query, đừng sửa file gốc.

## Nguyên tắc sửa

- **Tổng quát, không hardcode.** Không thêm từ khóa, regex hay danh sách từ đồng nghĩa theo nội dung một tài liệu. Dùng: tín hiệu từ LLM analyzer, thống kê trên các passage (IDF, độ phủ), cấu trúc tài liệu (heading, bảng), hoặc cấu hình tenant.
- Câu hỏi liệt kê hoặc đếm ("có bao nhiêu bài viết", "liệt kê…"): phải lấy **đủ** mục. Kiểm tra `wants_list` / `aggregate` / `count_unit` và cách context gom đủ các section, đừng chỉ tăng top_k.
- Thay đổi ở analyzer ảnh hưởng mọi lượt. Bắt buộc chạy lại test multi-turn và test routing.
- Theo dõi latency: mỗi lần gọi LLM thêm (HyDE, decompose) đều làm tăng p95. Ghi lại latency trước và sau khi sửa.

## Test liên quan

`tests/test_pre_retrieval_optimization.py`, `test_hyde_engine.py`, `test_multi_hop_iterative_rag.py`, `test_native_sparse_and_pydantic_v2.py`, `test_lost_in_middle_reordering.py`, `test_context_combine.py`, `test_hard_gatekeeper_and_cutoff.py`, `test_rag_speculative_retrieval.py`, `test_diacritics_restoration.py`, `test_vietnamese_id_recognition.py`, `test_rag_quality_fixes.py`.

Thay đổi retrieval cần được chứng minh bằng `rag-evaluation` (so với baseline), không chỉ bằng một câu hỏi thử.
