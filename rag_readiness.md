# AIP RAG – Mức độ sẵn sàng production theo từng bước

Cập nhật: 06/11/2026 (lần 2, sau các bản sửa ở local). Mỗi con số có nhãn nguồn:
- **[Đo]**: đo trực tiếp (benchmark iter5, cổng dữ liệu, trace, dữ liệu index, phân tích lại trace iter5).
- **[Ước tính]**: suy ra từ bằng chứng gián tiếp; cần đo lại.
- **[Chưa đo]**: chưa có cách đo; phải xây trước khi kết luận.

"Chuẩn production" là mức các sản phẩm như NotebookLM hoặc ChatGPT đạt được trên cùng loại tài liệu: khoảng 99% ở từng bước.

> **Lưu ý quan trọng:** mọi bản sửa trong file này **chưa commit, chưa deploy, chưa re-index**. Các số "Sau sửa" đo ở local (cổng dữ liệu, unit test, chạy lại trace offline), **không phải** điểm end-to-end. Điểm end-to-end vẫn là **54,3%** (iter5) cho tới khi chạy lại benchmark trên server.

---

## 1. Vì sao điểm tổng chỉ khoảng 54%: phép nhân giữa các bước

Một câu trả lời đúng cần **mọi bước** đều đúng. Dùng số đo của bộ Khung AI (iter5, 111 lượt có căn cứ vàng):

| Bước | Tỷ lệ giữ được căn cứ | Nguồn |
|---|---|---|
| Hiểu câu hỏi và chọn đường xử lý | ~0,90 | [Ước tính] từ các nhóm hội thoại G08/G20/G21/G25 (0–60%) |
| Truy xuất + rerank | 0,966 | [Đo] Rerank@k 96,6% |
| Đưa vào context | 0,919 | [Đo] Context recall 91,9% |
| Model 7B viết đúng khi đã có căn cứ | 0,683 | [Đo] 62,8% / 91,9% |
| **Tích các bước** | **≈ 0,55** | khớp với **54,3%** đo được |

### Phân tích lại 69 câu trượt từ trace iter5 [Đo]

| Loại lỗi | Số câu |
|---|---|
| Thiếu ý chính | 44 (64%) |
| Từ chối dù tài liệu có đáp án | 9 (13%) |
| Liệt kê thiếu | 7 (10%) |
| Sai mã / sai chỗ | 4 (6%) |
| Đúng nhưng chỉ ngầm trong mã | 2 (3%) |
| Khác | 3 (4%) |

**80 ý chính bị thiếu nằm ở đâu:**
- **57% đã có trong context, model 7B bỏ qua** → lỗi bước sinh câu trả lời;
- 36% đã truy xuất nhưng không được chọn vào context;
- 6% không truy xuất được.

**8 câu từ chối sai:** cả 8 đều **qua** bước kiểm tra căn cứ, căn cứ đứng hạng 1–2, nhưng **model tự từ chối**.

**Kết luận cho bộ Khung AI:** nút cổ chai là **model 7B** (bỏ ý, tự từ chối), sau đó là việc chọn context còn bỏ sót. Truy xuất **không** phải nguyên nhân chính. Giả thuyết trước đây "context nhiễu gây sai" đã bị **bác bỏ** (xem D2).

**Với bản tin và DG233** (bảng, đếm, liệt kê, nhiều tài liệu, scan) thì điểm mất lớn nhất nằm ở **tầng dữ liệu** và **đường xử lý câu đếm/liệt kê**. Hai phần này đã sửa ở local (xem A và C).

---

## 2. Bảng sẵn sàng theo từng bước

### A. Dữ liệu (lúc nạp tài liệu)

| # | Bước | Trước | **Sau sửa (local)** | Chuẩn | Đạt? | Nguồn / ghi chú |
|---|---|---|---|---|---|---|
| A1 | Đọc chữ DOCX/XLSX/PDF (độ phủ nội dung) | 97,7% | **99,6%** | 99% | ✅ | [Đo] cổng dữ liệu, 56 file DG233 |
| A2 | Bảng đủ tên cột (header nhiều tầng, caption, PDF phân trang) | 82,3% (Excel 0%) | **100%** | 99% | ✅ | [Đo] ~1.840 dòng bảng |
| A3 | PDF scan (OCR) | 0 trang có chữ | **22/22 trang; 85% khớp nguyên câu; ~99% theo ký tự** | 95% câu | ❌ | [Đo] trong image `aip-rag:ocr-test`. Còn lỗi dấu ("chỉ cục", "tôi đa") → cần model OCR tốt hơn |
| A4 | Cấu trúc văn bản (văn bản con, chương, điều) | Breadcrumb sai ở file gộp | **Đúng**: "Điều 7" của Quy chế và của Quy định tách biệt | 99% | ✅ | [Đo] trên quy chế thật |
| A5 | Không trùng tài liệu | 2 nhóm trùng | Chặn upload trùng (SHA-256) | 0 trùng | ⚠️ | [Đo] Dữ liệu trùng cũ trên msp chưa dọn |
| A6 | Kho bảng có cấu trúc (để đếm, liệt kê bằng code) | Không có | **Có**: lưu toàn bộ bảng lúc nạp | Có | ✅ | Code xong; cần **re-index** để có dữ liệu |
| A7 | Nhận file Excel | Bị chặn | **Mở `.xlsx`** | 100% | ✅ | |
| — | **Căn cứ vàng nằm trọn trong 1 chunk** (25 điểm kiểm tra DG233) | 56% | **100%** | 95% | ✅ | [Đo] gồm cả 4 câu Nghị định scan |
| A8 | Nạp trực tiếp từ nguồn của khách (API JSON, website nội bộ) | Chỉ upload tay | **Connector**: đồng bộ theo lịch, chỉ nạp lại phần đổi, xóa khi nguồn xóa | Có | ✅ | [Đo] e2e 26/26 trên stack cô lập với nguồn giả lập (đếm bảng đúng 10/2 → 9/3 sau khi sửa ở nguồn). Chưa thử với nguồn thật |

**Cổng dữ liệu bước 1:** đạt 4/5 chỉ số; chỉ còn **OCR (A3)**.

### B. Hiểu câu hỏi và chọn đường xử lý

| # | Bước | Hiện tại | Đã sửa | Chuẩn | Đạt? | Nguồn |
|---|---|---|---|---|---|---|
| B1 | Phân loại ý định (hỏi / chào / phàn nàn / đính chính) | ~70% với câu hội thoại | Chào và phàn nàn không lặp câu cũ; fallback khi model lỗi không ghép câu trước | 99% | ❓ | [Đo] trace lỗi gốc; bản sửa mới có unit test. "thiểu 22 mà" (đính chính) **chưa sửa** |
| B2 | Viết lại câu hỏi nối tiếp | 60% (G08), 40% (G25) | Giữ đúng chữ người dùng gõ ("voi" ≠ "với") | 99% | ❌ | [Đo] iter5 |
| B3 | Câu cực ngắn / chỉ từ khóa | 0% (G21) | — | 95% | ❌ | [Đo] iter5 |
| B4 | Câu tham chiếu mơ hồ ("Điều 7") | Trả lời một trong hai như thể duy nhất | **Hỏi lại kèm các lựa chọn** | 99% | ✅ local | [Đo] 5/5 trên quy chế thật |

### C. Truy xuất

| # | Bước | Trước | Sau sửa | Chuẩn | Đạt? | Nguồn |
|---|---|---|---|---|---|---|
| C1 | Tìm đúng đoạn cho câu tra cứu | 96,6–98,2% (Khung AI) | BM25 trên DG233: R@10 45% → **95%**, R@20 → **100%** | 99% | ⚠️ gần đạt | [Đo] iter5; BM25 đo lại offline 07/11 (dense/rerank chưa đo) |
| C1b | Tài liệu cùng mẫu (nhiều tài liệu gần giống nhau) | Chunk không mang tên tài liệu, xếp hạng ngẫu nhiên | **Tên tài liệu trong text tìm kiếm** | 99% | ✅ local | [Đo] VT-08 hạng 35 → 6 |
| C2 | **Câu đếm/liệt kê trên bảng của tài liệu lớn** | Chỉ đọc khi ≤ 300 chunk | **Đọc toàn bộ bảng từ kho bảng** | 99% | ✅ local | [Đo] 15/15 câu DG233 + **5/5 câu bản tin** (34 trung tính, 34 tiêu đề) – với kế hoạch truy vấn đúng |
| C3 | **Câu trên nhiều tài liệu cùng mẫu** (ví dụ 24 bản mô tả vị trí) | Tối đa 2 tài liệu | **Đọc cùng mẫu bảng ở mọi tài liệu** | 99% | ✅ local | [Đo] "vị trí nào cần cấp độ 4": đúng 4/4 từ 18 tài liệu |
| C4 | Liệt kê trong **văn bản thường** (không phải bảng) của tài liệu lớn | Chỉ dựa vài đoạn | — | 99% | ❌ | Chưa có giải pháp |
| C5 | **Planner** chuyển câu hỏi thành truy vấn bảng (LLM) | — | — | 95% | ❓ | [Chưa đo] cần LLM thật |

### D. Chọn context

| # | Bước | Hiện tại | Chuẩn | Đạt? | Nguồn |
|---|---|---|---|---|---|
| D1 | Context chứa căn cứ (recall) | 91,9–96,2% | 99% | ❌ | [Đo] iter5 |
| D2 | Context precision | 29–40% | — | **không phải mục tiêu** | [Đo] Thu gọn context làm recall giảm còn 87–92% mà không tăng điểm; lượt có context "sạch" không đạt cao hơn lượt nhiễu. **Không thu gọn** |
| D3 | Context chứa đủ ý chính | 72% ý chính bị thiếu đã có trong context | 99% | ❌ | [Đo] Lấy thêm 16 đoạn: 92% nhưng context dài ×3,6 → chỉ khả thi với model context 12k (A/B ở M1) |

### E. Sinh câu trả lời và kiểm tra

| # | Bước | Hiện tại | Chuẩn | Đạt? | Nguồn |
|---|---|---|---|---|---|
| E1 | Model viết đúng khi đã có căn cứ | **68%** | 98% | ❌ | [Đo] **điểm mất lớn nhất** ở Khung AI: 57% ý thiếu đã nằm trong context |
| E2 | Không đưa mã/số lạ | Phần lớn "mã lạ" là khối gợi ý do code thêm (đúng chủ đề 81%) và hotline giả | ~0 | ⚠️ | [Đo] Hotline giả **đã gỡ**; không phải model bịa |
| E3 | Từ chối khi không có thông tin / không từ chối sai | 60% đúng (G14); 8 câu từ chối sai do model | 99% | ❌ | [Đo] Lỗi ở model, không phải gate |
| E4 | Đếm, cộng, liệt kê đúng | ~30–50% | 99% | ✅ local cho bảng | [Đo] Bảng: tính bằng code, 15/15; văn bản thường: chưa |
| E5 | Nhất quán khi hỏi lại | — | 99% | ❓ | [Chưa đo] Câu bảng giờ do code tính nên nhất quán theo thiết kế |
| E6 | Chữ đầu tiên ≤ 3 giây | p95 7,4 giây | ≤ 3 giây | ❌ | [Đo] Lab ưu tiên chất lượng, chấp nhận chậm |
| E7 | Không xin thông tin nhạy cảm (mật khẩu, ID truy cập) | Mọi tenant bị xin mật khẩu UltraViewer | **Đã gỡ** | 100% | ✅ | Mặc định rỗng |

### F. Đo lường

| # | Bước | Hiện tại | Chuẩn | Đạt? |
|---|---|---|---|---|
| F1 | Độ tin cậy điểm số | 120/151 câu chưa người chấm; judge 7B | Có hiệu chỉnh | ❌ |
| F2 | Bộ test phủ các loại tài liệu | Khung AI (151) + **DG233 (49 câu, 20 ô ma trận)** + cổng dữ liệu (`make rag-data-gate`) | ≥ 3 bộ | ⚠️ thiếu bản tin |
| F3 | Chặn hồi quy | iter1 → iter5: sửa 25, hỏng lại 16 | 0 hồi quy | ❌ chưa chạy lại |
| F4 | Test tự động | **284 test RAG pass** | | ✅ |

---

## 3. Vì sao NotebookLM / ChatGPT gần như tuyệt đối mà AIP thì không

| Yếu tố | NotebookLM / ChatGPT | AIP hiện tại |
|---|---|---|
| Model | Model rất lớn, suy luận mạnh | 7B lượng tử hóa Q4 |
| Context | Hàng trăm nghìn tới 1 triệu token: **đọc cả tài liệu** một lần | Vài nghìn token: chỉ thấy vài đoạn được chọn |
| Đếm, liệt kê | Model đọc hết rồi tự đếm | **Bảng: nay tính bằng code trên toàn bảng** (đã sửa). Văn bản thường: vẫn phụ thuộc vài đoạn |
| Đọc tài liệu | Bộ OCR và đọc layout thương mại | Đã sửa bảng (100%) và có OCR (85% câu) |
| Hiểu hội thoại | Chính model lớn hiểu luôn | Một lần gọi model 7B quyết định nhiều nhánh xử lý |

**Ý nghĩa:** mọi việc model lớn tự làm thì AIP phải làm bằng code. Phần dữ liệu và bảng đã làm xong ở local. Phần còn lại phụ thuộc chủ yếu vào **model** (bỏ ý, tự từ chối, hiểu hội thoại).

## 4. Vì sao như "mở túi mù"

1. **Nhiều nhánh quyết định bởi model 7B và ngưỡng điểm.** Đổi một chữ trong câu hỏi có thể sang nhánh khác.
2. **Dữ liệu hỏng một phần** (lần trúng chunk đủ tên cột, lần trúng chunk mất tên cột). → **Đã sửa ở local.**
3. **Câu đếm/liệt kê do model tự viết từ vài đoạn.** → **Câu trên bảng nay do code tính**, cùng câu hỏi luôn ra cùng kết quả.
4. **Chưa đo độ nhất quán (E5).**

## 5. Vì sao 5 vòng sửa gần như không tăng

1. Sửa theo từng câu lỗi, không theo loại lỗi (16 hồi quy). → Nay có quy trình sửa theo loại, ma trận bao phủ và cổng dữ liệu.
2. Tầng dữ liệu chưa từng được đo. → Nay có `make rag-data-gate`.
3. Thước đo không tin được (120 câu chưa chấm, judge 7B). → **Chưa sửa.**
4. Chỉ đo trên 1 bộ tài liệu. → Đã thêm DG233.
5. **Nút cổ chai của bộ Khung AI là model 7B**, mà 5 vòng sửa không đổi model.

---

## 6. Lộ trình lên ≥ 90–95%

| Giai đoạn | Việc | Trạng thái | Cổng đạt |
|---|---|---|---|
| 1. Dữ liệu | Bảng, heading, cấu trúc văn bản, chống trùng, Excel, OCR | ✅ 4/5 chỉ số; **OCR 85%** | Cổng dữ liệu đạt cho Khung AI, DG233, bản tin |
| 2. Dữ liệu có cấu trúc | Kho bảng; đếm/liệt kê/lọc/tổng bằng code; đọc cùng mẫu ở mọi tài liệu | ✅ code xong (15/15) | ≥ 99% câu bảng **với planner LLM thật** |
| 3. Deploy | Commit, build image, re-index, dọn trùng | ⏳ chờ server | Cổng dữ liệu đạt trên server |
| 4. **Model** | A/B Qwen2.5-7B → Gemma 3 12B → Qwen3-14B, kèm nới context (12k) | ⏳ chờ server | E1 ≥ 90%, E3 ≥ 95% |
| 5. Hội thoại | Đính chính, nối tiếp, câu cực ngắn | ⚠️ một phần | B1–B3 ≥ 95% |
| 6. Đo lường | Chấm tay đủ, judge tách khỏi model trả lời, đo nhất quán, chặn hồi quy | ❌ | Đủ để tin số |

**Đánh giá thẳng:**
- Với các câu **trên bảng** (đếm, liệt kê, lọc, nhiều tài liệu), giai đoạn 1–2 đã đưa phần dữ liệu và tính toán lên khoảng 99% ở local. Điểm thật còn phụ thuộc planner LLM chọn đúng truy vấn (chưa đo).
- Với các câu **tra cứu văn bản** (bộ Khung AI), nút cổ chai còn lại là **model 7B**. Chỉ đổi model ước tính lên khoảng 70–76%; đổi model + nới context + làm xong giai đoạn 5–6 thì **khoảng 90% là khả thi**.
- Các câu **suy luận nhiều bước** với model 12–14B vẫn khó vượt khoảng 80%.

Bước kế tiếp khi server bật: **re-index → A/B model → benchmark Khung AI + DG233**, có số trước/sau cho từng bước.
