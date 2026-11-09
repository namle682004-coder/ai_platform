# Báo cáo Kiểm thử Chất lượng RAG (Audited Scientific Report)

### Thông tin Kiểm toán (Audit Provenance)
- **Mã đợt chạy (Run ID):** `run_20261017_110346`
- **Track kiểm thử:** `end_to_end` (End-to-End RAG Pipeline)
- **Phiên bản Bộ đánh giá (Evaluator Version):** `2.0.0-ranx-audited`
- **Dataset SHA-256:** `28098ded769cdc52...`
- **Git Commit Hash:** `39ffac7`
- **Quy mô mẫu:** Tổng số = 6 (In-Domain: 4, Out-of-Domain: 2) | Thành công: 6 | Lỗi thực thi: 0
- **Độ trễ trung bình:** 5745.01 ms

---

## 1. Kết quả In-Domain (Câu hỏi trong phạm vi tài liệu, $N_{in} = 4$)

| Hạng mục | Chỉ số chuẩn (Metric) | Điểm số & Khoảng tin cậy 95% CI | Phương pháp tính toán |
| :--- | :--- | :---: | :--- |
| **Truy xuất (Retrieval)** | **nDCG@10** | 63.1% `[63.1% - 63.1%]` | Chuẩn BEIR/TREC qua thư viện `ranx` |
| | **Recall@1** | 0.0% `[0.0% - 49.0%]` | Tỷ lệ tìm thấy văn bản vàng ở Rank 1 (Wilson CI) |
| | **Recall@3** | 100.0% `[51.0% - 100.0%]` | Tỷ lệ văn bản vàng nằm trong Top 3 (Wilson CI) |
| | **MRR@5** | 50.0% `[50.0% - 50.0%]` | Mean Reciprocal Rank qua `ranx` |
| **Sinh câu trả lời** | **Answer Correctness** | 52.3% `[11.9% - 92.7%]` | Token F1 so với đáp án vàng |
| | **Completeness** | 87.5% `[47.7% - 100.0%]` | Tỷ lệ bao phủ Required Facts |
| **Trích dẫn nguồn** | **Citation Precision** | 100.0% `[100.0% - 100.0%]` | Tỷ lệ nhãn trích dẫn khớp tài liệu liên quan |

---

## 2. Kết quả Out-Of-Domain (Phát hiện bẫy & Từ chối câu hỏi ngoài phạm vi, $N_{ood} = 2$)

| Chỉ số kiểm thử OOD | Điểm số & Khoảng tin cậy 95% CI | Ghi chú đánh giá |
| :--- | :---: | :--- |
| **Abstention Accuracy** | 100.0% `[34.2% - 100.0%]` | Năng lực nhận biết câu hỏi không có căn cứ và chủ động từ chối |
| **Retrieval trên OOD** | **N/A** | *Không đo: Vì không có ground-truth chunk trong kho dữ liệu* |
| **Citation trên OOD** | **N/A** | *Không đo: Không được phép trích dẫn nguồn khi câu hỏi bị từ chối* |

---

## 3. Bảng Chi tiết Từng Ca Kiểm thử

| Case ID | Phạm vi | Recall@3 | Correctness | Cit. Prec. | Abstention | Trạng thái |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `enterprise_diplomacy_001` | In-Domain | 100% | 73% | 100% | N/A | `success` |
| `enterprise_meeting_002` | In-Domain | 100% | 30% | 100% | N/A | `success` |
| `enterprise_hr_probation_003` | In-Domain | 100% | 76% | 100% | N/A | `success` |
| `enterprise_hr_probation_004` | In-Domain | 100% | 31% | 100% | N/A | `success` |
| `enterprise_trap_ood_005` | OOD Trap | N/A | N/A | N/A | 100% | `success` |
| `enterprise_trap_ood_006` | OOD Trap | N/A | N/A | N/A | 100% | `success` |

---

## 4. Hạn chế Kỹ thuật & Các Hạng mục Chưa Hoàn thiện (Known Limitations & Gaps)

1. **Cỡ mẫu nhỏ (N=6):** Đợt chạy này mang tính chất **Smoke Test** để xác thực pipeline và adapter, chưa đủ độ lớn thống kê để kết luận độ tin cậy của toàn hệ thống (khoảng tin cậy còn rộng). Cần mở rộng lên tối thiểu 50–100 ca có gán nhãn độc lập.
2. **Thiếu LLM-Judge độc lập (Ragas/ARES):** Hiện tại hệ thống đang dùng metric đối soát chuỗi (Token F1 & Fact Coverage) do môi trường On-Premise chỉ triển khai 1 mô hình `vllm-engine`. Cần tích hợp mô hình Judge độc lập (khác mô hình sinh) để đo Faithfulness/Relevance sâu hơn.
3. **Cần Bộ Kiểm thử Mù (Blind Holdout Test Set):** Để phòng ngừa rủi ro rò rỉ hoặc overfit vào dữ liệu kiểm thử, đội ngũ nghiệm thu cần tự giữ kín một tập test độc lập (30–50 câu tự viết) và chỉ đưa vào chạy kiểm thử lần cuối.
