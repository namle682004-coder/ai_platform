# Tiêu chuẩn hạ tầng AIP RAG (lab msp và các server sau này)

Mục tiêu: **máy không bao giờ treo**. Quá tải thì từ chối có kiểm soát (429/503 kèm Retry-After), không xếp hàng vô hạn. Thành phần nào vượt bộ nhớ thì chỉ thành phần đó bị khởi động lại, máy vẫn sống.

Công cụ: `deploy/testing/scripts/server_gate.sh` (một lệnh sau mỗi lần deploy, trả PASS/FAIL). Diễn tập không cần GPU: `scripts/loadtest_local.sh` (stack cô lập + runtime giả lập `scripts/stub_runtimes.py`).

## 1. Các lớp bảo vệ bắt buộc

| Lớp | Cơ chế | Ở đâu |
|---|---|---|
| Ứng dụng – cửa vào | Rate limit theo client và toàn cục (429) | `interfaces/api/rate_limiter.py`, `RAG_CHAT_GLOBAL_RATE_LIMIT_PER_MINUTE` |
| Ứng dụng – lượt chat | Giới hạn lượt chat đồng thời; vượt thì 503 ngay | `ChatAdmission`, `RAG_CHAT_MAX_INFLIGHT` |
| Ứng dụng – runtime model | Bulkhead theo số slot runtime báo về (`/props`) + circuit breaker | `infrastructure/adapters/runtime_guard.py`, `RAG_LLM_MAX_CONCURRENT`, `RAG_RUNTIME_QUEUE_TIMEOUT_SECONDS` |
| Ứng dụng – nạp tài liệu | File ≤ 50 MB; OCR ≤ `RAG_OCR_MAX_PAGES` trang/tài liệu, ≤ `RAG_OCR_PAGE_TIMEOUT_SECONDS`/trang; trang bị bỏ qua được ghi lên tài liệu | `knowledge_use_case.py`, `pdf_parser.py` |
| Container | `mem_limit` = `memswap_limit` cho mọi container; `restart: unless-stopped` | `docker-compose.server.yml`, `apply_container_limits.sh` |
| Runtime model | systemd `MemoryMax` + `Restart=always`; `--no-mmap`; `--parallel` = slot | `deploy/onprem/host/models/` |
| Máy chủ | earlyoom (tắt model lớn nhất trước khi máy treo); swap 2 GB; ổ trống ≥ 6 GB trước khi build | `install.sh`, `scripts/deploy_server.sh` |

Quy tắc đồng bộ cấu hình: `RAG_LLM_MAX_CONCURRENT` = `--parallel` của llama-server; `RAG_CHAT_MAX_INFLIGHT` ≤ 3 × số slot.

## 2. Ngân sách tài nguyên (máy 8 GB RAM, GPU 12 GB)

| Thành phần | RAM (cap) | VRAM |
|---|---|---|
| Model chat / embedding / rerank (systemd) | 2 G / 1 G / 1 G | 7B: ~5,7 G; 14B: ~10 G; embed + rerank ~1 G |
| rag-api / rag-worker / gateway | 1 G / 768 M / 512 M | – |
| qdrant / rabbitmq / minio / redis | 1 G / 512 M / 512 M / 256 M | – |
| Hệ điều hành + page cache | phần còn lại (≥ 1,5 G trống khi rảnh) | – |

Đã đo (07/11/2026): OCR 22 trang scan trong worker đỉnh ~247 MB / 768 MB.

## 3. Cổng server (`server_gate.sh`) – ngưỡng

| Pha | Đạt khi |
|---|---|
| 0 preflight | `health.sh` exit ≤ 1: RAM trống ≥ 600 MB, ổ < 95%, earlyoom chạy, 3 runtime model `/health` = 200, mọi container có cap |
| 1 steady (số user = số slot) | ≥ 95% trả lời 200; p95 ≤ `AIP_GATE_MAX_P95` (45 s); TTFT p95 ≤ `AIP_GATE_MAX_TTFT` (15 s); không lỗi ngoài 200/429/503 |
| 2 burst (user = 8 × slot) | Không request nào treo quá 90 s; chỉ 200/429/503; lượt chat đồng thời ≤ giới hạn admission |
| 3 ingestion dưới tải | Tài liệu (docx + xlsx + PDF scan) upload trong lúc có burst chat đều INDEXED; chat vẫn giữ ngưỡng pha 2 |
| 4 postcheck | Không container nào bị OOM-kill / restart; không OOM trong kernel log; runtime model không restart; `health.sh` không critical |

Ngưỡng p95/TTFT là của lab (ưu tiên chất lượng, 1–2 slot). Mục tiêu sản phẩm (gate chất lượng `benchmarks/rag/configs/gate.yaml`): p95 tổng ≤ 8 s, TTFT ≤ 3 s – chỉ đạt được trên server lớn hơn.

## 4. Quy trình mỗi lần deploy

1. `deploy/onprem/host/scripts/disk_report.sh` – ổ trống ≥ 6 GB.
2. `make deploy-server` (tự kiểm tra ổ/RAM trước khi build).
3. `deploy/testing/scripts/server_gate.sh` với `AIP_GATE_DOCS=<thư mục 3 tài liệu thử>` → phải PASS.
4. Re-index nếu đổi parser/chunker: dọn trùng trước, `scripts/reindex_rag_documents.py --apply --delay 2`, theo dõi `health.sh`.
5. Benchmark chất lượng (`make rag-eval …`).

Không PASS ở bước 3 thì không làm bước 4–5.
