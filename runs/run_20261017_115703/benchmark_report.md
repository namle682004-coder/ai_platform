# Báo cáo Kiểm thử Chất lượng RAG (Audited Scientific Report)

### Thông tin Kiểm toán (Audit Provenance)
- **Mã đợt chạy (Run ID):** `run_20261017_115703`
- **Track kiểm thử:** `end_to_end` (End-to-End RAG Pipeline)
- **Phiên bản Bộ đánh giá (Evaluator Version):** `2.0.0-ranx-audited`
- **Dataset SHA-256:** `92ed2c81ac3522cd...`
- **Git Commit Hash:** `39ffac7`
- **Quy mô mẫu:** Tổng số = 20 (In-Domain: 12, Out-of-Domain: 8) | Thành công: 20 | Lỗi thực thi: 0
- **Độ trễ trung bình:** 13629.14 ms

---

## 1. Kết quả In-Domain (Câu hỏi trong phạm vi tài liệu, $N_{in} = 12$)

| Hạng mục | Chỉ số chuẩn (Metric) | Điểm số & Khoảng tin cậy 95% CI | Phương pháp tính toán |
| :--- | :--- | :---: | :--- |
| **Truy xuất (Retrieval)** | **nDCG@10** | 61.6% `[57.9% - 65.3%]` | Chuẩn BEIR/TREC qua thư viện `ranx` |
| | **Recall@1** | 0.0% `[0.0% - 24.2%]` | Tỷ lệ tìm thấy văn bản vàng ở Rank 1 (Wilson CI) |
| | **Recall@3** | 83.3% `[55.2% - 95.3%]` | Tỷ lệ văn bản vàng nằm trong Top 3 (Wilson CI) |
| | **MRR@5** | 47.9% `[43.3% - 52.5%]` | Mean Reciprocal Rank qua `ranx` |
| **Sinh câu trả lời** | **Answer Correctness** | 43.6% `[29.2% - 58.1%]` | Token F1 so với đáp án vàng |
| | **Completeness** | 65.3% `[40.0% - 90.6%]` | Tỷ lệ bao phủ Required Facts |
| **Trích dẫn nguồn** | **Citation Precision** | 95.8% `[86.7% - 100.0%]` | Tỷ lệ nhãn trích dẫn khớp tài liệu liên quan |

---

## 2. Kết quả Out-Of-Domain (Phát hiện bẫy & Từ chối câu hỏi ngoài phạm vi, $N_{ood} = 8$)

| Chỉ số kiểm thử OOD | Điểm số & Khoảng tin cậy 95% CI | Ghi chú đánh giá |
| :--- | :---: | :--- |
| **Abstention Accuracy** | 37.5% `[13.7% - 69.4%]` | Năng lực nhận biết câu hỏi không có căn cứ và chủ động từ chối |
| **Retrieval trên OOD** | **N/A** | *Không đo: Vì không có ground-truth chunk trong kho dữ liệu* |
| **Citation trên OOD** | **N/A** | *Không đo: Không được phép trích dẫn nguồn khi câu hỏi bị từ chối* |

---

## 3. Bảng Chi tiết Từng Ca Kiểm thử

| Case ID | Phạm vi | Recall@3 | Correctness | Cit. Prec. | Abstention | Trạng thái |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `ent_diplomacy_001` | In-Domain | 100% | 62% | 100% | N/A | `success` |
| `ent_diplomacy_002` | In-Domain | 100% | 73% | 100% | N/A | `success` |
| `ent_diplomacy_003` | In-Domain | 100% | 24% | 100% | N/A | `success` |
| `ent_meeting_004` | In-Domain | 100% | 29% | 100% | N/A | `success` |
| `ent_meeting_005` | In-Domain | 100% | 32% | 100% | N/A | `success` |
| `ent_meeting_006` | In-Domain | 100% | 58% | 100% | N/A | `success` |
| `ent_hr_probation_007` | In-Domain | 100% | 84% | 100% | N/A | `success` |
| `ent_hr_probation_008` | In-Domain | 100% | 32% | 100% | N/A | `success` |
| `ent_hr_probation_009` | In-Domain | 100% | 61% | 100% | N/A | `success` |
| `ent_hr_probation_010` | In-Domain | 0% | 13% | 50% | N/A | `success` |
| `ent_multihop_011` | In-Domain | 50% | 20% | 100% | N/A | `success` |
| `ent_multihop_012` | In-Domain | 100% | 36% | 100% | N/A | `success` |
| `ent_trap_ood_013` | OOD Trap | N/A | N/A | N/A | 100% | `success` |
| `ent_trap_ood_014` | OOD Trap | N/A | N/A | N/A | 100% | `success` |
| `ent_trap_ood_015` | OOD Trap | N/A | N/A | N/A | 0% | `success` |
| `ent_trap_ood_016` | OOD Trap | N/A | N/A | N/A | 0% | `success` |
| `ent_trap_ood_017` | OOD Trap | N/A | N/A | N/A | 100% | `success` |
| `ent_trap_ood_018` | OOD Trap | N/A | N/A | N/A | 0% | `success` |
| `ent_trap_ood_019` | OOD Trap | N/A | N/A | N/A | 0% | `success` |
| `ent_trap_ood_020` | OOD Trap | N/A | N/A | N/A | 0% | `success` |

---

## 4. Hạn chế Kỹ thuật & Các Hạng mục Chưa Hoàn thiện (Known Limitations & Gaps)

1. **Cỡ mẫu nhỏ (N=6):** Đợt chạy này mang tính chất **Smoke Test** để xác thực pipeline và adapter, chưa đủ độ lớn thống kê để kết luận độ tin cậy của toàn hệ thống (khoảng tin cậy còn rộng). Cần mở rộng lên tối thiểu 50–100 ca có gán nhãn độc lập.
2. **Thiếu LLM-Judge độc lập (Ragas/ARES):** Hiện tại hệ thống đang dùng metric đối soát chuỗi (Token F1 & Fact Coverage) do môi trường On-Premise chỉ triển khai 1 mô hình `vllm-engine`. Cần tích hợp mô hình Judge độc lập (khác mô hình sinh) để đo Faithfulness/Relevance sâu hơn.
3. **Cần Bộ Kiểm thử Mù (Blind Holdout Test Set):** Để phòng ngừa rủi ro rò rỉ hoặc overfit vào dữ liệu kiểm thử, đội ngũ nghiệm thu cần tự giữ kín một tập test độc lập (30–50 câu tự viết) và chỉ đưa vào chạy kiểm thử lần cuối.
