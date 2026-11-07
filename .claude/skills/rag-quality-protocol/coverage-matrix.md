# Ma trận bao phủ AIP RAG

Cập nhật: 2026-11-06. Mỗi khi sửa hoặc đo thì cập nhật ô tương ứng (trạng thái, số đo, ngày, nguồn số đo).

Ký hiệu trạng thái: **Đo** (có benchmark, ghi tỷ lệ) · **Test** (có unit test, chưa có benchmark) · **Chưa đo** (có route nhưng chưa có test hay benchmark) · **Hổng** (lỗi đã biết hoặc chưa có route) · **?** (chưa xác minh)

## Dạng dữ liệu

| Mã | Dạng | Ví dụ | Parser |
|---|---|---|---|
| D1 | Văn bản tự do (bài viết, tin tức) | Phần A/B bản tin | docx/pdf/txt |
| D2 | Văn bản quy phạm, khung có mã | Khung nội dung GD AI (`10.C2.MR1`), quy chế chương/điều | docx/pdf |
| D3 | Bảng thống kê (có cột số, tiêu đề gộp, dòng Tổng) | PHẦN C bản tin | docx/pdf table → markdown rows |
| D4 | Danh sách mục dài (không phải bảng) | danh sách tiêu đề, gạch đầu dòng | docx/pdf |
| D5 | Bảng tính | xlsx nhiều sheet, csv | `excel_parser.py` (xlsx **bị chặn khi upload**), csv qua text |
| D6 | PDF scan / ảnh chụp văn bản | | ? (OCR chưa xác minh trong ingestion) |
| D7 | Ảnh, biểu đồ trong tài liệu | ảnh minh họa bản tin, ảnh chụp màn hình từng bước HDSD | ảnh được lưu; trong câu trả lời, code đặt mỗi ảnh **dưới bước/đoạn nó minh họa** (theo số bước, không có thì theo câu đứng trước ảnh — `media_assets.interleave_inline_images`); ảnh không khớp dòng nào → khối cuối. Nội dung **bên trong** ảnh chưa được đọc |
| D8 | Nguồn kết nối trực tiếp: bản ghi API JSON, trang web nội bộ (+ file được liên kết) | API bài đăng MXH (kiểu fbx_runner), cổng thông tin nội bộ | connector (`CONNECTORS.md`): bản ghi → bảng markdown theo partition (vào D3/kho bảng); HTML → markdown, bảng gộp ô → `table_grid` |

## Loại câu hỏi

| Mã | Loại | Route chính |
|---|---|---|
| Q1 | Tra cứu một sự kiện | `generate` (hybrid + rerank + gate) |
| Q2 | Đếm / tổng / lớn nhất / nhỏ nhất / xếp hạng | `table_query` (kho bảng, tính bằng code) → `numeric` |
| Q3 | Liệt kê toàn bộ theo điều kiện | `table_query` (bảng: lọc theo cột, mọi tài liệu cùng mẫu) → `structured` (bảng có mã) → `generate` (D4) |
| Q4 | So sánh / tổng hợp nhiều phần | `generate` (compare) / `multihop` |
| Q5 | Nhiều điều kiện / rẽ nhánh | `generate` / `structured` |
| Q6 | Hỏi nối tiếp (kế thừa ngữ cảnh) | query analyzer → mọi route |
| Q7 | Đính chính / phàn nàn / chào hỏi | query analyzer → `support` (feedback, greeting) |
| Q8 | Không có trong tài liệu | evidence gate → `gate_refusal` |

## Ma trận

| | Q1 Tra cứu | Q2 Đếm/tính | Q3 Liệt kê đủ | Q4 So sánh | Q5 Nhiều ĐK | Q6 Nối tiếp | Q7 Đính chính | Q8 Không có |
|---|---|---|---|---|---|---|---|---|
| **D1 Văn bản** | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Hổng (H3) | Chưa đo |
| **D2 Khung mã** | Đo¹ | Đo¹ | Đo¹ | Đo¹ (G19 40%) | Đo¹ (G09 0%) | Đo¹ (G08 60%) | Đo¹ (G20 60%) | Đo¹ (G14 60%) |
| **D3 Bảng TK** | Chưa đo | **Hổng (H1, H2)** | **Hổng (H1)** | Chưa đo | Chưa đo | Hổng (H3) | Hổng (H3) | Chưa đo |
| **D4 Danh sách** | Chưa đo | Chưa đo | ? | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Chưa đo |
| **D5 Bảng tính** | **Hổng (H4)** | Hổng (H4) | Hổng (H4) | Hổng (H4) | Hổng (H4) | — | — | — |
| **D6 Scan** | Test (OCR 85% câu, căn cứ 4/4) | Chưa đo | Chưa đo | Chưa đo | Chưa đo | — | — | Chưa đo |
| **D7 Ảnh** | Test (ảnh kèm câu trả lời) | — | — | — | — | — | — | — |

¹ Bộ `khung_ai_v2` (151 câu), lần chạy `iter5_khung_ai_20261106`: tổng 54.3%; judge Qwen2.5-7B Q4, còn 120 câu cần người chấm. Số đo này **chỉ** áp dụng cho D2.

## Lỗi hổng đã biết (theo loại)

| Mã | Loại lỗi | Bằng chứng | Tầng | Trạng thái |
|---|---|---|---|---|
| H1 | **Bảng có tiêu đề gộp nhiều tầng bị làm phẳng sai**: hàng tiêu đề thứ 2 ("Tích cực / Tiêu cực / Trung tính" dưới "Sắc thái") chỉ nằm ở chunk đầu; các chunk sau mang tiêu đề `Sắc thái, "", ""` nên route không biết cột nào là cột nào | Bản tin `doc_7c52f38af4f3`: 8 chunk PHẦN C, 7 chunk mất tên cột; bảng thật có 42 dòng (5/3/34) + dòng Tổng | Dữ liệu (parser/chunker bảng) | **Đã sửa** (table_grid dùng chung docx/xlsx/pdf; DQ2 100%) |
| H2 | **Ô gộp dọc bị lặp lại từng dòng** ("Số tin/bài" = 8 lặp 8 lần), cộng vào là ra số sai; dòng "Tổng" lẫn vào dòng dữ liệu | Như trên | Dữ liệu + `numeric` | Chưa sửa |
| H3 | **Câu đính chính bị hiểu thành câu hỏi mới** ("thiểu 22 mà" → "có bao nhiêu mục ít hơn 22?") | Trace tenant `20f3df7e` | Thuật toán (query analyzer) | Chưa sửa (bản sửa "HI" không bắt được ca này) |
| H4 | **Upload chặn xlsx/xls** dù có `ExcelDocumentParser` | `ALLOWED_EXTENSIONS` trong `knowledge_use_case.py` | Dữ liệu | **Đã sửa** (.xlsx; .xls nhị phân cũ không hỗ trợ) |
| H5 | Tài liệu nạp trùng làm số liệu bị nhân đôi (5+5=10) | Tenant `20f3df7e`: 2 bản bản tin, cả 2 được mở rộng toàn văn | Dữ liệu | **Đã sửa** chặn upload mới (SHA-256); bản trùng cũ cần chạy `scripts/backfill_rag_content_hash.py` trên msp |
| H6 | Chào hỏi / phàn nàn bị trả lời lại câu trả lời cũ | Trace phiên `41ba0c1d` | Thuật toán (analyzer) | **Đã sửa** (đường LLM); đường fallback khi LLM timeout vẫn còn |
| H7 | Bot xin ID/mật khẩu UltraViewer, hotline giả `1900-xxxx` | Mặc định trong `config.py` | Cấu hình | **Đã sửa** (mặc định rỗng) |
| H1b | (cùng loại H1) **xlsx: dòng tiêu đề bảng (ô gộp A1:I1) bị coi là header**; header thật chỉ nằm ở chunk đầu → chunk dữ liệu không có tên cột | `TieuChi_DanhGia_XepLoai_DonVi.xlsx`: "ĐV06" và "Điểm tối đa" không cùng chunk (dg233 index check) | Dữ liệu (`excel_parser`/chunker) | **Đã sửa** |
| H1c | (cùng loại H1) **PDF: bảng rộng bị cắt cột**, chỉ còn Mã/Tiêu chí/ĐVT; các cột điểm tách khỏi tiêu chí | `TieuChi_DanhGia_XepLoai_DonVi.pdf` | Dữ liệu (`pdf_parser` table) | **Đã sửa** (ghép theo cột và theo dòng) |
| H8 | **PDF scan không được OCR**: chỉ lưu ảnh trang, 0 chữ; OCR fallback (tesseract) không có trong môi trường, dịch vụ `ocr-server` của platform không được ingestion gọi | `233-ndcp.signed.pdf`: 22 trang, 21 trang 0 ký tự; 4/4 câu ND-* MISSING | Dữ liệu (ingestion → OCR) | **Một phần**: Tesseract best (Dockerfile) 85% khớp nguyên câu, ~99% ký tự; cần OCR mạnh hơn để ≥ 95% |
| H9 | **Tài liệu gộp nhiều văn bản con, mỗi văn bản đánh số Điều riêng** ("Điều 7" có 2 nghĩa); chunk chỉ mang heading "Điều 7" không mang tên văn bản con | `QuyChe_DanhGia_...docx` (Quy chế + Quy định tiêu chí + …) | Dữ liệu (heading_path) + routing (hỏi lại khi mơ hồ) | **Dữ liệu: đã sửa** (cấp heading từ outline level của Word, heading nhiều dòng gộp làm một, heading đoán nằm dưới heading thật). Routing hỏi lại: chưa |
| H10 | (bảng: **đã xử lý** bằng kho bảng – không phụ thuộc ngưỡng; văn bản thường: chưa) **Tài liệu lớn vượt ngưỡng mở rộng toàn văn** (622 chunk > `doc_expansion_max_chunks`=300) → câu liệt kê/đếm trên toàn văn bản chỉ dựa top-k | Quy chế 228k ký tự | Thuật toán (structured index lúc ingest) | Chưa sửa |
| H12 | **Ảnh hướng dẫn tách khỏi bước của nó**: model nhỏ ít khi tự chép thẻ ảnh → mọi ảnh dồn vào khối "Hình ảnh trong tài liệu" cuối câu (phản ánh của DVKH: "chữ riêng, ảnh riêng") | Phiếu khảo sát chatbot DVKH, ca cài Plugin ký số | Generation → post-process | **Đã sửa 07/11** (code đặt ảnh dưới bước; stream gửi lại thân có ảnh + nguồn). 6 test (gồm 1 test trọn luồng stream). Chưa đo trên tài liệu HDSD thật |
| H11 | **Hai nguồn mâu thuẫn** (bảng xlsx: "trên 70% nhiệm vụ" vs Quy chế Điều 7: "100% nhiệm vụ") → bot phải nêu cả hai kèm nguồn | dg233 QC-15 | Thuật toán / generation | Chưa đo |

## Bộ benchmark cần có (để mọi ô có số đo)

| Bộ | Tài liệu | Ô phủ | Trạng thái |
|---|---|---|---|
| `khung_ai_v2` | Khung nội dung GD AI | D2 × Q1–Q8 | Có (151 câu) |
| `dg233_v1` | DG233: 24 bản mô tả VTVL (docx bảng), tiêu chí (xlsx + pdf), quy chế (docx 228k ký tự), Nghị định 233 (scan) | D1, D2, D3, D5, D6 × Q1–Q8 (20 ô) | **Có** (49 câu, đáp án lấy từ nguồn gốc). Tầng dữ liệu 2026-11-06: 15/24 kiểm tra đạt (VTVL 8/8, Quy chế 6/6, bảng xlsx/pdf 1/6, scan 0/4). End-to-end: chưa chạy (cần LLM runtime) |
| `ban_tin_mxh` | Bản tin MXH (≥2 số khác ngày) | D1, D3, D4, D7 × Q1–Q8 | Chưa có |
| `bang_tinh` | xlsx nhiều sheet + csv dài | D5 × Q1–Q5 | Chưa có, chờ tài liệu |
| `quy_che` | Văn bản quy định chương/điều/khoản | D2 × Q1, Q4, Q5, Q8 | Chưa có, chờ tài liệu |
| `scan` | PDF scan | D6 | Chưa có, chờ tài liệu |
