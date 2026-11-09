# Phân tích lỗi RAG Chatbot – Bộ test Khung AI (151 câu)

Nguồn: `Bo_test_Chatbot_KhungAI_v2_KetQua.xlsx`, sheet "Bộ câu hỏi" (chạy ngày 03/11/2026, tenant 20f3df7e…, POST `/v1/rag/chat` stream, top_k 4, ngưỡng 0.65).

**Kết quả: 52 Đạt / 94 Không đạt / 5 chưa chấm (G29) → 35,6%.**

Mỗi câu sai được xếp vào **một nguyên nhân chính**. Một số câu còn dính thêm nguyên nhân phụ, được ghi ở mục "Lỗi phụ".

| # | Nguyên nhân gốc (vị trí trong code) | Số câu |
|---|---|---|
| NN1 | Cổng chống bịa chỉ dựa vào điểm rerank, ngưỡng bị ép lên 0.75 → từ chối dù tài liệu có đáp án | 25 |
| NN2 | Câu hỏi tổng quan/liệt kê chỉ nhận tối đa 4 đoạn → thiếu, sai hoặc từ chối | 22 |
| NN3 | Không đọc được phần đầu văn bản và phần quy ước (chunk 0, chunk "quy ước" gán sai mục) | 12 |
| NN4 | Hỏi nối tiếp: viết lại câu hỏi sai hoặc không viết lại | 12 |
| NN5 | Kênh liên hệ / chuyển người xử lý / phản hồi không có | 9 |
| NN6 | System prompt ép khuôn "Bước 1/2/3", không bắt ghi mã → bịa, thiếu mã, lỗi định dạng | 8 |
| NN7 | Định tuyến sai sang nhánh trò chuyện tự do (bỏ qua RAG) | 3 |
| NN8 | Không có tính năng gợi ý thêm | 3 |
| | **Tổng** | **94** |

> **Đính chính nhận xét trong file Excel.** Báo cáo cho rằng 53 lượt "rerank = 0.0" bị chặn bởi heuristic TRƯỚC KHI tìm kiếm. Code không làm vậy. Vòng tìm kiếm luôn chạy (`chat_use_case._retrieve_and_gate`). `TIER_1_HEURISTIC` và `standalone_shield_activated` chỉ là cờ của bước viết lại câu hỏi, không chặn gì. Giá trị 0.0 có nghĩa là reranker trả về danh sách rỗng: `reranker.filter_candidates` trả `[]` khi điểm cao nhất < 0.20 (`reranker.py:117-119`), sau đó `top_score` bị gán 0.0 (`chat_use_case.py:917`). Vì vậy cần sửa ở **cổng từ chối sau rerank**, không phải ở một bộ lọc trước tìm kiếm.

---

## NN1 – Từ chối dù tài liệu có đáp án (25 câu)

**Câu:** G01-03, G01-05, G02-01, G02-02, G02-03, G02-04, G02-05, G05-03, G06-01, G06-03, G06-05, G07-02, G07-05, G09-03, G10-01, G10-02, G10-04, G10-05, G11-03, G13-05, G21-04, G21-05, G22-04, G24-02, G26-02

**Nguyên nhân trong code:**
1. **Ngưỡng bị ép tối thiểu 0.75.** `chat_use_case._effective_threshold()` trả `max(request.similarity_threshold, CONFIDENCE_GATE_MIN_THRESHOLD)`, trong đó `CONFIDENCE_GATE_MIN_THRESHOLD = 0.75` (`dtos.py:12`). Giao diện gửi 0.65 nhưng ngưỡng thực tế là 0.75. Vì thế các câu có điểm 0.67–0.74 vẫn bị từ chối (G06-02: 0.74, G22-04: 0.73, G23-05: 0.71, G26-02: 0.69, G08-04: 0.69, G21-04: 0.67).
2. **Chỉ dùng một tín hiệu là điểm cross-encoder.** `refused = top_score < threshold` (`chat_use_case.py:918`). bge-reranker cho điểm rất thấp khi so câu hỏi ngắn tiếng Việt với đoạn bảng dài khoảng 800 ký tự. Điều này xảy ra cả khi đoạn chứa **nguyên văn** từ khóa ("overfitting" 0.22, "thiên vị dữ liệu" 0.35, "nông nghiệp", "Luật Dữ liệu"). Code có tìm BM25 song song (`qdrant_adapter.search` hybrid) nhưng kết quả từ khóa **không được dùng khi quyết định từ chối**.
3. **Câu diễn đạt khác, viết tắt, không dấu** (G02, G06, G07): điểm rerank càng thấp hơn. LLM là bên hiểu được các câu này, nhưng không bao giờ được gọi vì bị chặn trước đó.
4. **Câu tiền đề sai** (G10-01/02/04/05): đoạn đúng (ví dụ RAG ở lớp 11) có điểm thấp so với câu hỏi "lớp 10", nên bị từ chối. LLM không có cơ hội đính chính.
5. `filter_candidates` cắt theo "information cliff" (khoảng cách 0.25 / 0.15 / tỉ lệ 0.6). Các đoạn hợp lệ thứ 2–4 bị loại khỏi danh sách.

**Hướng sửa (tổng quát, không theo tài liệu):**
- Bỏ ép 0.75; dùng đúng ngưỡng client gửi.
- Cổng 3 vùng:
  - **Qua:** rerank ≥ ngưỡng **hoặc** bằng chứng từ khóa mạnh. Bằng chứng từ khóa đo bằng tỉ lệ từ khóa hiếm của câu hỏi có trong đoạn, trọng số IDF tính trên chính các đoạn tìm được, không phân biệt dấu.
  - **Xám:** có một phần bằng chứng → gọi LLM kèm lệnh "nếu tài liệu không có thì trả đúng câu từ chối". Code phát hiện câu từ chối đó trước khi stream ra cho người dùng.
  - **Từ chối ngay, không gọi LLM:** không có bằng chứng từ khóa và rerank thấp.
- Gọi reranker với `min_threshold=0`, lấy điểm của mọi ứng viên, rồi tự chọn top_k theo điểm kết hợp rerank + từ khóa.
- **Rủi ro cần theo dõi:** 15 câu G14/G15/G16 hiện đang Đạt nhờ bot từ chối. Phải chạy lại để chắc các câu này không chuyển sang bịa.

## NN2 – Câu hỏi tổng quan / liệt kê thiếu, sai hoặc bị từ chối (22 câu)

**Câu:** G04-01, G04-02, G04-03, G04-04, G09-01, G09-02, G09-04, G09-05, G17-03, G19-02, G19-03, G19-04, G19-05, G22-02, G23-01, G23-02, G24-01, G24-03, G24-05, G25-05, G27-01, G27-03

**Nguyên nhân trong code:**
1. **Tối đa 4 đoạn vào prompt.** `target_top_k = routing.adaptive_top_k or request.top_k` (= 4), rồi tiếp tục bị cắt bởi information cliff. Riêng phần LỚP 10 đã có 6 đoạn, LỚP 12 có 7 đoạn, chủ đề D2 trải trên 4 đoạn của 3 lớp. Hệ quả: chỉ trả 2–6 trên 10–11 chủ đề (G04, G22-02), bỏ sót lớp (G19-05, G24-03), hoặc khẳng định sai "tài liệu không có" (G09-02, G09-04, G09-05).
2. **Từ khóa "toàn bộ", "tổng quan" kích hoạt map-reduce** (`_resolve_combine_strategy`). Ở pha map, từng đoạn trả `KHÔNG_CÓ_THÔNG_TIN_LIÊN_QUAN`, nên kết quả là câu từ chối (G23-01: status success nhưng nội dung là câu từ chối).
3. Câu tổng hợp nhiều lớp hoặc nhiều ý có điểm rerank thấp nên rơi vào NN1 (G17-03, G19-02/03/04, G23-02, G24-01/05, G25-05).
4. Prompt không yêu cầu "rà soát tất cả các đoạn, liệt kê đầy đủ, đúng thứ tự tài liệu" (G27-01 bỏ 12.D2.MR3 dù nằm cùng đoạn; G09-01 thiếu MR).

**Đã sửa (không dùng từ khóa):**
- **Adaptive top-k theo phân bố điểm**: giữ mọi đoạn có điểm ≥ 60% đoạn tốt nhất (45% khi bộ phân tích LLM báo câu cần liệt kê đầy đủ), trong ngân sách ký tự. Câu cụ thể chỉ giữ 1–2 đoạn trội; câu tổng quan, khi cả phần khớp ngang nhau, giữ cả phần.
- Đọc **toàn bộ chunk của tài liệu đứng đầu** (scroll Qdrant theo `doc_id`) để phần được hỏi không bị thiếu đoạn. Ngữ cảnh được xếp theo thứ tự trong tài liệu.
- Chế độ `auto` không tự bật map-reduce theo từ khóa nữa.
- Prompt thêm quy tắc "liệt kê đầy đủ, đúng thứ tự, không khẳng định 'không có' khi chưa rà hết".

## NN3 – Không đọc được phần đầu văn bản và phần quy ước (12 câu)

**Câu:** G03-04, G04-05, G05-04, G05-05, G06-02, G11-01, G12-05, G13-01, G23-05, G27-05, G30-02, G30-05

**Nguyên nhân trong code:**
1. Chunk 0 chứa tên văn bản, số hiệu, ngày và dòng "Trích QĐ…". Các câu "cơ quan nào ban hành", "ngày nào", "số mấy", "tên đầy đủ" không trùng chữ với chunk này nên điểm rerank rất thấp → bị từ chối (NN1).
2. **Chunker gán sai mục.** Dòng `* Quy ước mã hoá Yêu cầu cần đạt:` không được `chunker._extract_heading` nhận là tiêu đề, nên phần quy ước nằm dưới heading "D. Thiết kế hệ thống AI". Trích dẫn vì thế ghi sai mục (G03-03, G13-02, G23-03, G27-02), và ví dụ thứ hai `6.A1.MR1` bị tách sang chunk 5.
3. Phần "4 mạch, 13 chủ đề" bị cắt thành 5 chunk nhỏ (mỗi tiêu đề A./B./C./D. thành một chunk). Câu "kể 4 mạch", "tên chủ đề C5, D1" không gom đủ (G04-05, G23-05, G30-05).

**Hướng sửa:**
- Câu hỏi về chính văn bản (tên, số hiệu, ban hành, hiệu lực, toàn văn/trích, áp dụng cho…) thì đưa thêm "thẻ văn bản" vào prompt. Thẻ gồm **nguyên văn các dòng đầu** và **mục lục heading** của chính tài liệu, lấy khi truy vấn; không suy diễn, không cần bảng tra cứu.
- Chunker: dòng ngắn dạng gạch đầu dòng và kết thúc bằng dấu `:` được coi là tiêu đề mục; gộp các mục rất ngắn liền nhau.
- Phần cắt chunk mới cần **nạp lại tài liệu** (re-index) mới có hiệu lực.

## NN4 – Hỏi nối tiếp mất hoặc dính ngữ cảnh (12 câu)

**Câu:** G08-01, G08-02, G08-03, G08-04, G08-05, G20-01, G20-02, G20-03, G25-01, G25-02, G25-03, G25-04

**Nguyên nhân trong code (`query_rewriter.py`):**
1. **Luật "standalone ≥ 4 từ".** Câu không chứa đại từ trong danh sách `PRONOUNS` và có từ 4 từ trở lên bị coi là câu độc lập. "Lớp 10 thì sao?" có 4 từ; "Cái nào là yêu cầu mở rộng?" có "cái nào", không nằm trong danh sách. Cả hai bị tìm kiếm như câu mới → từ chối.
2. **Tier-2 LLM viết lại có timeout 0.8s** (`speculative_rewrite_timeout`), trong khi mô hình mất trung vị 2,5s mới ra token đầu. Lần viết lại nào cũng hết giờ và rơi về nối chuỗi thô.
3. **Ghép ellipsis sai.** "Thế còn mạng nơ-ron?" thành "Nguyên tắc đạo đức… **đối với** mạng nơ-ron" (G25-03). "Còn quy ước mã hoá là gì?" bị ghép vào câu về RAG (G25-01).
4. Câu phản bác ("Sai rồi, RAG học lớp 12 mà", "Tôi nghĩ chỉ có 3 thôi", "Bạn còn thiếu mã… phải không?") bị tìm như câu mới → từ chối. Bot không giữ hoặc rút lại câu trả lời (G20-01/02/03).
5. Không bỏ qua lượt chen ngang ngoài phạm vi (G25-02: lượt "lương" chen giữa), không hiểu "lớp dưới" (G08-03) hay "câu đầu tiên tôi hỏi" (G25-04). Lịch sử chỉ giữ 6 tin nhắn (`_resolve_history`).
6. Lượt 1 của G08-05 ("Chủ đề A3 là gì?") bị từ chối do NN1, nên các lượt sau cũng sai theo.

**Đã sửa (Query rewriting bằng LLM, slide 66; không dùng danh sách từ):**
- `query_analyzer.py`: **một lần gọi LLM ra JSON** đọc lịch sử hội thoại, viết lại tin nhắn thành câu hỏi độc lập (thay đại từ, bổ sung chủ thể, thay "câu đầu tiên" bằng nội dung câu đó, bỏ lượt chen ngang, không mang ngữ cảnh khi đổi chủ đề, khôi phục dấu, sửa lỗi gõ). Đồng thời trả các cờ `new_topic`, `challenge`, `wants_list`, `about_document`, `wants_brief`.
- Khi LLM lỗi hoặc quá thời gian (`RAG_QUERY_ANALYSIS_TIMEOUT`, mặc định 4s): ghép câu hỏi trước vào câu ngắn (cách "concatenate previous turns").
- Câu phản bác: tìm lại trên câu đã viết lại, kèm chỉ dẫn trong prompt (giữ câu trả lời nếu tài liệu ủng hộ, thừa nhận nếu người dùng đúng).
- Câu đã viết lại được lưu vào session (`standalone`); lịch sử giữ 12 tin nhắn (`RAG_HISTORY_WINDOW_MESSAGES`).

## NN5 – Không có kênh liên hệ / chuyển người xử lý (9 câu)

**Câu:** G20-04, G20-05, G26-04, G27-04, G28-01, G28-02, G28-03, G28-04, G28-05

**Nguyên nhân trong code:**
1. Mọi trường hợp đều trả **một câu cố định** `REFUSAL_MESSAGE` ("…liên hệ bộ phận liên quan"), kể cả khi người dùng xin gặp người hỗ trợ, báo lỗi, để lại số điện thoại, từ chối để lại số, hay hỏi "đã chuyển chưa".
2. Hotline, UltraViewer và mã ticket chỉ nằm trong trường `escalation` của API. Frontend không đọc trường này: grep `escalation` trong `frontend/` không có kết quả.
3. Hotline mặc định là giá trị mẫu `1900-xxxx (Nhánh 2)` (`config.py`, `escalation_hotline`).
4. Không có xử lý số điện thoại, phản hồi/báo lỗi, trạng thái ticket hay lượt phàn nàn lặp lại ("Không phải cái đó" ×2).

**Hướng sửa:**
- Đưa hotline, hỗ trợ từ xa và mã ticket **vào nội dung câu trả lời**, hiện được trên web, Zalo và app mà không phải sửa frontend.
- Tách câu trả lời theo loại: không có trong tài liệu / xin gặp người / báo lỗi / để lại số (ghi ticket kèm số) / không muốn để lại số / hỏi trạng thái / phàn nàn lặp lại / câu hỏi mơ hồ (hỏi lại kèm mục lục tài liệu).
- Cấu hình `RAG_ESCALATION_HOTLINE` bằng số thật.

## NN6 – Prompt ép khuôn, bịa nội dung, thiếu mã, lỗi định dạng (8 câu)

**Câu:** G01-04, G06-04, G07-01, G11-05, G17-01, G17-02, G23-04, G24-04

**Nguyên nhân trong code (`prompt_builder.build_context_and_citations`):**
1. Quy tắc 5 **bắt buộc** khuôn `### HƯỚNG DẪN XỬ LÝ… * **Bước 1**…` kèm ảnh mẫu `![Ảnh minh họa Bước 1](url_anh_1)` và `> [!IMPORTANT]`. `intent_classifier` gắn HOWTO cho mọi câu có "cách", "như thế nào", "hướng dẫn"… Kết quả là khối Bước 1/2/3 bịa, gắn trích dẫn (11 câu trả lời), `[!IMPORTANT]` thô (8 câu), ảnh `url_anh_1` (G22-01), link npm bịa (G25-02).
2. Quy tắc 4 bị **cắt cụt**: "…BẮT BUỘC phải trả lời chính xác câu từ chối chuẩn:" mà không có câu nào phía sau. Dòng kế tiếp "Tuyệt đối không tự suy diễn…" vì thế bị LLM chép ra như câu trả lời (G04-04).
3. Prompt bắt LLM **tự viết** "Căn cứ pháp lý & Tài liệu tham chiếu". Mô hình nhỏ chép sai tên ("GIáo DỤC" 26 lần, "KHUF"), đánh số nhảy cóc ([2] không có [1]).
4. Không bắt ghi mã hoặc số hiệu cho từng ý → thiếu mã (G01-04, G11-05). Không cấm ngoặc kép khi không phải nguyên văn (G17-02). Không phân biệt "ví dụ minh họa" với "nội dung quy định" (G24-04 lấy ví dụ `6.A1.MR1` → "lớp 6"; G13-02 sửa ví dụ). Không cấm đổi checklist thành Bước (G17-01).
5. Chunk đưa vào LLM còn tiền tố `[Ngữ cảnh: LỚP 10]` → bị lộ ra câu trả lời (G26-05).

**Hướng sửa:**
- Viết lại prompt: trả lời thẳng, ghi chính xác mã/mục, chỉ dùng ngoặc kép khi nguyên văn, ví dụ không phải quy định, không tự viết danh sách nguồn, chỉ tiếng Việt, câu từ chối chuẩn đầy đủ.
- Khuôn "Bước" **chỉ bật khi đoạn tài liệu thật sự có bước/ảnh**.
- Hậu xử lý (cả khi stream):
  - bỏ danh sách nguồn LLM tự viết, `[!IMPORTANT]`, ảnh không có trong tài liệu, `[Ngữ cảnh: …]`, câu chỉ thị bị lộ, chữ Trung/Nga;
  - đánh lại số trích dẫn;
  - thêm chân trang nguồn lấy từ metadata (đúng chính tả tên tài liệu).
- Bỏ tiền tố breadcrumb khỏi văn bản đưa vào LLM.

## NN7 – Lọt sang nhánh trò chuyện tự do (3 câu)

**Câu:** G16-03, G21-01, G21-02

**Nguyên nhân trong code:**
1. `intent_classifier.classify_advanced`: câu ngắn hoặc không có "?" sẽ gọi LLM phân loại. LLM trả `CHITCHAT`, và `chat_use_case` chuyển sang `CHITCHAT_SYSTEM_PROMPT` (temperature 0.7, **không có tài liệu**). Kết quả: bot viết bài văn kèm tiếng Trung (G16-03), giải thích "RAG?" bằng kiến thức ngoài (G21-01), đáp "AI agent" bằng lời chào lẫn tiếng Nga (G21-02).
2. Intent `OUT_OF_DOMAIN` không được xử lý ở đâu trong `chat_use_case`. Câu về lương, thông tin cá nhân, doanh thu, prompt injection rơi vào câu từ chối chung "không có trong tài liệu". Các câu này đang Đạt nhưng sai lý do (G16-01/02/04/05/06).

**Đã sửa (Intent detection bằng LLM, slide 134):**
- Ý định được xác định trong cùng lần gọi phân tích ở trên: `document_question`, `support_request`, `feedback`, `contact_info`, `decline_contact`, `ticket_status`, `greeting`, `out_of_scope`, `unclear`.
- Đã bỏ hẳn nhánh trò chuyện tự do không dùng tài liệu.
- Nhóm bị từ chối được định nghĩa bằng **cấu hình theo tenant** (`RAG_OUT_OF_SCOPE_POLICY`), không viết trong code. Câu từ chối nêu rõ lý do.

## NN8 – Không có gợi ý thêm (3 câu)

**Câu:** G26-01, G26-03, G26-05 (G26-02 và G26-04 cũng không có gợi ý nhưng được tính ở NN1 và NN5)

**Nguyên nhân:** code không có tính năng này.

**Hướng sửa:** sau câu trả lời, thêm 1–2 gợi ý lấy từ **các đoạn thật đã truy xuất** mà chưa được trích: hàng bảng cùng nhóm với hàng đã trả lời, hoặc tiêu đề mục kế tiếp. Không thêm gợi ý khi người dùng yêu cầu "một câu", "ngắn gọn"…

---

## Lỗi phụ

| Lỗi | Câu bị ảnh hưởng | Nguyên nhân |
|---|---|---|
| Viết tắt / không dấu | G06-01..05, G07-01/02/05, G21-04 | Từ điển viết tắt cố định: `HS` → "hồ sơ" (chat shorthand), `ND` → "NĐ", `CV` → "hồ sơ ứng tuyển"; thiếu YCCĐ, THPT, BVDLCN. Khôi phục dấu bằng LLM có timeout 0.8s nên luôn hết giờ. **Không sửa bằng cách thêm từ điển cứng.** Đã sửa: bộ phân tích LLM hiểu viết tắt và khôi phục dấu khi viết lại câu hỏi; ngoài ra khôi phục dấu và sửa lỗi gõ 1 ký tự **từ chính từ vựng của các đoạn tìm được** (`restore_diacritics_from_corpus`); cổng bằng chứng so khớp không phân biệt dấu, i/y. |
| Chậm (trung vị 7,5s, chỉ 4/88 lượt < 3s) | Toàn bộ | Các lệnh gọi LLM nối tiếp trước khi tìm kiếm: HyDE tự bật cho câu < 8 từ (timeout 1s), phân loại ý định bằng LLM, khôi phục dấu bằng LLM. Câu trả lời dài do khuôn Bước. Map-reduce gọi N+1 lần LLM. Cần chốt với khách: "< 3 giây" đo đến chữ đầu tiên hay đến khi trả lời xong. |
| Bản cũ hết hiệu lực (G29) | Chưa chấm | Bộ lọc `effective_status=ACTIVE` chỉ có tác dụng khi admin đặt metadata cho tài liệu. Không suy ra từ tiêu đề. |
| Câu đúng nhưng cache cũ | Sau khi sửa | `redis_cache_adapter.compute_cache_key` không có phiên bản pipeline. Cần thêm phiên bản vào khóa cache hoặc xóa cache sau khi triển khai. |

## Nguyên tắc khi sửa code

1. **Không có từ điển, danh từ, mẫu mã hay tên cơ quan riêng của tài liệu Khung AI trong code.** Mọi thống kê (IDF, từ vựng khôi phục dấu, mã định danh, mục lục, thẻ văn bản) lấy từ chính các đoạn của tài liệu được upload, tính lúc truy vấn.
2. Các luật cố định chỉ gồm từ hỏi và từ chỉ trỏ tiếng Việt chung, cùng chính sách hỗ trợ khách hàng (phiếu khảo sát 5.1, 9.1, 9.3, 9.4).
3. Dùng 151 câu làm bộ phát triển; chạy lại toàn bộ sau mỗi lần sửa, theo dõi cả hai chiều (câu đang Đạt nhờ từ chối không được chuyển sang bịa).

## Các file đã sửa

| File | Nội dung | NN |
|---|---|---|
| `use_cases/chat_use_case.py` | Viết lại phần điều phối: phân tích câu hỏi → hybrid retrieval → rerank toàn bộ ứng viên → mở rộng tài liệu → cổng bằng chứng → adaptive context → sinh câu trả lời → hậu xử lý. Non-stream và stream dùng chung một planner; vòng multi-hop cũng dùng cổng bằng chứng | 1, 2, 4, 5, 7 |
| `components/query_analyzer.py` (mới) | Viết lại câu hỏi + phân loại ý định bằng một lần gọi LLM ra JSON, có fallback | 4, 5, 7 |
| `components/lexical_evidence.py` (mới) | Độ phủ từ khóa có trọng số IDF tính trên các đoạn tìm được; mã định danh tổng quát; khôi phục dấu từ từ vựng đoạn tìm được | 1 |
| `components/context_selector.py` (mới) | Adaptive top-k theo phân bố điểm; thẻ văn bản (nguyên văn phần đầu + mục lục); lost-in-the-middle theo tài liệu | 2, 3 |
| `components/conversation_policy.py` (mới) | Soạn câu trả lời hỗ trợ (hotline, hỗ trợ từ xa, ticket) từ cấu hình; đọc ticket và câu chưa trả lời trong lịch sử | 5 |
| `components/answer_postprocessor.py` (mới) | Lọc theo cấu trúc khi stream; đánh lại số trích dẫn; chân trang nguồn lấy từ metadata; gợi ý xem thêm | 6, 8 |
| `components/prompt_builder.py` | Prompt mới; câu từ chối chuẩn đầy đủ; khuôn Bước chỉ bật khi tài liệu có bước/ảnh; bỏ breadcrumb | 6 |
| `components/error_attribution.py` | Nhận diện câu từ chối mới khi phân tích phản hồi | – |
| `config.py`, `domain/ports.py`, `adapters/qdrant_adapter.py`, `adapters/redis_cache_adapter.py` | Tham số mới (đổi được qua env); `fetch_document_chunks`; phiên bản pipeline trong khóa cache | – |
| `scripts/eval_rag_testset.py` (mới) | Chạy bộ test qua API, chấm tự động: từ chối/ticket, thiếu mã bắt buộc, lỗi hiển thị, thời gian | – |

Chưa sửa: `chunker.py` (gán sai mục cho phần quy ước). Thẻ văn bản và adaptive context đã bù cho câu hỏi về phần này; sửa chunker cần nạp lại tài liệu nên để sau.
