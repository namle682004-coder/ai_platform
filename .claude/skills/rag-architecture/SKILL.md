---
name: rag-architecture
description: Architecture of the AIP RAG service (solutions/rag, Clean Architecture/DDD) and how it plugs into the AIP platform (gateway proxy, model aliases, gRPC runtimes, RabbitMQ worker, Mongo/Redis/Qdrant/MinIO). Use before adding or reordering a pipeline stage, changing routing/intents, multi-turn handling, ports/adapters, caching or data contracts, or when a fix spans several layers.
---

# RAG Architecture

## Phân tầng (`solutions/rag`)

```
domain/            entities.py, ports.py (VectorStorePort, LLMPort, RerankerPort, CachePort, TraceStorePort…), exceptions.py
application/
  use_cases/       chat_use_case.py (~3.2k dòng, điều phối lượt chat), ingestion_use_case.py,
                   knowledge_use_case.py (upload/QA/xóa), session_use_case.py
  components/      các bước pipeline thuần (analyzer, rewriter, chunker, context_selector, prompt_builder,
                   answer_verifier, postprocessor, run_trace, trace_diagnosis…)
infrastructure/    adapters (qdrant, embedding, llm, reranker, redis, rabbitmq, storage, model_registry, runtime_guard),
                   parsers, repositories (Mongo), observability
interfaces/        api (chat_router, knowledge_router, identity, rate_limiter), worker (consumer, publisher)
config.py          RagSolutionSettings, env prefix RAG_*
```

Quy tắc phụ thuộc: `domain` ← `application` ← `infrastructure` / `interfaces`. Component không được import adapter, mọi I/O đi qua port. Có `tests/test_clean_architecture_ports.py` và `test_architecture_srs2.py` kiểm tra điều này.

## Vị trí trong platform

- Client → gateway `:8000` → proxy `/v1/rag`, `/v1/knowledge` → RAG API `:8010`.
- LLM, embedding và rerank được gọi theo **alias** (`chat-general-standard`, `rerank-standard`…) thông qua `model_registry.py`. Alias được phân giải tại gateway hoặc runtime (vLLM/llama-server, gRPC `:50058`). Không hardcode URL model.
- Ingestion chạy bất đồng bộ: upload ghi PENDING → RabbitMQ → worker.
- Lưu trữ: Mongo (documents, sessions, `rag_traces`, tickets), Qdrant (chunks), Redis (cache, rate limit), MinIO (file gốc, ảnh).

## Luồng một lượt chat (`RagChatUseCase`)

`_plan_turn` quyết định `plan.kind`:
1. Khôi phục dấu → `query_analyzer.analyze` (cùng history) → `standalone_query` + `intent`.
2. Intent không phải câu hỏi tài liệu (GREETING, SUPPORT_REQUEST, FEEDBACK, CONTACT_INFO, TICKET_STATUS, OUT_OF_SCOPE) → `_plan_support_turn` trả lời bằng mẫu cố định (`conversation_policy.py`).
   - FEEDBACK khi chưa có câu trả lời nào trong phiên, hoặc OUT_OF_SCOPE khi bật verify, sẽ bị **hạ xuống UNCLEAR hoặc DOCUMENT_QUESTION** để retrieval quyết định.
3. Câu mơ hồ → clarification; câu nhiều bước → multihop; còn lại → `_plan_document_turn` (retrieval, rerank, gate, context).
4. Cache: tra theo `standalone_query` (`_cache_lookup`), nên **sai standalone sẽ dẫn đến cache trả nhầm câu trả lời**.
5. Sinh câu trả lời (stream hoặc không) → post-process (footer nguồn, đánh lại số trích dẫn, ảnh, gợi ý) → verifier → có thể sinh lại.
6. Lưu message, kèm trường `standalone` cho các lượt sau (`_generation_history`).

Lưu ý: còn có `intent_classifier.py` (enum `QueryIntent`, có CHITCHAT) song song với `query_analyzer.Intent`. Trước khi thêm intent mới, xác định rõ lượt đó đi qua bộ nào để không tạo thêm nhánh routing thứ ba.

## Checklist khi thay đổi kiến trúc

1. Vẽ luồng trước và sau (stage nào thêm, bỏ hoặc đổi thứ tự). Kiểm tra trace vẫn ghi đủ stage, vì `trace_diagnosis.STAGE_ORDER` phụ thuộc vào tên stage.
2. Port mới phải có Null adapter (như `NullCacheAdapter`, `NullTraceStore`) để test chạy được offline.
3. Một lần gọi LLM thêm vào đường nóng: ghi rõ tác động latency và hành vi khi timeout (phải degrade an toàn, như analyzer fallback).
4. Đổi schema payload (Qdrant, Mongo, response DTO) thì phải tương thích ngược, hoặc có migration (`migrations/`) và kế hoạch re-index. Frontend `frontend/solutions/rag/index.html` đọc các field của DTO.
5. Đa tenant: mọi truy vấn mới đều phải có `tenant_id` và lọc theo role.
6. Viết thiết kế ngắn (vấn đề, phương án, trade-off) trước khi code nếu thay đổi chạm từ 2 tầng trở lên.
