# Đánh giá chất lượng RAG & cổng go-live

Bộ công cụ này trả lời hai câu hỏi trước mỗi lần phát hành:

1. Chatbot có đạt chuẩn để go-live không (≥ 95%, cùng các điều kiện bắt buộc)?
2. Câu nào sai, và sai ở bước nào của pipeline?

## Ba lớp kiểm soát

| Lớp | Ở đâu | Đo gì |
|---|---|---|
| **Trace từng lượt** (observability) | `solutions/rag/application/components/run_trace.py`, collection Mongo `rag_traces` | Đầu vào và đầu ra của từng bước, gồm query analysis, retrieval, rerank, gate, context, generation, verification, correction, route và kết quả cuối. PII được che khi lưu. |
| **Bộ nghiệm thu offline** (evaluation) | `benchmarks/rag` (`rag_benchmark.cli suite`) | Chạy toàn bộ golden set qua API thật, chấm điểm, quy lỗi về đúng bước, rồi quyết định GO / NO-GO. |
| **Giám sát online** (monitoring) | Prometheus job `aip-rag`, dashboard Grafana "AIP RAG – Chất lượng & Pipeline", alert `aip_rag_quality_alerts` | Tỷ lệ từ chối, câu bị kiểm chứng cắt, sinh lại, latency theo stage, lỗi theo stage. |

### Trace: tìm lỗi nằm ở đâu

Mỗi câu trả lời có một `trace_id`. Giá trị này nằm trong header `X-Trace-ID`, trong `telemetry.trace_id` (non-stream) và trong event `done` (stream). Feedback gửi kèm `trace_id` sẽ được gắn vào trace tương ứng.

```
GET /v1/rag/traces/{trace_id}            # toàn bộ trace + chẩn đoán bước lỗi (nếu có feedback)
GET /v1/rag/traces?feedback=negative     # các lượt bị người dùng chê → hàng đợi review
GET /v1/rag/traces?session_id=…          # cả phiên hội thoại
GET /v1/rag/eval/index-snapshot          # mọi chunk đã index (để biết lỗi do parse/chunk hay retrieval)
```

Các endpoint này chỉ dành cho admin: cần role admin (gọi qua `X-AIP-Runtime-Token` + `X-User-Role: admin`) hoặc `AIP_ADMIN_API_KEY`.

Cấu hình qua biến môi trường:

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `RAG_TRACE_ENABLED` | `true` | Bật/tắt lưu trace |
| `RAG_TRACE_SAMPLE_RATE` | `1.0` | Tỷ lệ lấy mẫu lượt bình thường. Lượt bị từ chối, bị cắt câu, có sinh lại hoặc lỗi luôn được giữ. |
| `RAG_TRACE_RETENTION_DAYS` | `14` | Số ngày lưu trace |
| `RAG_TRACE_REDACT_PII` | `true` | Che PII khi lưu |
| `RAG_TRACE_POOL_TEXT_CHARS` | `600` | Số ký tự giữ lại cho mỗi chunk trong pool |
| `RAG_TRACE_CONTEXT_TEXT_CHARS` | `4000` | Số ký tự giữ lại cho mỗi chunk trong context |

### Quy lỗi về từng bước (`trace_diagnosis.py`)

Khi một câu không đạt, hệ thống lần theo **căn cứ vàng** (các mã bắt buộc hoặc trích dẫn) qua từng bước. Bước đầu tiên làm mất căn cứ là bước bị quy lỗi:

| Bước | Nghĩa là | Thường sửa ở |
|---|---|---|
| `ingestion` | Căn cứ không có trong chunk nào đã index | parser / chunker, rồi re-index |
| `routing` | Câu bị coi là chit-chat/hỗ trợ, không truy xuất tài liệu | query analyzer |
| `retrieval` | Có trong index nhưng không lọt vào ứng viên tìm kiếm | hybrid search, BM25, multi-query |
| `rerank` | Có trong ứng viên nhưng bị xếp dưới top-k | reranker, focus retrieval |
| `gate` | Đã truy xuất được nhưng gate từ chối | ngưỡng gate |
| `context` | Qua gate nhưng không được đưa vào prompt | chọn context, window fitting |
| `verification` | Model viết đúng nhưng bộ kiểm chứng cắt mất câu | answer_verifier |
| `generation` | Prompt đã có căn cứ mà model vẫn trả lời sai hoặc thiếu | prompt, temperature, model |

Báo cáo còn có recall theo từng bước: index → retrieval → rerank@k → context → answer. Recall tụt mạnh ở đâu thì đó là chỗ cần xem trước.

## Quy trình go-live

```bash
# 1. Chuyển bộ test xlsx thành golden JSONL; các câu đã chấm tay trở thành mẫu hiệu chỉnh judge
make rag-eval-import            # RAG_EVAL_XLSX=…  RAG_EVAL_DATASET_CONFIG=benchmarks/rag/configs/datasets/<bộ>.yaml

# 2. Rút ý chính của từng câu (model nháp), đội nghiệm thu duyệt <bộ>.checklist.xlsx rồi nhập lại
make rag-eval-checklist
cd benchmarks/rag/src && python -m rag_benchmark.cli checklist --dataset ../datasets/acceptance/<bộ>.jsonl \
  --import-xlsx ../datasets/acceptance/<bộ>.checklist.xlsx

# 3. Hiệu chỉnh cách chấm với điểm chấm tay
#    (làm lại khi đổi model judge, cách chấm, hoặc sau khi duyệt thêm ý chính)
make rag-eval-calibrate         # cần LLM_JUDGE_URL / LLM_JUDGE_MODEL

# 4. Chạy toàn bộ bộ nghiệm thu qua API rồi đánh giá cổng go-live (exit 1 = NO-GO).
#    Điểm tay của các câu trả lời không đổi được giữ lại (RAG_EVAL_GRADES_FROM, mặc định file calibration).
make rag-eval RAG_EVAL_TENANT=<project_id> \
  RAG_EVAL_HEADERS='--header "X-AIP-Runtime-Token: <token>"' \
  RAG_EVAL_BASELINE=benchmarks/rag/runs/<lần_chạy_trước> \
  RAG_EVAL_GRADES_FROM="benchmarks/rag/datasets/acceptance/<bộ>.calibration.jsonl benchmarks/rag/runs/<lần_chạy_trước>"

# 5. Chấm tay các câu đầu runs/<id>/review.xlsx (cột "Cần người chấm"), điền cột "Chấm tay" (Đạt/Không đạt)
cd benchmarks/rag/src && python -m rag_benchmark.cli import-grades --run ../runs/<id> \
  --grades ../runs/<id>/review.xlsx --gate ../configs/gate.yaml --calibration ../runs/calibration_khung_ai_checklist.json
```

Mỗi lần chạy sinh ra trong `runs/<id>/`:

- `run.json`: commit, hash dataset, model judge, rubric, cấu hình server
- `results.jsonl`
- `summary.json`
- `report.md`
- `gate.json`
- `review.xlsx`
- `traces/<case>/…json`

### Thứ tự ưu tiên khi ra kết luận cho một câu

**Người chấm** (kể cả điểm giữ lại cho câu trả lời không đổi) > **kiểm tra cứng** > **máy chấm đã hiệu chỉnh**.

Các kiểm tra cứng (`--hard-checks`, mặc định theo cách chấm):

- từ chối hoặc chuyển hỗ trợ trong khi tài liệu có đáp án (`wrongly_refused`);
- lỗi hiển thị (`artefacts`);
- tuỳ chọn: thiếu mã bắt buộc (`missing_identifiers`, mặc định của `--grader rubric`), mã ngoài câu hỏi / đáp án (`stray_identifiers`).

Bất kỳ kiểm tra cứng nào bị vi phạm thì câu đó không đạt, máy chấm nói gì cũng vậy.

Hai cách chấm (`--grader`):

- `checklist` (mặc định, dùng được với model nhỏ như Qwen-7B):
  - mỗi câu có tối đa 3 ý chính, lưu trong `<bộ>.checklist.jsonl`;
  - mỗi ý được so khớp trước (mã có mặt, chữ đã chuẩn hoá nằm trong câu trả lời); chỉ khi không quyết được mới hỏi model một câu có / không / mâu thuẫn;
  - câu tài liệu không có thông tin: Đạt khi bot từ chối hoặc chuyển hỗ trợ, quyết bằng code.
- `rubric`: judge chấm cả câu theo **đáp án kỳ vọng** và cột **FAIL nếu**, đối chiếu đoạn tài liệu trong trace. Chỉ dùng với model judge mạnh.

Câu có kết luận dựa vào model, hoặc có mã lạ, được đánh dấu "Cần người chấm" và xếp đầu `review.xlsx`.

- `--judge-votes 3` lấy đa số; khi hòa thì tính là không đạt.
- Kết luận của máy chỉ được tính khi file calibration khớp model, cách chấm, kiểm tra cứng và quy tắc mã, đồng thời đạt hai ngưỡng:
  - mức khớp với chấm tay ≥ 85%;
  - tỷ lệ judge cho đạt sai ≤ 10%.

### Tiêu chí cổng (`configs/gate.yaml`)

| Tiêu chí | Ngưỡng |
|---|---|
| Số câu | ≥ 100 |
| Tỷ lệ đạt toàn bộ | ≥ 95% (báo kèm khoảng tin cậy Wilson 95%) |
| Mỗi nhóm | ≥ 80% |
| Câu bắt buộc (`must_pass_groups`: trích dẫn chính xác, không bịa, thông tin cấm, tên riêng) | 100% |
| Bịa khi tài liệu không có thông tin | 0 |
| Lỗi API | 0 |
| Câu còn chờ chấm | 0 |
| Hồi quy so với lần chạy trước | 0 |
| Latency (p95 ≤ 8s, chữ đầu ≤ 3s) | Hiện chỉ cảnh báo; bật `latency.enforce` khi muốn chặn |

### Thêm bộ test cho tài liệu / khách hàng mới

1. Tạo file `configs/datasets/<tên>.yaml`, ánh xạ tên sheet và tên cột.
2. Khai báo regex cho câu "không có trong tài liệu", danh sách nhóm bắt buộc, và override mã bắt buộc nếu đáp án chỉ nêu mã làm ví dụ.
3. Không sửa code: mọi đặc thù của bộ dữ liệu nằm trong config.

**Khuyến nghị:** giữ một **bộ test mù** (holdout) do đội nghiệm thu tự viết và không dùng khi sửa lỗi. Bộ này chỉ chạy ở vòng cuối, để tránh tình trạng hệ thống chỉ khớp riêng với bộ test đã biết.
