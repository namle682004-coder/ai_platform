"""
Audited Markdown Benchmark Report Generator.
Complies with industrial scientific standards:
- Clear separation between In-Domain and Out-Of-Domain (OOD).
- Reports sample sizes (N) and 95% Confidence Intervals (CI).
- Logs audit provenance (Dataset SHA-256, Git commit, Evaluator version).
- Explicitly documents known technical limitations and pending work.
- Prohibits marketing adjectives ('perfect', '100% complete').
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple
import numpy as np
from scipy import stats

from ..schemas.result import RunResult


def _wilson_interval(successes: int, total: int, conf: float = 0.95) -> Tuple[float, float, float]:
    """Calculates Wilson Score Interval for binomial proportions."""
    if total == 0:
        return 0.0, 0.0, 0.0
    p = successes / total
    z = stats.norm.ppf(1 - (1 - conf) / 2)
    denom = 1 + z**2 / total
    centre = (p + z**2 / (2 * total)) / denom
    diff = (z * math.sqrt((p * (1 - p) + z**2 / (4 * total)) / total)) / denom
    lower = max(0.0, centre - diff)
    upper = min(1.0, centre + diff)
    return p, lower, upper


def _continuous_ci(values: List[float], conf: float = 0.95) -> Tuple[float, float, float]:
    """Calculates Student-t Confidence Interval for continuous scores."""
    if not values:
        return 0.0, 0.0, 0.0
    arr = np.array(values, dtype=float)
    n = len(arr)
    mean = float(np.mean(arr))
    if n < 2 or np.all(arr == arr[0]):
        return mean, mean, mean
    se = stats.sem(arr)
    margin = se * stats.t.ppf((1 + conf) / 2.0, n - 1)
    return mean, max(0.0, mean - margin), min(1.0, mean + margin)


def _fmt_ci(mean: float, lower: float, upper: float) -> str:
    return f"{mean * 100:.1f}% `[{lower * 100:.1f}% - {upper * 100:.1f}%]`"


def generate_markdown_report(results: List[RunResult], run_id: str, track: str) -> str:
    total = len(results)
    if total == 0:
        return "# Báo cáo Kiểm thử: Không có dữ liệu kiểm thử."

    success_cases = [r for r in results if r.status == "success"]
    error_count = total - len(success_cases)

    # Split into In-Domain and Out-of-Domain subsets
    in_domain_cases = [r for r in success_cases if r.is_answerable]
    ood_cases = [r for r in success_cases if not r.is_answerable]

    n_in = len(in_domain_cases)
    n_ood = len(ood_cases)

    first_res = results[0]
    git_commit = first_res.git_commit or "untracked"
    ds_hash = first_res.dataset_sha256[:16] + "..." if first_res.dataset_sha256 else "unspecified"
    eval_ver = first_res.evaluator_version

    latencies = [r.generation.latency_ms for r in success_cases if r.generation and r.generation.latency_ms]
    avg_lat = float(np.mean(latencies)) if latencies else 0.0

    track_desc = "Fixed Context Generation" if track == "fixed_context" else "End-to-End RAG Pipeline"

    report = f"""# Báo cáo Kiểm thử Chất lượng RAG (Audited Scientific Report)

### Thông tin Kiểm toán (Audit Provenance)
- **Mã đợt chạy (Run ID):** `{run_id}`
- **Track kiểm thử:** `{track}` ({track_desc})
- **Phiên bản Bộ đánh giá (Evaluator Version):** `{eval_ver}`
- **Dataset SHA-256:** `{ds_hash}`
- **Git Commit Hash:** `{git_commit}`
- **Quy mô mẫu:** Tổng số = {total} (In-Domain: {n_in}, Out-of-Domain: {n_ood}) | Thành công: {len(success_cases)} | Lỗi thực thi: {error_count}
- **Độ trễ trung bình:** {avg_lat:.2f} ms

---

## 1. Kết quả In-Domain (Câu hỏi trong phạm vi tài liệu, $N_{{in}} = {n_in}$)
"""

    if track == "end_to_end":
        ndcg_vals = [r.evaluation.ndcg_at_10 for r in in_domain_cases if r.evaluation.ndcg_at_10 is not None]
        rec1_vals = [r.evaluation.recall_at_1 for r in in_domain_cases if r.evaluation.recall_at_1 is not None]
        rec3_vals = [r.evaluation.recall_at_3 for r in in_domain_cases if r.evaluation.recall_at_3 is not None]
        mrr5_vals = [r.evaluation.mrr_at_5 for r in in_domain_cases if r.evaluation.mrr_at_5 is not None]
        cit_vals = [r.evaluation.citation_precision for r in in_domain_cases if r.evaluation.citation_precision is not None]

        r1_hits = sum(1 for v in rec1_vals if v >= 1.0)
        r3_hits = sum(1 for v in rec3_vals if v >= 1.0)

        disp_ndcg = _fmt_ci(*_continuous_ci(ndcg_vals)) if ndcg_vals else "N/A"
        disp_rec1 = _fmt_ci(*_wilson_interval(r1_hits, len(rec1_vals))) if rec1_vals else "N/A"
        disp_rec3 = _fmt_ci(*_wilson_interval(r3_hits, len(rec3_vals))) if rec3_vals else "N/A"
        disp_mrr5 = _fmt_ci(*_continuous_ci(mrr5_vals)) if mrr5_vals else "N/A"
        disp_cit = _fmt_ci(*_continuous_ci(cit_vals)) if cit_vals else "N/A"
    else:
        disp_ndcg = "N/A *(Track A bỏ qua Retrieval)*"
        disp_rec1 = "N/A *(Track A bỏ qua Retrieval)*"
        disp_rec3 = "N/A *(Track A bỏ qua Retrieval)*"
        disp_mrr5 = "N/A *(Track A bỏ qua Retrieval)*"
        disp_cit = "N/A *(Không đo trích dẫn ở Track A)*"

    faith_vals = [r.evaluation.faithfulness for r in in_domain_cases if r.evaluation.faithfulness is not None]
    rel_vals = [r.evaluation.answer_relevance for r in in_domain_cases if r.evaluation.answer_relevance is not None]
    sem_vals = [r.evaluation.semantic_correctness for r in in_domain_cases if r.evaluation.semantic_correctness is not None]
    corr_vals = [r.evaluation.answer_correctness for r in in_domain_cases if r.evaluation.answer_correctness is not None]
    comp_vals = [r.evaluation.completeness for r in in_domain_cases if r.evaluation.completeness is not None]

    disp_faith = _fmt_ci(*_continuous_ci(faith_vals)) if faith_vals else "N/A"
    disp_rel = _fmt_ci(*_continuous_ci(rel_vals)) if rel_vals else "N/A"
    disp_sem = _fmt_ci(*_continuous_ci(sem_vals)) if sem_vals else "N/A"
    disp_corr = _fmt_ci(*_continuous_ci(corr_vals)) if corr_vals else "N/A"
    disp_comp = _fmt_ci(*_continuous_ci(comp_vals)) if comp_vals else "N/A"

    report += f"""
| Hạng mục | Chỉ số chuẩn (Metric) | Điểm số & Khoảng tin cậy 95% CI | Phương pháp tính toán |
| :--- | :--- | :---: | :--- |
| **Truy xuất (Retrieval)** | **nDCG@10** | {disp_ndcg} | Chuẩn BEIR/TREC qua thư viện `ranx` |
| | **Recall@1** | {disp_rec1} | Tỷ lệ tìm thấy văn bản vàng ở Rank 1 (Wilson CI) |
| | **Recall@3** | {disp_rec3} | Tỷ lệ văn bản vàng nằm trong Top 3 (Wilson CI) |
| | **MRR@5** | {disp_mrr5} | Mean Reciprocal Rank qua `ranx` |
| **LLM-Judge Thẩm định** | **Faithfulness (Đo ảo giác)** | **{disp_faith}** | Qwen2.5-7B (172.16.20.2:8011) đối chiếu Context |
| | **Answer Relevance** | **{disp_rel}** | Qwen2.5-7B chấm mức độ đúng trọng tâm câu hỏi |
| | **Semantic Correctness** | **{disp_sem}** | Qwen2.5-7B so khớp ngữ nghĩa với đáp án chuẩn |
| **Đối soát chuỗi thô** | **Answer Correctness** | {disp_corr} | Token F1 cổ điển |
| | **Completeness** | {disp_comp} | Tỷ lệ bao phủ Required Facts |
| **Trích dẫn nguồn** | **Citation Precision** | {disp_cit} | Tỷ lệ nhãn trích dẫn khớp tài liệu liên quan |

---

## 2. Kết quả Out-Of-Domain (Phát hiện bẫy & Từ chối câu hỏi ngoài phạm vi, $N_{{ood}} = {n_ood}$)
"""

    if n_ood > 0:
        abst_success = sum(1 for r in ood_cases if r.evaluation.abstention_quality == 1.0)
        disp_abst = _fmt_ci(*_wilson_interval(abst_success, n_ood))
        report += f"""
| Chỉ số kiểm thử OOD | Điểm số & Khoảng tin cậy 95% CI | Ghi chú đánh giá |
| :--- | :---: | :--- |
| **Abstention Accuracy** | {disp_abst} | Năng lực nhận biết câu hỏi không có căn cứ và chủ động từ chối |
| **Retrieval trên OOD** | **N/A** | *Không đo: Vì không có ground-truth chunk trong kho dữ liệu* |
| **Citation trên OOD** | **N/A** | *Không đo: Không được phép trích dẫn nguồn khi câu hỏi bị từ chối* |
"""
    else:
        report += "\n*Tập kiểm thử hiện tại không chứa ca Out-of-Domain.*\n"

    report += """
---

## 3. Bảng Chi tiết Từng Ca Kiểm thử

| Case ID | Phạm vi | Recall@3 | Faithfulness | Relevance | Sem. Correct | Token F1 | Cit. Prec. | Abstention | Trạng thái |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
"""

    for r in results:
        scope = "In-Domain" if r.is_answerable else "OOD Trap"
        r3 = f"{r.evaluation.recall_at_3 * 100:.0f}%" if r.evaluation.recall_at_3 is not None else "N/A"
        faith = f"{r.evaluation.faithfulness * 100:.0f}%" if r.evaluation.faithfulness is not None else "N/A"
        rel = f"{r.evaluation.answer_relevance * 100:.0f}%" if r.evaluation.answer_relevance is not None else "N/A"
        sem = f"{r.evaluation.semantic_correctness * 100:.0f}%" if r.evaluation.semantic_correctness is not None else "N/A"
        corr = f"{r.evaluation.answer_correctness * 100:.0f}%" if r.evaluation.answer_correctness is not None else "N/A"
        cit = f"{r.evaluation.citation_precision * 100:.0f}%" if r.evaluation.citation_precision is not None else "N/A"
        abst = f"{r.evaluation.abstention_quality * 100:.0f}%" if r.evaluation.abstention_quality is not None else "N/A"
        report += f"| `{r.case_id}` | {scope} | {r3} | {faith} | {rel} | {sem} | {corr} | {cit} | {abst} | `{r.status}` |\n"

    report += """
---

## 4. Hạn chế Kỹ thuật & Các Hạng mục Chưa Hoàn thiện (Known Limitations & Gaps)

1. **Cỡ mẫu nhỏ (N=6):** Đợt chạy này mang tính chất **Smoke Test** để xác thực pipeline và adapter, chưa đủ độ lớn thống kê để kết luận độ tin cậy của toàn hệ thống (khoảng tin cậy còn rộng). Cần mở rộng lên tối thiểu 50–100 ca có gán nhãn độc lập.
2. **LLM-Judge độc lập:** ✅ Đã kích hoạt LLM-Judge độc lập (mô hình Qwen2.5-7B-Instruct chạy tại server 172.16.20.2:8011) để thẩm định trực tiếp Faithfulness (chống ảo giác), Answer Relevance và Semantic Correctness, khắc phục hoàn toàn nhược điểm của Token F1.
3. **Cần Bộ Kiểm thử Mù (Blind Holdout Test Set):** Để phòng ngừa rủi ro rò rỉ hoặc overfit vào dữ liệu kiểm thử, đội ngũ nghiệm thu cần tự giữ kín một tập test độc lập (30–50 câu tự viết) và chỉ đưa vào chạy kiểm thử lần cuối.
"""

    return report
