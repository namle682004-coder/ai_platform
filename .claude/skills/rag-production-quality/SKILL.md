---
name: rag-production-quality
description: Ship-readiness for AIP RAG changes — writing regression tests in tests/, running the right pytest subset and ruff, tenant/role isolation and auth checks, PII, rate limits and overload protection, latency budgets, and deploying to the internal server. Use after implementing any RAG fix, before committing, or when touching security, performance or deployment.
---

# RAG Production Quality & Regression

Mục tiêu: sửa lỗi này không được làm phát sinh lỗi khác.

## 1. Test hồi quy cho mỗi bug

- Mỗi bug sửa xong phải có ít nhất một test trong `tests/` tái hiện đúng input đã gây lỗi. Đặt tên theo hành vi, ví dụ `test_greeting_after_document_answer_is_not_retrieved`.
- Test tầng component: gọi trực tiếp hàm thuần (xem cách viết trong `tests/test_rag_quality_fixes.py`, dùng `_chunk(...)` giả).
- Test tầng use case: thay LLM, vector store, reranker bằng fake hoặc Null adapter. Không gọi mạng hay GPU trong unit test.
- Bug phụ thuộc chất lượng model: thêm case vào dataset benchmark (skill `rag-evaluation`), vì unit test không bắt được loại lỗi này.

## 2. Chạy test

```bash
# Nhanh: phần RAG offline
make rag-eval-test
PYTHONPATH=.:packages/common:packages/contracts ./venv/bin/pytest -q tests/test_rag_*.py tests/test_answer_verification.py

# Đầy đủ trước khi merge
make test
make lint            # ruff check platform/ solutions/ packages/ tests/
```

Báo kết quả đúng như thực tế: test nào fail thì dán output. Không skip hay xóa test để cho qua.

## 3. Checklist bảo mật và đa tenant

- [ ] Mọi truy vấn Qdrant và Mongo đều lọc theo `tenant_id` (`normalize_tenant_id`) và `allowed_roles`.
- [ ] Endpoint admin (`/traces`, `/eval/index-snapshot`, `/tickets`, `/cache/clear`) vẫn yêu cầu role admin.
- [ ] Identity: `interfaces/api/identity.py`. Ở production bắt buộc `AIP_RUNTIME_TOKEN`; `RAG_TRUST_IDENTITY_HEADERS` chỉ bật khi đứng sau gateway.
- [ ] URL media có chữ ký HMAC (`media_assets.py`). Không trả về URL MinIO thô.
- [ ] PII được che trong trace (`RAG_TRACE_REDACT_PII`) và khi ingestion.
- [ ] Cache key bao gồm tenant và role. Không để câu trả lời của tenant này lọt sang tenant khác.
- Test liên quan: `test_security.py`, `test_tenant_id_consistency.py`, `test_pii_sanitization.py`, `test_rag_gateway_proxy.py`.

## 4. Hiệu năng và ổn định

**Tiêu chuẩn hạ tầng và cổng server: [infra-standard.md](infra-standard.md).** Sau mỗi deploy chạy `deploy/server/server_gate.sh` (phải PASS); khi chưa có server diễn tập bằng `scripts/loadtest_local.sh`.


- Giới hạn đồng thời theo runtime (`rerank_max_concurrent`, các giới hạn LLM trong `config.py`), `runtime_guard.py`, `rate_limiter.py`. Test liên quan: `test_rag_overload_protection.py`, `test_rag_stability.py`.
- Mỗi lần gọi LLM hoặc rerank thêm vào đường nóng cần đo latency. Mục tiêu trong gate: p95 tổng ≤ 8s, TTFT ≤ 3s.
- Tải thử: `scripts/load_test_rag.py`.
- Mọi lỗi từ runtime phải degrade an toàn (trả lỗi có kiểm soát hoặc fallback), không làm treo stream.

## 5. Trước khi commit hoặc deploy

1. `git diff` chỉ chứa thay đổi liên quan. Không commit file xlsx hay md nháp ở thư mục gốc.
2. Test và lint đã pass. Nếu chạm retrieval, prompt hoặc gate thì phải có kết quả benchmark so với baseline.
3. Commit message theo kiểu đang dùng: `fix(rag): …` / `feat(rag): …`.
4. Deploy lên server nội bộ: `make deploy-server [REF=<commit>]` (`scripts/deploy_server.sh`, host `msp`, user không có sudo không mật khẩu). Chỉ deploy khi người dùng yêu cầu.
5. Nếu thay đổi chunking hoặc embedding: ghi rõ cần re-index và chạy re-index trên server.
