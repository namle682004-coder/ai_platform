# Tiêu chuẩn chất lượng dữ liệu (cổng bước 1)

Bước 2 (thuật toán: routing, retrieval, numeric/structured, generation) **chỉ được bắt đầu khi bộ tài liệu kiểm thử qua cổng này**. Chưa qua thì quay lại sửa tầng dữ liệu; không "đánh giá sơ bộ rồi đi tiếp".

Công cụ đo: `make rag-data-gate` (`benchmarks/rag/src/rag_benchmark/data_audit.py`), ngưỡng trong `benchmarks/rag/configs/data_gate.yaml`. Công cụ chạy **chính parser + chunker của AIP** và so với **trích xuất độc lập** (python-docx, openpyxl, PyMuPDF) của file gốc. Không cần LLM, không cần retrieval.

## Các chỉ số và ngưỡng

| Mã | Chỉ số | Cách đo | Ngưỡng |
|---|---|---|---|
| DQ1 | **Độ phủ nội dung**: chữ của tài liệu gốc có mặt trong các chunk | Recall theo từ (multiset) giữa trích xuất độc lập và tập chunk, từng tài liệu | ≥ 99% mỗi tài liệu có lớp chữ |
| DQ2 | **Gắn nhãn cột của bảng**: mỗi dòng bảng trong chunk có header với tên cột cho **mọi** ô có giá trị; header không phải dòng tiêu đề bảng (caption), không phải tên giả (`Col2`) | Tỷ lệ dòng bảng hợp lệ trên tổng dòng bảng trong mọi chunk | ≥ 99% toàn bộ, 100% mỗi bảng của bộ kiểm thử |
| DQ3 | **Trang scan được OCR**: trang không có lớp chữ phải có chữ OCR trong chunk | Tỷ lệ trang scan có ≥ 200 ký tự OCR | 100% |
| DQ4 | **Độ chính xác OCR** | Tỷ lệ câu chuẩn (đọc tay từ ảnh trang) xuất hiện đúng trong chunk (so khớp sau chuẩn hóa khoảng trắng) | ≥ 95% |
| DQ5 | **Căn cứ vàng trong một chunk**: với mỗi câu của bộ benchmark, có một chunk chứa cả dữ kiện lẫn nhãn của nó (tên cột, tên trường) | `datasets/acceptance/<bộ>.index_checks.json` | ≥ 95% (mục tiêu 100%) |
| DQ6 | **Không trùng tài liệu** trong một tenant | SHA-256 nội dung (`find_duplicate`) | 0 bản trùng |

## Bất biến khi sửa

- Bảng nhiều tầng tiêu đề: header phẳng dạng `Nhóm / Cột` (ví dụ `Sắc thái / Trung tính`), một dòng duy nhất, được chunker lặp lại ở mọi chunk của bảng.
- Dòng tiêu đề bảng (một giá trị trải ngang toàn bảng) là **caption**, không phải header.
- Một sheet hoặc một trang có nhiều bảng thì tách thành nhiều bảng; không nối bảng sau vào bảng trước.
- Ô gộp dọc trong phần dữ liệu được lặp lại ở từng dòng (mỗi dòng tự đủ nghĩa). Việc không cộng trùng các giá trị gộp là trách nhiệm của bước 2 (route `numeric`).
- Bảng bị phân trang theo cột (PDF in từ bảng tính): ghép lại theo vị trí dòng trước khi tạo markdown.
- Sửa parser hoặc chunker thì phải chạy lại cổng cho **toàn bộ** bộ kiểm thử, không chỉ file đang sửa.
