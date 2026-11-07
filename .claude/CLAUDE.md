# AIP – quy tắc làm việc cho Claude Code

AIP là nền tảng AI inference đa tenant. Phần trọng tâm hiện tại là **Enterprise RAG tiếng Việt** (`solutions/rag`).

## Bản đồ nhanh

| Thành phần | Vị trí | Ghi chú |
|---|---|---|
| RAG API | `solutions/rag` (FastAPI, port **8010**, `make dev-rag`) | Gateway :8000 chỉ proxy `/v1/rag` và `/v1/knowledge` sang 8010 |
| RAG worker (ingestion) | `make dev-rag-worker` | Đọc job từ RabbitMQ |
| Gateway / workers / runtimes | `platform/` | gRPC fast-lane, dispatcher, callback |
| Shared kernel | `packages/common` (chunking, retrieval, messaging) | |
| Frontend RAG | `frontend/solutions/rag/index.html` | File đơn rất lớn (~11k dòng) |
| Benchmark / go-live gate | `benchmarks/rag` + `make rag-eval*` | Gate: `benchmarks/rag/configs/gate.yaml` |
| Hạ tầng | Mongo, Redis, RabbitMQ, MinIO, Qdrant | `make dev-env` |

## Đọc trước tiên

**Trước khi viết hoặc sửa bất kỳ code RAG nào, nạp skill `rag-quality-protocol`** (ma trận bao phủ `coverage-matrix.md`, nguyên tắc sửa theo loại, các bất biến chống bịa, definition of done). Sau đó mới nạp skill theo tầng.

## Quy trình bắt buộc khi sửa RAG

**Audit → Baseline → Root cause → Implement → Evaluate → Regression**

1. **Audit**: đọc đúng đoạn code liên quan. Không sửa khi chưa biết lượt đó đi qua route nào.
2. **Baseline**: lấy trace hoặc chạy lại case lỗi trước khi sửa, để có số liệu "trước".
3. **Root cause**: quy lỗi về **một** bước trong `ingestion → routing → retrieval → rerank → gate → context → verification → generation`. Bước đầu tiên làm mất căn cứ là bước có lỗi.
4. **Implement**: sửa đúng tầng bị lỗi, càng nhỏ càng tốt.
5. **Evaluate**: thêm unit test tái hiện lỗi và chạy `make rag-eval-test`.
6. **Regression**: chạy test liên quan. Nếu thay đổi chạm tới retrieval, prompt hoặc gate thì so sánh với baseline (`make rag-eval … RAG_EVAL_BASELINE=…`).

## Skill nào dùng khi nào

| Tình huống | Skill |
|---|---|
| Câu trả lời sai hoặc lạ, cần biết vì sao | `rag-debugging` (luôn bắt đầu từ đây với bug hành vi) |
| Upload, parse, chunk, trùng tài liệu, index | `rag-data-engineering` |
| Tìm thiếu hoặc sai passage, rerank, HyDE, query rewrite | `rag-retrieval` |
| Đo chất lượng, golden set, go-live gate | `rag-evaluation` |
| Thay đổi kiến trúc hoặc luồng, thêm bước pipeline | `rag-architecture` |
| Test, bảo mật tenant, hiệu năng, deploy | `rag-production-quality` |

Mỗi lần chỉ nạp skill cần cho giai đoạn hiện tại, không nạp tất cả.

## Nguyên tắc cứng

- **Không hardcode từ khóa hoặc regex theo tài liệu cụ thể.** Đây là SaaS đa tenant. Sửa lỗi theo cách tổng quát (phân tích bằng LLM, thống kê passage, cấu hình tenant), không dựa vào từ có trong một bộ tài liệu.
- Không đổi kiến trúc, dependency hay schema Qdrant/Mongo khi chưa đánh giá tác động. Đổi chunking hoặc embedding thì phải re-index.
- Cách ly tenant (`tenant_id`, `allowed_roles`) không bao giờ được nới lỏng chỉ để làm test qua.
- File test đặt ở `tests/` (pytest, chạy với `PYTHONPATH` như trong `make test`).
- Lint: `make lint` (ruff).
