# Báo cáo Kiểm thử Chất lượng RAG (Audited Scientific Report)

### Thông tin Kiểm toán (Audit Provenance)
- **Mã đợt chạy (Run ID):** `run_20261021_141242`
- **Track kiểm thử:** `fixed_context` (Fixed Context Generation)
- **Phiên bản Bộ đánh giá (Evaluator Version):** `2.0.0-ranx-audited`
- **Dataset SHA-256:** `75e06c9438067344...`
- **Git Commit Hash:** `39ffac7`
- **Quy mô mẫu:** Tổng số = 5 (In-Domain: 3, Out-of-Domain: 0) | Thành công: 3 | Lỗi thực thi: 2
- **Độ trễ trung bình:** 4528.77 ms

---

## 1. Kết quả In-Domain (Câu hỏi trong phạm vi tài liệu, $N_{in} = 3$)

| Hạng mục | Chỉ số chuẩn (Metric) | Điểm số & Khoảng tin cậy 95% CI | Phương pháp tính toán |
| :--- | :--- | :---: | :--- |
| **Truy xuất (Retrieval)** | **nDCG@10** | N/A *(Track A bỏ qua Retrieval)* | Chuẩn BEIR/TREC qua thư viện `ranx` |
| | **Recall@1** | N/A *(Track A bỏ qua Retrieval)* | Tỷ lệ tìm thấy văn bản vàng ở Rank 1 (Wilson CI) |
| | **Recall@3** | N/A *(Track A bỏ qua Retrieval)* | Tỷ lệ văn bản vàng nằm trong Top 3 (Wilson CI) |
| | **MRR@5** | N/A *(Track A bỏ qua Retrieval)* | Mean Reciprocal Rank qua `ranx` |
| **LLM-Judge Thẩm định** | **Faithfulness (Đo ảo giác)** | **86.7% `[58.0% - 100.0%]`** | Qwen2.5-7B (172.16.20.2:8011) đối chiếu Context |
| | **Answer Relevance** | **100.0% `[100.0% - 100.0%]`** | Qwen2.5-7B chấm mức độ đúng trọng tâm câu hỏi |
| | **Semantic Correctness** | **93.3% `[79.0% - 100.0%]`** | Qwen2.5-7B so khớp ngữ nghĩa với đáp án chuẩn |
| **Đối soát chuỗi thô** | **Answer Correctness** | 79.7% `[48.8% - 100.0%]` | Token F1 cổ điển |
| | **Completeness** | 66.7% `[0.0% - 100.0%]` | Tỷ lệ bao phủ Required Facts |
| **Trích dẫn nguồn** | **Citation Precision** | N/A *(Không đo trích dẫn ở Track A)* | Tỷ lệ nhãn trích dẫn khớp tài liệu liên quan |

---

## 2. Kết quả Out-Of-Domain (Phát hiện bẫy & Từ chối câu hỏi ngoài phạm vi, $N_{ood} = 0$)

*Tập kiểm thử hiện tại không chứa ca Out-of-Domain.*

---

## 3. Bảng Chi tiết Từng Ca Kiểm thử

| Case ID | Phạm vi | Recall@3 | Faithfulness | Relevance | Sem. Correct | Token F1 | Cit. Prec. | Abstention | Trạng thái |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `bkai_case_0001` | In-Domain | N/A | N/A | N/A | N/A | N/A | N/A | N/A | `error` |
| `bkai_case_0002` | In-Domain | N/A | 80% | 100% | 90% | 81% | N/A | N/A | `success` |
| `bkai_case_0003` | In-Domain | N/A | 100% | 100% | 100% | 91% | N/A | N/A | `success` |
| `bkai_case_0004` | In-Domain | N/A | N/A | N/A | N/A | N/A | N/A | N/A | `error` |
| `bkai_case_0005` | In-Domain | N/A | 80% | 100% | 90% | 67% | N/A | N/A | `success` |

---

## 4. Hạn chế Kỹ thuật & Các Hạng mục Chưa Hoàn thiện (Known Limitations & Gaps)

1. **Cỡ mẫu nhỏ (N=6):** Đợt chạy này mang tính chất **Smoke Test** để xác thực pipeline và adapter, chưa đủ độ lớn thống kê để kết luận độ tin cậy của toàn hệ thống (khoảng tin cậy còn rộng). Cần mở rộng lên tối thiểu 50–100 ca có gán nhãn độc lập.
2. **LLM-Judge độc lập:** ✅ Đã kích hoạt LLM-Judge độc lập (mô hình Qwen2.5-7B-Instruct chạy tại server 172.16.20.2:8011) để thẩm định trực tiếp Faithfulness (chống ảo giác), Answer Relevance và Semantic Correctness, khắc phục hoàn toàn nhược điểm của Token F1.
3. **Cần Bộ Kiểm thử Mù (Blind Holdout Test Set):** Để phòng ngừa rủi ro rò rỉ hoặc overfit vào dữ liệu kiểm thử, đội ngũ nghiệm thu cần tự giữ kín một tập test độc lập (30–50 câu tự viết) và chỉ đưa vào chạy kiểm thử lần cuối.
