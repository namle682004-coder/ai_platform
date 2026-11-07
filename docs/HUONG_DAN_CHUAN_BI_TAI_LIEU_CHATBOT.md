# HƯỚNG DẪN CHUẨN BỊ TÀI LIỆU DÀNH CHO CHATBOT AI (AIP RAG)
*Tài liệu hướng dẫn dành cho Bộ phận Dịch vụ Khách hàng (DVKH) & Đơn vị Quản trị nghiệp vụ*

---

## 1. NGUYÊN LÝ HOẠT ĐỘNG CỦA CHATBOT

Chatbot thế hệ mới hoạt động theo công nghệ **RAG (Retrieval-Augmented Generation - Tra cứu kết hợp Tạo sinh có căn cứ)**:
- **Nguyên tắc "Căn cứ tài liệu" (Quote-First):** Chatbot **chỉ trả lời dựa trên nội dung có thật** trong các tài liệu nội bộ đã được nạp vào hệ thống.
- **Không tự suy đoán hoặc bịa đặt:** Nếu tài liệu chưa có thông tin hoặc thông tin mơ hồ, chatbot sẽ thẳng thắn từ chối và hướng dẫn người dùng liên hệ kênh hỗ trợ (Hotline, UltraViewer, Ticket).
- **Quy tắc "Dữ liệu đầu vào chuẩn → Câu trả lời tốt":** Chatbot đọc tài liệu tương tự như một nhân viên mới tiếp nhận tài liệu. Văn bản rõ ràng, cấu trúc mạch lạc, hình ảnh và bảng biểu chuẩn mực giúp chatbot trả lời **đúng và đủ các bước hơn, và hiển thị hình ảnh minh họa ngay dưới bước thao tác tương ứng**. Tài liệu càng rõ ràng thì càng ít câu trả lời sai; mức chính xác thực tế được đo bằng bộ câu hỏi nghiệm thu (mục 7).

---

## 2. CÁC ĐỊNH DẠNG TỆP ĐƯỢC HỖ TRỢ

| Định dạng | Đánh giá | Trường hợp sử dụng tối ưu | Lưu ý quan trọng |
|---|---|---|---|
| **Microsoft Word (`.docx`)** | ⭐⭐⭐ **Khuyên dùng số 1** | Tài liệu Hướng dẫn sử dụng (HDSD), quy trình cài đặt, quy chế, chính sách nghiệp vụ. | Dễ trích xuất cấu trúc đề mục, bảng biểu và hình ảnh minh họa theo từng bước. |
| **Microsoft Excel (`.xlsx`)** | ⭐⭐⭐ **Khuyên dùng số 1** cho tra cứu số liệu & FAQ | Bảng tra cứu mã lỗi, danh bạ hỗ trợ, bảng so sánh tính năng, bộ 100 câu Hỏi – Đáp (FAQ). | Có dòng tiêu đề (header) rõ ràng, hạn chế gộp ô (merge cells) ở phần thân bảng. |
| **Adobe PDF (`.pdf`)** | ⭐⭐ Tốt | Văn bản pháp quy, nghị định, thông tư, tài liệu ban hành chính thức có sẵn. | **Bắt buộc có lớp chữ (Searchable PDF)**. Hạn chế tải file PDF scan mờ hoặc chụp từ camera điện thoại. |

---

## 3. QUY TẮC VÀNG CHO TÀI LIỆU HƯỚNG DẪN THAO TÁC CÓ HÌNH ẢNH (HDSD)

Đây là điểm quan trọng nhất được khách hàng và người dùng quan tâm: **"Chữ và hình ảnh phải đi liền nhau theo từng bước, không để chữ riêng, ảnh gom một đống ở cuối"**.

### 3.1. Chữ và ảnh phải đi liền nhau
- Trong file Word (`.docx`) hoặc PDF, **ảnh chụp màn hình thao tác phải nằm ngay bên dưới câu văn mô tả bước đó**.
- **Không** dồn toàn bộ ảnh xuống cuối trang, cuối chương hoặc phần phụ lục.

✅ **Định dạng chuẩn:**
> **Bước 1: Tải bộ cài đặt Plugin ký số**  
> Người dùng truy cập vào mục *Cài đặt hệ thống*, chọn *Tải Plugin ký số* tương thích với hệ điều hành đang sử dụng.  
> *(Chèn ảnh chụp màn hình nút bấm tải plugin ngay tại đây)*  
> *Hình 1: Giao diện tải bộ cài đặt Plugin*
> 
> **Bước 2: Cài đặt và kích hoạt**  
> Mở tệp vừa tải về, nhấn *Tiếp tục* và chọn *Đồng ý* với các điều khoản sử dụng.  
> *(Chèn ảnh chụp màn hình hộp thoại cài đặt ngay tại đây)*  
> *Hình 2: Hộp thoại kích hoạt Plugin*

❌ **Cần tránh:**
- Mô tả toàn bộ Bước 1, Bước 2, Bước 3 bằng chữ, sau đó để 3 ảnh liên tiếp ở cuối bài mà không rõ ảnh nào thuộc bước nào.

### 3.2. Đánh số bước nhất quán
- Sử dụng các định dạng chuẩn: `Bước 1: ...`, `Bước 2: ...` hoặc `1. ...`, `2. ...`.
- Tiêu đề từng bước nên in đậm để chatbot nhận diện ranh giới giữa các thao tác.

### 3.3. Tránh "chụp ảnh thay cho chữ"
- Toàn bộ nội dung quy định, hướng dẫn, thông báo lỗi phải được **gõ bằng văn bản (text)**.
- **Không chụp ảnh cả đoạn văn bản hoặc chụp ảnh bảng tính** rồi dán vào tài liệu Word, vì chatbot sẽ khó tra cứu nội dung chi tiết bên trong bức ảnh đó. Ảnh chỉ nên dùng để minh họa giao diện, vị trí nút bấm hoặc màn hình thao tác thực tế.

---

## 4. QUY TẮC THIẾT KẾ BẢNG BIỂU (WORD & EXCEL)

Câu hỏi đếm, cộng, liệt kê trên bảng được chatbot tính bằng chương trình (không để AI tự đếm). Để chương trình đọc đúng bảng, bảng biểu cần tuân thủ:

### 4.1. Tiêu đề cột (Header) rõ ràng
- Mỗi cột dữ liệu phải có **tiêu đề duy nhất** ở dòng đầu tiên.
- Tránh để trống tiêu đề cột.

### 4.2. Hạn chế gộp ô (Merge cells) phức tạp
- Tránh gộp ô theo chiều dọc hoặc ngang ở phần thân dữ liệu (nội dung chi tiết).
- Với bảng nhiều tầng tiêu đề (ví dụ: nhóm *Doanh thu* chia thành *Quý 1*, *Quý 2*), hãy đặt tên cột phẳng: `Doanh thu / Quý 1`, `Doanh thu / Quý 2`.

### 4.3. Dòng Tổng cộng
- Dòng tính tổng phải ghi rõ từ khóa: `Tổng cộng` hoặc `Tổng` ở cột đầu tiên, không ghi chung chung hoặc để trống tên.

---

## 5. THUẬT NGỮ, TỪ VIẾT TẮT VÀ MÃ HIỆU

1. **Từ viết tắt:**
   - Khi thuật ngữ xuất hiện lần đầu trong văn bản, hãy mở ngoặc giải thích nghĩa đầy đủ.  
     *Ví dụ: Bảo hiểm xã hội (BHXH), Hóa đơn điện tử (HĐĐT), Chữ ký số (CKS).*
   - Chatbot sẽ tự động thu hoạch các cặp từ viết tắt này vào kho thuật ngữ riêng để khi khách gõ từ viết tắt hay viết đầy đủ, bot đều hiểu như nhau.
2. **Số hiệu nghị định, thông tư, văn bản:**
   - Ghi chính xác và đầy đủ số hiệu văn bản: `Nghị định 123/2020/NĐ-CP`, `Thông tư 78/2021/TT-BTC`, `Mẫu số 01/ĐKTĐ-HĐĐT`.
   - Giúp chatbot trích dẫn nguyên văn căn cứ pháp lý và không bị nhầm lẫn giữa các phiên bản luật.

---

## 6. QUẢN LÝ PHIÊN BẢN & HIỆU LỰC TÀI LIỆU

Khi phần mềm hoặc chính sách được nâng cấp:
1. **Ghi rõ phiên bản trên tài liệu:**  
   *Ví dụ: "Tài liệu HDSD Phần mềm Ký số – Phiên bản 2.0 (Áp dụng từ 01/10/2026)".*
2. **Thay thế tài liệu cũ (Tính năng "Thay bản mới"):**
   - Vào **Thư viện tri thức → Kho tài liệu**, bấm nút **"Thay phiên bản mới" (🔄)** ở dòng tài liệu cũ và chọn file mới. **Không** tải bản mới lên như một tài liệu riêng: khi đó cả hai bản cùng tồn tại và bot có thể trả lời theo bản cũ.
   - Trong lúc bản mới đang được nạp, bot **vẫn dùng bản cũ** (không có khoảng trống). Khi bản mới nạp xong, bản cũ tự chuyển sang trạng thái **SUPERSEDED (Đã thay thế)** và bị loại khỏi tra cứu.
   - Nếu bản mới nạp lỗi (file hỏng, PDF không có chữ…), bản cũ được **giữ nguyên**; sửa file rồi thay lại.

---

## 7. BỘ CÂU HỎI NGHIỆM THU VÀ CÁC CẶP HỎI – ĐÁP

Có **hai việc khác nhau**, đừng gộp làm một:

| | Bộ câu hỏi nghiệm thu | Cặp Hỏi – Đáp nạp vào bot |
|---|---|---|
| Dùng để | **Đo** bot trả lời đúng bao nhiêu % trước khi đưa vào dùng | Bắt bot trả **nguyên văn** một câu trả lời cố định |
| Gửi cho | Đội triển khai AIP (file Excel: câu hỏi + đáp án chuẩn) | Nạp qua tab **Hỏi – Đáp** |
| Ảnh hưởng | Không thay đổi cách bot trả lời | Mọi lần sau hỏi giống thế, bot trả đúng câu đã nạp, **kể cả khi tài liệu đã có thông tin mới hơn** |

⚠️ **Không nạp cả bộ câu nghiệm thu thành Hỏi – Đáp.** Làm vậy thì bot chỉ "chép đáp án" đúng các câu đó, kết quả nghiệm thu không còn đo được chất lượng thật, và các câu trả lời bị đóng đinh, không tự cập nhật theo tài liệu.

Chỉ nạp thành Hỏi – Đáp những câu **cần trả lời cố định**: thông tin liên hệ, chính sách không đổi, câu tài liệu chưa có. Phần lớn nghiệp vụ nên để bot trả lời từ tài liệu, để khi tài liệu cập nhật thì câu trả lời cập nhật theo.

Cách nạp các cặp Hỏi – Đáp từ Excel:

1. Tải file mẫu tại tab **Hỏi – Đáp** trên giao diện: Bấm nút **"Tải file mẫu"** (hoặc tạo file Excel gồm 4 cột).
2. Định dạng các cột trong file Excel:
   - **Cột A (bắt buộc): `Câu hỏi`** – Câu hỏi thường gặp nhất của khách hàng.
   - **Cột B (bắt buộc): `Câu trả lời`** – Câu trả lời chuẩn xác, có thể trình bày theo các bước hoặc có kèm số hotline liên hệ.
   - **Cột C (tùy chọn): `Danh mục`** – Phân loại nhóm (ví dụ: *Hóa đơn điện tử*, *Chữ ký số*, *Cài đặt*, *CSKH*).
   - **Cột D (tùy chọn): `Biến thể câu hỏi`** – Các cách hỏi khác nhau của người dùng, phân tách nhau bởi dấu gạch đứng `|` (Ví dụ: `cai plugin ky so | loi chu ky so | khong ky duoc hoa don`).
3. Tải lên hệ thống:
   - Vào tab **Hỏi – Đáp** > Bấm **"Nhập từ Excel (.xlsx)"** > Chọn file.
   - Hệ thống nhận cột theo **tên tiêu đề** (thứ tự cột không quan trọng) và đưa các cặp vào dùng ngay. Câu hỏi đã có trong kho sẽ được bỏ qua, nên nhập lại cùng một file không tạo bản trùng.

---

## 8. PHÒNG BAN

Nghiệp vụ của từng phòng ban có thể khác nhau (ví dụ Dịch vụ khách hàng và Quản lý dịch vụ xử lý cùng một yêu cầu theo cách khác nhau).

- Khi tải tài liệu lên, điền ô **Phòng ban** (gõ tên phòng; tên đã dùng sẽ được gợi ý). **Để trống** nghĩa là tài liệu **dùng chung** cho mọi phòng.
- Khi dự án có từ 2 phòng ban trở lên, khung chat hiện ô chọn **Phòng ban**. Chọn một phòng thì bot trả lời theo tài liệu **của phòng đó và tài liệu dùng chung**; chọn "Tất cả phòng ban" thì bot dùng mọi tài liệu.
- Đặt tên phòng ban **thống nhất** (cùng một cách viết cho cùng một phòng), vì "DVKH" và "Dịch vụ khách hàng" sẽ được coi là hai phòng khác nhau.

---

## 9. KẾT NỐI THẲNG TÀI LIỆU TRÊN WEBSITE / HỆ THỐNG (KHÔNG CẦN TẢI FILE)

Nếu tài liệu Hướng dẫn sử dụng đã có trên **website nội bộ** hoặc một **hệ thống có API**, bot có thể đọc trực tiếp theo lịch thay vì phải xuất PDF và tải lên từng file:

- Vào **Thư viện tri thức → Nguồn dữ liệu → Thêm nguồn**, nhập địa chỉ website (hoặc API), bấm **Thử kết nối** để xem bot đọc được những gì, rồi **Lưu và đồng bộ**.
- Trang nào được sửa trên website thì bot tự cập nhật ở lần đồng bộ sau; trang bị gỡ khỏi website thì bot tự bỏ.
- Cần cung cấp cho đội triển khai: **địa chỉ** website/API và **cách đăng nhập** (nếu có). Mật khẩu/token do quản trị hệ thống đặt trên máy chủ, không nhập vào màn hình.

---

## 10. CHECKLIST TỰ KIỂM TRA TÀI LIỆU TRƯỚC KHI TẢI LÊN

Trước khi nạp tài liệu vào chatbot, DVKH hãy kiểm tra nhanh bảng sau:

| STT | Tiêu chí kiểm tra | Đạt | Lưu ý |
|---|---|---|---|
| 1 | File là định dạng `.docx`, `.xlsx` hoặc `.pdf` có thể quét chọn và copy chữ được. | ☐ | Tránh PDF scan chỉ có ảnh. |
| 2 | Với tài liệu quy trình: có phân tách `Bước 1: ...`, `Bước 2: ...` rõ ràng. | ☐ | Đầy đủ mọi bước từ đầu đến cuối. |
| 3 | Hình ảnh minh họa nằm ngay dưới bước thao tác tương ứng, có chú thích ảnh. | ☐ | Chữ và ảnh đi liền nhau. |
| 4 | Bảng biểu có tên cột rõ ràng, không gộp ô phức tạp ở phần dữ liệu. | ☐ | Có dòng "Tổng cộng" riêng. |
| 5 | Các từ viết tắt chuyên ngành (BHXH, CKS, HĐĐT...) đã được định nghĩa rõ ràng. | ☐ | Giúp bot nhận diện từ đồng nghĩa. |
| 6 | Nếu là tài liệu sửa đổi/bản mới: đã dùng nút "Thay phiên bản mới" ở dòng tài liệu cũ. | ☐ | Tránh bot dùng nhầm tài liệu cũ. |
| 7 | Đã điền Phòng ban nếu tài liệu chỉ dành cho một phòng (để trống = dùng chung). | ☐ | Tên phòng viết thống nhất. |

---
*Mọi thắc mắc hoặc yêu cầu hỗ trợ định dạng dữ liệu, vui lòng liên hệ đội ngũ Kỹ thuật AIP để được hướng dẫn trực tiếp.*
