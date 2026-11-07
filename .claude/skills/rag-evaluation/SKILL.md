---
name: rag-evaluation
description: Measure AIP RAG answer quality with the in-repo benchmark (benchmarks/rag, rag_benchmark CLI, make rag-eval*) — golden JSONL datasets from xlsx test sheets, checklists, judge calibration, acceptance suite, per-stage recall, baseline comparison and the ≥95% go-live gate. Use to prove a fix improved quality, to add regression cases, or to decide GO/NO-GO.
---

# RAG Evaluation & Benchmarking

Repo **đã có** harness đánh giá riêng. Không cài thêm Ragas hoặc DeepEval để chạy song song: hai bộ chấm sẽ cho hai con số khác nhau và gate không biết tin con số nào. Nếu cần một metric mới, viết nó thành evaluator trong `benchmarks/rag/src/rag_benchmark/evaluators/`.

## Thành phần

| Thành phần | Vị trí |
|---|---|
| CLI | `benchmarks/rag/src/rag_benchmark/cli.py` (gọi qua `$(RAG_BENCH)` trong Makefile) |
| Evaluators | `evaluators/`: `checks.py`, `citation.py`, `retrieval.py`, `stage_metrics.py`, `checklist_judge.py`, `llm_judge.py`, `rubric_judge.py` |
| Gate | `benchmarks/rag/configs/gate.yaml`: ≥100 case, pass ≥ 95%, mỗi nhóm ≥ 80%, must_pass 100%, 0 regression, judge đã hiệu chỉnh (agreement ≥ 0.85) |
| Dataset | `benchmarks/rag/datasets/acceptance/khung_ai_v2*.jsonl`, `datasets/enterprise/` (frozen test có kèm sha256) |
| Kết quả chạy | `benchmarks/rag/runs/<id>/` (gồm `review.xlsx`) |
| Script nhanh dạng xlsx | `scripts/eval_rag_testset.py` (multi-turn "Lượt 1/2", biến thể "(1)(2)") |

## Quy trình

```bash
make rag-eval-test                                   # offline, không cần API: chạy trước tiên
make rag-eval-import RAG_EVAL_XLSX=<file.xlsx>       # xlsx → golden JSONL + mẫu hiệu chỉnh
make rag-eval-checklist                              # model nháp các ý chính → người duyệt .checklist.xlsx
make rag-eval-calibrate                              # cần LLM_JUDGE_URL / LLM_JUDGE_MODEL
make rag-eval RAG_EVAL_TENANT=<project_id> \
  RAG_EVAL_HEADERS='--header "X-AIP-Runtime-Token: <token>"' \
  RAG_EVAL_BASELINE=benchmarks/rag/runs/<lần_trước>  # exit 1 = NO-GO
make rag-gate RAG_EVAL_RUN=benchmarks/rag/runs/<id>  # đánh giá lại gate cho một lần chạy có sẵn
```

`make rag-eval` cần RAG API đang chạy (`make dev-rag`, port 8010) và tenant đã index đúng bộ tài liệu.

## Chứng minh một bản sửa

1. **Baseline**: lần chạy gần nhất trên commit trước khi sửa. Nếu chưa có thì chạy trước khi sửa.
2. Sửa code, rồi chạy lại cùng dataset và cùng tenant, truyền `RAG_EVAL_BASELINE`.
3. Báo cáo: pass rate trước và sau, theo từng nhóm; danh sách case **mới đạt** và **mới hỏng** (`max_regressions: 0`); phân bố lỗi theo stage; latency p95.
4. Một bản sửa làm hỏng bất kỳ case nào từng đạt là chưa xong, kể cả khi tổng điểm tăng.

## Thêm case mới từ bug thật

Mỗi bug người dùng báo (ví dụ chào "HI" sau một câu hỏi tài liệu, phàn nàn "mày trả lời gì vậy") cần thành một case trong dataset:
- multi-turn ghi đủ các lượt;
- ghi kỳ vọng ở dạng **hành vi** (không truy xuất tài liệu, không lặp lại câu trả lời trước, có lời chào hoặc lời xin lỗi), không ghi nguyên văn câu trả lời;
- đánh `must_pass` nếu là lỗi nghiêm trọng.

Không sửa file trong `datasets/enterprise/frozen_test/`: sha256 khóa nội dung các file đó.

## Lưu ý về độ tin cậy

- Verdict ưu tiên theo thứ tự: chấm tay > checks tự động > judge đã hiệu chỉnh.
- Đổi model judge hoặc rubric thì phải hiệu chỉnh lại.
- Bộ dưới 100 case không đủ để kết luận đạt 95%.
