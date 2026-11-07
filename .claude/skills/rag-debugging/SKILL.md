---
name: rag-debugging
description: Root-cause analysis for wrong, odd or refused answers of the AIP RAG chatbot (solutions/rag). Use when a user reports a bad answer, a repeated/stale answer, a greeting answered with document content, a hallucinated number, a missed follow-up, or any "sao lại trả lời như này". Traces the turn through query analysis → retrieval → rerank → gate → context → generation → verification and names the failing stage before any code change.
---

# RAG Debugging & Root Cause Analysis

Mục tiêu: **không sửa code theo kiểu đoán**. Mọi lỗi hành vi phải được quy về một bước trước khi sửa.

## 1. Lấy bằng chứng

Ưu tiên theo thứ tự sau:

1. **Trace của lượt đó.** Mỗi câu trả lời có `trace_id` (header `X-Trace-ID`, `telemetry.trace_id`, hoặc event `done` khi stream).
   ```
   GET /v1/rag/traces/{trace_id}          # toàn bộ các stage + chẩn đoán
   GET /v1/rag/traces?session_id=<id>     # cả phiên (lỗi multi-turn)
   GET /v1/rag/traces?feedback=negative   # các lượt bị chê
   GET /v1/rag/eval/index-snapshot        # chunk đã index (để phân biệt lỗi ingestion và retrieval)
   ```
   Các endpoint này chỉ dành cho admin: `X-AIP-Runtime-Token` + `X-User-Role: admin`, hoặc `AIP_ADMIN_API_KEY`. RAG chạy trên port 8010, gateway :8000 proxy `/v1/rag`.
2. **Gọi lại API** với cùng `session_id` hoặc cùng history (`POST /v1/rag/chat`) để tái hiện lỗi.
3. Report hoặc export hội thoại do người dùng gửi chỉ là triệu chứng, chưa phải bằng chứng.

## 2. Đọc trace theo thứ tự stage

Trace do `application/components/run_trace.py` ghi. Phần quy lỗi nằm ở `application/components/trace_diagnosis.py` (`STAGE_ORDER`).

| Stage trong trace | Cần xem | Lỗi điển hình |
|---|---|---|
| `query_analysis` | `intent`, `standalone_query`, `new_topic`, `focus` | Analyzer viết lại câu chào hoặc câu phàn nàn thành câu hỏi trước đó; sai intent |
| `route` | `support` / `clarification` / `multihop` / document | Câu hỏi tài liệu bị coi là chit-chat, hoặc ngược lại |
| `retrieval` | ứng viên dense + sparse, có chứa căn cứ không | Có trong index nhưng không được lấy ra |
| `rerank` | điểm, thứ hạng của chunk căn cứ | Bị đẩy xuống dưới top-k |
| `gate` | quyết định của evidence gate | Từ chối dù có căn cứ, hoặc cho qua dù không có |
| `context` | các passage đưa vào prompt | Căn cứ bị rơi khi fit window |
| `generation` / `verification` / `correction` | raw answer, các câu bị cắt | Model bịa; verifier cắt mất câu đúng |

Quy tắc: **stage đầu tiên làm mất căn cứ là stage có lỗi**. Đừng sửa prompt nếu căn cứ đã mất ngay ở retrieval.

## 3. Bản đồ code theo stage

| Stage | File chính |
|---|---|
| Lập kế hoạch lượt, routing | `application/use_cases/chat_use_case.py` → `_plan_turn`, `_plan_support_turn`, `_plan_document_turn` |
| Phân tích câu hỏi và intent | `application/components/query_analyzer.py` (`Intent`, một lần gọi LLM ra JSON) |
| Rewrite, HyDE, decompose | `query_rewriter.py`, `hyde_generator.py`, `query_decomposer.py` |
| Truy xuất | `infrastructure/adapters/qdrant_adapter.py` (`search_dense`, `search_sparse_keywords`, `search`) |
| Rerank | `infrastructure/adapters/reranker_adapter.py`, `application/components/reranker.py` |
| Gate, bằng chứng từ vựng | `lexical_evidence.py`, các phần gate trong `chat_use_case.py` |
| Chọn context | `context_selector.py` (`select_adaptive_context`) |
| Prompt | `prompt_builder.py` |
| Hậu xử lý, kiểm chứng | `answer_postprocessor.py`, `answer_verifier.py` |
| Cache câu trả lời | `_cache_lookup` trong `chat_use_case.py`, `redis_cache_adapter.py` (key = standalone query) |

## 4. Các mẫu lỗi đã biết, kiểm tra trước

- **Câu chào hoặc phàn nàn ("HI", "mày trả lời gì vậy") lại nhận câu trả lời của câu trước:**
  thường do `standalone_query` được analyzer viết lại thành câu hỏi trước, sau đó intent là document, nên pipeline truy xuất lại tài liệu cũ. Cache theo standalone query còn có thể trả nguyên câu trả lời cũ. Kiểm tra `intent` và `standalone_query` trong stage `query_analysis` và xem có `cache hit` không. Sửa ở analyzer (prompt hoặc ràng buộc intent GREETING/FEEDBACK) hoặc ở điều kiện dùng cache, **không** sửa bằng danh sách từ chào.
- **Câu follow-up mất ngữ cảnh:** `new_topic` bị đặt sai, hoặc `generation_history` rỗng.
- **Bịa số liệu:** xem `numeric_tables.py` / `table_rows.py`, và context có chứa con số đó không.
- **Liệt kê thiếu ("5 bài viết" bị hiểu thành 5 chủ đề):** xem `wants_list`, `aggregate`, `count_unit` trong flags của analysis, rồi xem context có đủ các mục không.

## 5. Đầu ra bắt buộc trước khi sửa

Viết ngắn gọn:
1. Triệu chứng (input → output sai).
2. Stage có lỗi kèm bằng chứng (trích trace hoặc log).
3. Nguyên nhân gốc ở cấp code (file:line).
4. Hướng sửa, kèm lý do nó tổng quát, không gắn với tài liệu cụ thể.
5. Test sẽ thêm để khóa lỗi (xem skill `rag-production-quality`).

Sau đó chuyển sang skill đúng tầng: `rag-retrieval`, `rag-data-engineering` hoặc `rag-architecture`.
