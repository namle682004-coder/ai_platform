# Kế hoạch sửa RAG để đạt ≥ 90% bộ test Khung AI

Tài liệu cho lần cập nhật code tiếp theo. Mỗi vấn đề ghi: **triệu chứng** (mã câu test), **nguyên nhân gốc** (file / hàm), **cách sửa** (thuật toán, chỗ sửa, cấu hình), **test cần viết**, **tiêu chí đạt**.

---

## 0. Hiện trạng và mục tiêu

| Lần chạy | Môi trường | Đạt | Tỷ lệ |
|---|---|---|---|
| 03/11 (bản cũ) | server | 52/146 | 35,6% |
| 04/11 sáng | local (LLM ctx 4096) | 86/151 | 57,0% |
| **04/11 chiều** | **server `e6e9f46`, LLM ctx 32768** | **93/151** | **61,6%** |

- **Mục tiêu: ≥ 136/151 (90%)**, tức còn phải gỡ **≥ 43 câu** trong 58 câu đang trượt.
- Thời gian: TB 7,4 s/lượt, chữ đầu tiên 5,7 s, chỉ 11/180 lượt < 3 s (chỉ tiêu < 3 s).
- File kết quả có ghi chú từng câu:
  - `Downloads/Bo_test_Chatbot_KhungAI_v2_KetQua_server_04-11.xlsx` (server);
  - `Bo_test_Chatbot_KhungAI_v2_KetQua.xlsx` ở thư mục gốc repo (local).

## 1. Nguyên tắc bắt buộc khi sửa

1. **Không hardcode** từ khoá, viết tắt, mẫu mã ("10.C1.1", "MR", "lớp", "YCCĐ"…) hay bất cứ thứ gì riêng của tài liệu test. Mọi luật phải đúng với tài liệu bất kỳ khách hàng upload (SaaS đa tenant).
   - Được dùng: thống kê trên đoạn đã truy xuất, cấu trúc văn bản (heading, bảng, mã định danh dạng chữ+số), LLM phân tích có cấu trúc (JSON), cấu hình tenant qua env.
2. Ngưỡng và chính sách mới đều thành tham số trong `solutions/rag/config.py` (env `RAG_*`), có giá trị mặc định.
3. Test đơn vị dùng **corpus mẫu trung lập** (HR mẫu trong `tests/test_rag_answer_pipeline.py`), không dùng nội dung tài liệu khách.
4. Mỗi đợt sửa phải chạy lại 151 câu trên server và so với lần trước (mục 6). Chạy **3 lần** để đo độ dao động.
5. Thay đổi phần ingest (nhóm A) **bắt buộc re-index** tài liệu; ghi rõ trong PR.

## 2. Bản đồ lỗi (58 câu trượt trên server)

| Nhóm | Vấn đề | Số câu | Ưu tiên | Ước tính gỡ |
|---|---|---|---|---|
| **A** | Câu liệt kê / tổng hợp / so sánh nhiều lớp bị thiếu mục | 17 | P2 (lớn nhất) | 13 |
| **D** | Từ chối sai hoặc truy xuất lệch phạm vi (có dữ liệu nhưng không trả lời) | 11 | P1 | 8 |
| **F** | Bịa / khẳng định sai / dùng mã ví dụ / tự mâu thuẫn | 11 | P1 | 8 |
| **B** | Câu trả lời ngắn thiếu mã định danh | 5 | P0 | 5 |
| **E** | Đồng nghĩa, viết tắt, cách nói đời thường | 4 | P2 | 3 |
| **G** | Mất ngữ cảnh hội thoại ở câu nối tiếp | 3 | P1 | 2 |
| **C** | Không lọc được theo loại mục (cốt lõi / mở rộng) | 2 | P2 | 2 |
| **H** | Lỗi hiển thị: lẫn tiếng Anh, lộ header ngữ cảnh, hỏng mã | 2 (+3 phụ) | P0 | 2 |
| **I** | Định tuyến hỗ trợ: phản hồi, từ chối để lại số | 2 | P0 | 2 |
| **J** | Câu hỏi về cấu trúc / quy ước / metadata văn bản | 1 (+4 phụ) | P0 | 1 |
| | **Tổng** | **58** | | **≈ 46 → ~139/151 (92%)** |

Danh sách đầy đủ câu → nhóm ở **Phụ lục A**.

---

## 3. Chi tiết từng nhóm

### P0 – Sửa nhanh, tất định (Đợt 1)

#### H. Lỗi hiển thị (G08-02, G17-02; phụ: G01-03, G06-01, G11-03, G20-03)

**Triệu chứng**
- Lẫn tiếng Anh khi ngữ cảnh dài: "…pecifically, the requirement is…".
- Chép nguyên header ngữ cảnh "(Tài liệu: …, Trang: 3, Mục: LỚP 12)" và bảng markdown thô vào câu trả lời.
- Mã bị hỏng: "[1].C3.MR4" (model viết `[11].C3.MR4`, trùng số nguồn hợp lệ nên bị đánh số lại).

**Nguyên nhân gốc**
- `components/prompt_builder.py::extract_citations_and_blocks` đánh dấu nguồn bằng `[n] (Tài liệu: …)`. Định dạng này trùng kiểu chữ với mã trong văn bản và dễ bị model chép lại.
- `components/answer_postprocessor.py::_MARKER_RE = \[(\d{1,2})\]` coi mọi `[số]` là số nguồn.
- Bộ lọc chữ nước ngoài `_FOREIGN_RE` chỉ bắt chữ Hán/Cyrillic, không bắt được tiếng Anh (chữ Latin).

**Cách sửa**
1. Đổi định dạng số nguồn trong prompt sang ký hiệu không trùng nội dung, ví dụ `【1】` hoặc `[S1]`:
   - sửa header khối ngữ cảnh và quy tắc 1 trong `ANSWER_RULES`;
   - `_MARKER_RE` chỉ bắt định dạng mới, rồi chuyển về `[n]` khi hiển thị;
   - `[11]` viết dính mã sẽ không còn bị đánh lại số.
2. Header khối ngữ cảnh đặt ở dạng model khó chép (`<<nguồn 1 | trang 3 | mục …>>`). Bổ sung `_CONTEXT_HEADER_RE` trong `AnswerStreamFilter._clean_inline` để xoá header bị chép, vì đó là định dạng **của chính hệ thống**.
3. **Chặn sai ngôn ngữ (language guard), làm chung cho mọi ngôn ngữ:**
   - Thêm hàm `detect_off_language_sentences(text, expected_lang)` dùng thư viện nhận diện ngôn ngữ (`lingua-language-detector` hoặc fastText `lid.176`; chạy offline, không cần internet).
   - Câu (> 6 từ) bị nhận là ngôn ngữ khác `expected_lang` (lấy từ câu hỏi, mặc định `vi`) thì bỏ khi stream. Nếu bỏ đi > 30% nội dung thì sinh lại một lần với `temperature=0`.
   - Cấu hình: `RAG_ANSWER_LANGUAGE=auto|vi|en`, `RAG_LANGUAGE_GUARD_ENABLED=true`.
4. Bảng markdown thô: khi câu hỏi không yêu cầu bảng (`analysis.wants_table` mới, xem nhóm A), quy tắc prompt yêu cầu viết lại thành câu. Trong `AnswerStreamFilter`, bảng chép **nguyên khối** từ ngữ cảnh (so khớp chuẩn hoá > 90%) thì chuyển thành gạch đầu dòng "mã. nội dung".

**Test**
- Stream có `[11].C3.MR4` vẫn giữ nguyên mã.
- Câu tiếng Anh xen giữa bị loại.
- Header "(Tài liệu: …)" bị xoá.

**Đạt khi** không câu nào trong 151 câu còn ký tự Latin-tiếng-Anh, header hay mã hỏng (kiểm tự động bằng `ARTEFACT_PATTERNS` trong `scripts/eval_rag_testset.py`, xem mục 6).

#### I. Định tuyến hỗ trợ (G20-04, G28-02; phụ: G25-02 lượt 2, G16-02)

**Triệu chứng**
- "Câu trả lời vừa rồi không đúng ý tôi, tôi muốn báo lỗi" → LLM từ chối → bot trả câu từ chối thay vì ghi nhận phản hồi.
- "Tôi không muốn để lại số" → xếp nhầm là yêu cầu hỗ trợ → bot vẫn đòi số điện thoại.
- "Lương giáo viên bao nhiêu?" lúc ra OUT_OF_SCOPE, lúc ra REFUSAL (dao động).

**Nguyên nhân gốc**
1. `chat_use_case.py`: cờ `plan.unverified_feedback` chỉ được xét trong nhánh `no_evidence` của `_plan_document_turn`. Khi cổng bằng chứng cho qua nhưng **LLM từ chối**, `_finalize_answer` gọi `_make_refusal_plan`, và hàm này không biết đến cờ đó.
2. `query_analyzer.py::build_messages` cắt mỗi tin nhắn lịch sử còn **400 ký tự đầu** (`content[:400]`). Câu "Nếu muốn được gọi lại, bạn có thể nhắn số điện thoại…" nằm ở **cuối** câu từ chối, nên bị cắt mất. Bộ phân tích không biết bot vừa xin số, nên không nhận ra "không muốn để lại số" là `decline_contact`.
3. Nhãn `out_of_scope` của Qwen 7B không ổn định.

**Cách sửa**
1. Đưa xử lý `unverified_feedback` vào `_make_refusal_plan`: nếu cờ bật thì tạo ticket `user_feedback` và trả `support.feedback(...)` thay vì `support.not_found(...)`. Áp dụng cho cả `execute` và `stream_execute`.
2. `build_messages`: với tin nhắn của trợ lý, giữ **đầu 200 + cuối 200 ký tự** (nối bằng "…"), hoặc thay bằng **tóm tắt cấu trúc**: lưu `intent` của lượt trợ lý trong session (đã có trong `_save_session_turn`) rồi đưa vào transcript dạng `Trợ lý [REFUSAL, đã xin SĐT]: …`. Thêm trường `asked_contact: bool` vào bản ghi lượt trợ lý khi trả `not_found` / `handoff`.
3. Kiểm tra chính sách khi định từ chối: trong `_make_refusal_plan`, gọi LLM một lần nữa với prompt nhị phân "Tin nhắn có thuộc nhóm bị từ chối theo chính sách sau không: {out_of_scope_policy}? Trả JSON {in_policy, category}". Nếu `in_policy` thì trả `support.out_of_scope(category)` (không tạo ticket). Chi phí chỉ phát sinh ở nhánh từ chối.

**Test**
- Phản hồi lượt đầu + LLM từ chối → intent FEEDBACK, có ticket.
- Lịch sử có lượt REFUSAL xin số + "không muốn để lại số" → DECLINE_CONTACT.
- Câu thuộc chính sách nhưng LLM gắn nhãn document → OUT_OF_SCOPE.

#### J. Câu hỏi về cấu trúc / metadata văn bản (G23-04; phụ: G03-04, G27-05, G12-01, G23-05)

**Triệu chứng**
- "Văn bản do cơ quan nào ban hành?", "Quyết định số mấy?" → từ chối hoặc tự mâu thuẫn.
- "Kể 4 mạch nội dung chính" → bịa tên.
- "Cách đọc mã 11.C3.MR4" → giải thích thiếu.

**Nguyên nhân gốc** `chat_use_case.py::_plan_document_turn` chỉ chèn **thẻ tài liệu** (`build_document_card`: tiêu đề, dòng đầu văn bản, mục lục) khi `analysis.about_document == True`. Cờ này do Qwen 7B đánh và hay sai.

**Cách sửa**
1. **Luôn** chèn thẻ tài liệu của các tài liệu trong `titled_docs` (tối đa 2) làm khối ngữ cảnh đầu tiên, giới hạn khoảng 600 ký tự mỗi thẻ (`RAG_DOCUMENT_CARD_MAX_CHARS`). Với cửa sổ 32k chi phí không đáng kể.
2. Bổ sung vào thẻ: các đoạn ở **phần mở đầu trước heading cấp 1 đầu tiên** (thường là định nghĩa, quy ước, danh sách mạch). Lấy theo cấu trúc qua `chunk_index` nhỏ nhất và heading level, không theo từ khoá.
3. Đánh dấu khối thẻ là `role=document_card` để `_build_prompt_within_window` không bao giờ bỏ nó khi cắt prompt (hiện thẻ không có trong `scores` nên đã được giữ, cần giữ hành vi này).

**Test** Câu hỏi metadata không có cờ `about_document` vẫn trả đúng tiêu đề và dòng mở đầu (corpus mẫu có dòng "Ban hành kèm theo Quyết định số …").

#### B. Câu trả lời ngắn thiếu mã định danh (G01-04, G07-01, G11-03, G11-05, G27-01)

**Triệu chứng**
- "Mạng nơ-ron học ở lớp nào?" → "lớp 11" nhưng không có mã.
- "Nội dung về RAG nằm ở những mã nào? Ghi đủ mã" → chỉ có 11.C3.MR4, thiếu 11.C3.MR3.

**Nguyên nhân gốc** LLM tự chọn mã; không có bước nào kiểm tra độ đầy đủ so với các đoạn đã truy xuất.

**Cách sửa: thêm bộ kiểm tra độ đầy đủ mã (completeness verifier, tất định)**, file mới `components/answer_verifier.py`:
1. Lấy các **mục có mã** trong ngữ cảnh đã chọn: tách dòng/hàng bảng có `IDENTIFIER_RE` (đã có trong `lexical_evidence.py`).
2. Mỗi mục tính độ phủ thuật ngữ đặc trưng của câu hỏi (dùng `score_evidence`, IDF trên các đoạn đã lấy). Mục **liên quan** là mục có ≥ 1 thuật ngữ đặc trưng (IDF cao nhất, xem `salient_terms`) hoặc độ phủ ≥ `RAG_COMPLETENESS_MIN_COVERAGE` (mặc định 0,5).
3. So với các mã đã xuất hiện trong câu trả lời. Mục liên quan bị **thiếu** thì nối thêm vào cuối câu trả lời, trước footer: dòng "Ngoài ra: `<mã>`. `<nội dung nguyên văn của mục>`" (tất định, không gọi LLM). Stream: phát sau `stream_filter.finish()`.
4. Câu hỏi hỏi vị trí ("ở đâu / lớp nào / mã nào", do bộ phân tích đánh `wants_location`) mà câu trả lời không có mã nào thì luôn nối mục liên quan nhất.

**Test** Corpus mẫu có 2 mục cùng chứa một thuật ngữ; LLM giả chỉ nêu 1 → câu trả lời cuối có cả 2 mã.

**Thêm cho G11-05 ("ghi rõ căn cứ")** Bộ phân tích có trường `wants_citation_detail`. Nếu bật thì footer thêm dòng "Căn cứ: `<tiêu đề tài liệu>` – `<dòng số hiệu ở thẻ tài liệu>` – Mục `<heading>` – `<mã>`".

#### Giảm dao động (ảnh hưởng chéo: G10-02, G21-05, G22-01, G22-04, G24-01)

Cùng code, cùng câu hỏi mà local đúng, server sai (và ngược lại).

**Cách sửa**
- Cấu hình `RAG_GENERATION_TEMPERATURE_MAX=0.0` (mặc định 0,1), áp vào mọi lời gọi `llm_service.generate/stream_generate` cho nhánh QA.
- Truyền `seed` cố định (llama.cpp hỗ trợ `seed` trong `/v1/chat/completions`).
- Bộ phân tích đã dùng temperature 0, giữ nguyên.

**Đạt khi** chạy 3 lần liên tiếp, ≥ 95% câu cho cùng kết luận Đạt/Không đạt.

---

### P1 – Truy xuất và chống bịa (Đợt 2)

#### D. Từ chối sai / truy xuất lệch phạm vi (11 câu: G05-03, G10-01, G10-02, G25-03, G20-01, G22-01, G22-04, G21-05, G09-04, G25-05, G03-04)

**Triệu chứng**
- "Lớp 10 học RAG như thế nào?", "Lớp 10 có học AI agent không?" → từ chối, thay vì đính chính "thuộc lớp 11/12".
- "RAG học lớp mấy?", "Teachable Machine học lớp mấy?", "luật dữ liệu" → lúc đúng lúc từ chối.
- Câu nhiều ý (G25-05) → từ chối toàn bộ.

**Nguyên nhân gốc**
1. **Truy xuất bị phạm vi trong câu hỏi kéo lệch.** Từ "lớp 10" chiếm trọng số lớn trong BM25/dense, nên top-k toàn đoạn lớp 10. Đoạn chứa **đối tượng chính** (RAG, AI agent) ở lớp khác không vào ngữ cảnh, LLM không có gì để đính chính.
2. **LLM từ chối dù ngữ cảnh có đáp án** (Qwen 7B với câu hỏi "X ở lớp mấy?"): bảng nhiều cột, đối tượng nằm sâu trong một ô.
3. Câu nhiều ý chỉ được truy xuất một lần cho cả câu.

**Cách sửa**
1. **Truy xuất theo đối tượng chính (focus) kết hợp RAG-Fusion:**
   - Bộ phân tích (`query_analyzer._system_prompt`) trả thêm 2 trường JSON:
     - `focus_terms`: đối tượng được hỏi, đúng chữ người dùng (ví dụ "AI agent");
     - `scope_terms`: điều kiện phạm vi (ví dụ "lớp 10").
   - `_search_candidates` chạy song song 2 truy vấn: (a) câu đầy đủ, (b) **chỉ `focus_terms`**. Gộp bằng RRF (`qdrant_adapter` đã có RRF cho dense + sparse; thêm RRF mức truy vấn trong `chat_use_case`). Truy vấn (b) có `top_k` riêng (`RAG_FOCUS_QUERY_TOP_K=16`).
   - Trong `select_adaptive_context`, luôn giữ ≥ 1 đoạn tốt nhất của truy vấn (b) (`RAG_FOCUS_MIN_PASSAGES=2`).
   - Khi đoạn của (b) **không khớp** `scope_terms` mà phạm vi đó có trong corpus, thêm vào user_content: "(Đối tượng được hỏi xuất hiện ở «<heading của đoạn>», không ở «<scope>»: đính chính tiền đề theo quy tắc 5)". Đây là thống kê trên đoạn, không phải từ khoá.
2. **Kiểm chứng câu từ chối bằng bằng chứng (kiểu Self-RAG):**
   - `_finalize_answer` nhận `refused=True` thì **trước khi** tạo ticket, kiểm tra `focus_terms` có xuất hiện nguyên văn (chuẩn hoá) trong ≥ 1 đoạn đã chọn không.
   - Nếu có, sinh lại **một lần** bằng prompt trích xuất: "Chép nguyên văn các dòng chứa «focus» kèm mã và mục, rồi trả lời câu hỏi trong 1–2 câu", `temperature=0`.
   - Nếu vẫn từ chối, trả câu trả lời **trích xuất tất định**: các dòng chứa focus kèm mã và heading, mở đầu bằng "Tài liệu đề cập «focus» tại:".
   - Stream: phần này chạy sau khi `AnswerStreamFilter` báo `refused` (lúc đó chưa có gì được phát ra).
3. **Tách câu nhiều ý:** khi `query_decomposer.should_decompose` trả true hoặc bộ phân tích trả `sub_questions` (trường mới, ≤ 3), đi nhánh multihop sẵn có (`_execute_multi_hop`) và kiểm tra lại nhánh đó với cửa sổ 32k.

**Cấu hình** `RAG_FOCUS_RETRIEVAL_ENABLED`, `RAG_FOCUS_QUERY_TOP_K`, `RAG_FOCUS_MIN_PASSAGES`, `RAG_REFUSAL_VERIFY_ENABLED`.

**Test**
- Corpus mẫu: "Chương I có quy định nghỉ thâm niên không?" khi thâm niên nằm ở Chương II → câu trả lời đính chính, có mã.
- LLM giả từ chối nhưng ngữ cảnh có focus → câu trả lời trích xuất có mã.

#### F. Bịa / khẳng định sai (11 câu: G12-01, G12-04, G13-04, G15-03, G19-01, G29-04, G29-05, G23-05, G24-04, G27-05, G20-03)

**Triệu chứng**
- Bịa ngày hiệu lực, "năm 2023", mã không tồn tại (12.C3.MR4, 6.D1.1).
- Dùng mã **ví dụ** của phần quy ước (6.A1.MR1) như nội dung thật.
- "5 rủi ro theo khung".
- Kết luận sai ("không có sự khác biệt"), tự mâu thuẫn.
- Đồng ý với người dùng khi bị phản bác sai (G20-01 lượt 2) hoặc phủ nhận khi người dùng đúng (G20-03).

**Cách sửa: 3 lớp kiểm chứng sau sinh (`components/answer_verifier.py`)**
1. **Kiểm chứng mã định danh (tất định):**
   - Mọi mã trong câu trả lời phải có **nguyên văn** trong ngữ cảnh đã chọn.
   - Mã không có (bịa) thì xoá câu chứa nó. Nếu câu đó là câu trả lời chính thì sinh lại một lần với chỉ dẫn "Các mã sau không có trong tài liệu: …".
   - Stream: giữ (hold) dòng có mã đến khi kiểm xong, như cơ chế giữ dòng tiêu đề hiện có trong `AnswerStreamFilter`.
2. **Gắn vai trò đoạn khi ingest (`content_role`):**
   - Trong `chunker.py` / `ingestion_use_case.py`, phân loại mỗi chunk thành `normative | example | definition | metadata`. Dùng LLM một lượt mỗi tài liệu (batch các chunk, JSON) hoặc luật cấu trúc: khối nằm trong phần định nghĩa/quy ước trước nội dung chính, dòng bắt đầu bằng nhãn kết thúc dấu ":" lặp lại.
   - Lưu `content_role` vào payload Qdrant.
   - Mã chỉ xuất hiện trong đoạn `example` thì không được dùng làm câu trả lời cho câu hỏi nội dung. Prompt đánh dấu khối example là "(VÍ DỤ MINH HOẠ – không phải nội dung quy định)". Bộ kiểm chứng (1) coi mã chỉ có trong example là không hợp lệ, trừ khi câu hỏi về quy ước (`analysis.about_document`).
3. **Kiểm chứng từng câu bằng cross-encoder (faithfulness, chạy được ngay):**
   - Tách câu trả lời thành câu. Mỗi câu khẳng định (có số, năm, ngày, mã, "không có", "chỉ có") chấm điểm với các đoạn bằng **bge-reranker** sẵn có (`reranker_service.arerank(query=câu, candidates=đoạn)`).
   - Câu có điểm tối đa < `RAG_CLAIM_SUPPORT_MIN_SCORE` (đặt khoảng 0,2, cần hiệu chỉnh trên tập dev) bị xoá. Nếu xoá câu đầu thì dùng câu trả lời trích xuất (nhóm D.2).
   - Áp riêng cho câu phủ định ("tài liệu không có X"): kiểm tra X có trong đoạn đã chọn bằng `normalize_for_match`. Có thì câu phủ định sai, phải xoá và sinh lại.
4. **Giữ quan điểm khi bị phản bác:** khi `analysis.challenge`, so khẳng định mới của người dùng (năm, lớp, mã, số lượng) với bằng chứng bằng (1) và (3).
   - Bằng chứng ủng hộ câu trả lời trước: nhắc lại kèm trích dẫn (dùng lại `citations` của lượt trước, lưu trong session).
   - Người dùng đúng (mã họ nêu có trong ngữ cảnh mà câu trả lời trước thiếu): thừa nhận và bổ sung.
5. Mở rộng `absent_numeric_details` thành `absent_premise_details`: thêm năm/ngày (các con số) và cụm "ngày hiệu lực"-loại do bộ phân tích trích (`premise_terms`). Đã có cơ chế báo cho LLM; bổ sung kiểm tra sau sinh: câu trả lời lặp lại chi tiết vắng mặt như sự thật thì xoá câu đó.

**Cấu hình** `RAG_IDENTIFIER_GROUNDING_ENABLED`, `RAG_CLAIM_VERIFICATION_ENABLED`, `RAG_CLAIM_SUPPORT_MIN_SCORE`.

**Test**
- LLM giả trả mã không có trong corpus → câu bị xoá.
- Mã chỉ có trong đoạn example → không xuất hiện.
- Câu "tài liệu không có X" khi X có trong đoạn → bị xoá.

#### G. Mất ngữ cảnh hội thoại (G08-03, G08-05, G25-02; phụ: G25-03)

**Triệu chứng**
- "Thế lớp dưới thì học gì về prompt?" → trả lớp 11.
- "Mã nào là mở rộng?" → trả ví dụ chung chung thay vì mã của chủ đề đang nói.
- "Quay lại, cái nào là yêu cầu mở rộng?" sau câu chen ngang → mất ngữ cảnh "công cụ".
- "Thế còn mạng nơ-ron?" → mang nhầm phạm vi "lớp 12" của câu trước.

**Nguyên nhân gốc** `query_analyzer.build_messages` chỉ đưa transcript đã cắt 400 ký tự. Không có **bộ nhớ thực thể** (mã, đối tượng, phạm vi) của các lượt trước.

**Cách sửa**
1. Lưu vào mỗi lượt trong session (`_save_session_turn`): `focus_terms`, `scope_terms`, `identifiers` (các mã có trong câu trả lời), `standalone`.
2. Đưa vào prompt bộ phân tích một khối "TRẠNG THÁI HỘI THOẠI": danh sách lượt gần nhất kèm focus/scope/mã. Prompt nêu quy tắc:
   - câu nối tiếp không có focus riêng thì kế thừa focus và scope của lượt liên quan gần nhất (bỏ qua lượt chen ngang có intent khác `document_question`);
   - câu có focus mới thì **không** kế thừa scope cũ;
   - tham chiếu tương đối ("dưới / trên / trước / sau") được giải theo **thứ tự các giá trị scope có trong corpus**. Danh sách giá trị scope lấy từ heading cấp 1 của tài liệu (`outline_from_candidates`), không hardcode.
3. Câu nối tiếp hỏi loại mục ("mã nào là mở rộng") thì dùng `identifiers` của lượt trước làm tập ứng viên và lọc theo nhóm C.

**Test** Corpus mẫu 3 lượt: chương II → "chương trước thì sao?" → standalone chứa "Chương I". Có lượt chen ngang thì vẫn đúng.

---

### P2 – Câu hỏi có cấu trúc (Đợt 3, cần re-index)

#### A. Liệt kê / tổng hợp / so sánh nhiều phần (17 câu: G04-01…05, G08-01, G17-03, G19-02…05, G22-02, G23-02, G24-01…03, G02-05)

**Triệu chứng**
- "Lớp 10 học những chủ đề nào?" chỉ ra 5–8/10 chủ đề, có lúc bịa chủ đề.
- "Chủ đề D2 qua 3 lớp" thiếu một lớp; bảng mạch D thiếu lớp 10.
- Mỗi lần hỏi lại ra danh sách khác nhau.

**Nguyên nhân gốc**
- Tài liệu dạng **bảng** (Chủ đề | Nội dung | Yêu cầu cần đạt) bị chunk theo khối khoảng 900 ký tự. Câu hỏi tổng quan cần **toàn bộ hàng** của một phạm vi, nhưng truy xuất top-k + `select_adaptive_context` (cắt theo điểm tương đối) chỉ giữ một phần.
- Kể cả khi đủ ngữ cảnh, Qwen 7B vẫn tóm tắt thiếu khi danh sách dài.

**Cách sửa: chỉ mục hàng bảng + truy vấn có cấu trúc (self-query, phương pháp metadata filtering trong slide RAG)**
1. **Ingest (`chunker.py`):**
   - Ngoài chunk thường, với mỗi bảng (đã có `_is_table_block`, `_extract_table_headers`), sinh **bản ghi hàng** gồm:
     - `section_path` (breadcrumb heading, ví dụ ["LỚP 10"]);
     - `columns` (tên cột lấy từ header bảng);
     - `cells` (giá trị từng cột, **điền xuống** các ô gộp, tức rowspan);
     - `identifiers` có trong hàng;
     - `row_index`.
   - Lưu thành collection mới `aip_table_rows` trong Qdrant (payload + vector của hàng chuẩn hoá) hoặc Mongo `rag_table_rows`.
   - Không giả định tên cột: mọi thứ lấy từ header của chính bảng.
2. **Truy vấn có cấu trúc:**
   - Khi `analysis.wants_list` (hoặc trường mới `structured: true`), gọi LLM một lần (JSON) với **lược đồ thật** của tenant: danh sách `section_path` duy nhất, tên cột, vài mã mẫu. LLM trả bộ lọc, ví dụ: `{"sections": [...], "column_filters": {"<tên cột>": "<giá trị>"}, "identifier_prefix": "...", "group_by": "<tên cột>"}`.
   - Áp bộ lọc lên `aip_table_rows` (khớp chuẩn hoá, có fuzzy) để lấy **đủ mọi hàng**.
3. **Sinh câu trả lời tất định cho danh sách:**
   - Hiển thị nhóm theo `group_by` theo đúng thứ tự `row_index`: tiêu đề nhóm (giá trị cột nhóm), rồi từng dòng "`mã`. `nội dung`".
   - LLM chỉ viết **1 câu mở đầu** (hoặc không cần), nên không còn thiếu mục hay bịa chủ đề.
   - Dạng bảng ("trình bày dạng bảng") hoặc checklist (☐) render theo `analysis.format`.
4. **So sánh / theo thời gian** ("A1 thay đổi thế nào từ lớp 10 đến 12", "D2 qua 3 lớp"):
   - bộ lọc trả nhiều `sections`, render theo từng section;
   - LLM nhận bảng đã đủ hàng để viết **nhận xét so sánh** ngắn (≤ 3 câu), sau đó qua bộ kiểm chứng F.3.
5. Phạm vi mơ hồ (G24-01…03: "Học sinh học gì về prompt?", "Yêu cầu C3.1 là gì?"): bộ lọc trả nhiều section thì **liệt kê tách theo section** (hoặc hỏi lại khi > `RAG_AMBIGUOUS_MAX_SECTIONS`).
6. Câu tổng quan cấp cao ("có mấy mạch và gồm chủ đề nào"): nếu tài liệu có danh sách cấu trúc ở phần mở đầu (thẻ tài liệu, nhóm J) thì dùng nó; nếu không thì suy ra từ giá trị duy nhất của cột nhóm trên toàn bộ hàng.

**Lưu ý** Phải **re-index** mọi tài liệu sau khi đổi ingest. Viết script `scripts/reindex_tenant.py --tenant <id>`.

**Test**
- Corpus mẫu dạng bảng 2 chương × 3 mục, có ô gộp. "Chương I gồm những mục nào?" → đủ 3 mục, đúng thứ tự.
- "So sánh mục X giữa chương I và II" → đủ 2 chương.

**Đạt khi** G04-01…05, G22-02 (3 lần nhất quán), G23-02, G24-03, G19-04 liệt kê đủ 100% mã kỳ vọng ở cột "Căn cứ" (kiểm tự động, mục 6).

#### C. Lọc theo loại mục (G06-04, G09-01)

**Triệu chứng** "Yêu cầu mở rộng lớp 11 thuộc mạch C" → lẫn mã cốt lõi.

**Cách sửa** (cần A)
- Bộ lọc self-query (A.2) có thêm `identifier_pattern`: LLM suy ra từ **phần quy ước của chính tài liệu** (đưa thẻ tài liệu vào prompt) và **mã mẫu thật**, rồi trả một regex an toàn.
- Hệ thống kiểm regex: chỉ cho ký tự an toàn, phải khớp ≥ 1 mã mẫu.
- Không hardcode "MR": quy ước khác (ví dụ ".a", ".b") vẫn hoạt động.

**Test** Corpus mẫu mã "HR.A2.1 / HR.A2.MR1" và quy ước trong thẻ tài liệu; hỏi "mục mở rộng" → chỉ ra mã MR.

#### E. Đồng nghĩa, viết tắt, cách nói đời thường (G02-01, G02-02, G02-04, G06-03)

**Triệu chứng**
- "máy học thuộc lòng dữ liệu quá mức" (= overfitting);
- "trợ lý AI tự động thực hiện nhiệm vụ" (= tác nhân AI);
- "HS THPT học gì về NLP và CV";
- "cấp 3" (= lớp 10–12).

**Cách sửa**
1. **Mở rộng truy vấn nhiều câu (multi-query, slide "query rewriting"):**
   - Bộ phân tích trả `paraphrases` (≤ 3 câu viết lại bằng **thuật ngữ chuyên môn** tương đương, ví dụ "quá khớp dữ liệu (overfitting)").
   - Mỗi câu chạy hybrid search, gộp RRF cùng truy vấn D.1.
   - Bật khi cổng bằng chứng của truy vấn gốc **yếu** (`top_score < gate_min_rerank_score` và `best_lexical < gate_min_lexical_coverage`) để không tốn thời gian cho câu dễ.
   - Cấu hình `RAG_MULTI_QUERY_ON_WEAK_EVIDENCE=true`.
2. **HyDE khi bằng chứng yếu:** `hyde_generator` đã có, đang tắt (`RAG_HYDE_AUTO_ENABLED=false`). Bật có điều kiện như (1), thay vì bật cho mọi câu.
3. **Bảng viết tắt lấy từ corpus:**
   - `components/acronym_harvester.py` đã có các bước EXPLICIT/DERIVE (bắt "xử lí ngôn ngữ tự nhiên (NLP)" trong văn bản) nhưng hiện chỉ dùng ở `glossary_for_prompt`.
   - Nối `harvest` vào ingest để lưu glossary **theo tenant**.
   - Dùng `expand_query` (ABBR ↔ dạng đầy đủ) cho **truy vấn sparse/BM25** trong `_search_candidates`.
   - Không nạp từ điển viết tắt tĩnh riêng cho tài liệu test (vi phạm nguyên tắc 1). Từ điển dùng chung tiếng Việt có sẵn trong `vietnamese_resources` thì giữ ở mức tổng quát.
4. Cổng bằng chứng tính trên **truy vấn mở rộng tốt nhất**, không chỉ chữ người dùng (hiện `lexical_query = rerank_query`).

**Test** Corpus mẫu có "nghỉ phép năm (NPN)"; hỏi "NPN được mấy ngày" và "được nghỉ bao nhiêu ngày mỗi năm" đều trả lời được.

---

## 4. Độ trễ (chỉ tiêu < 3 giây)

**Hiện trạng** chữ đầu tiên TB 5,7 s. Chuỗi xử lý tuần tự:
- bộ phân tích LLM ≈ 1–1,5 s;
- truy xuất + rerank ≈ 1 s;
- prefill prompt 3–8k token trên Titan Xp ≈ 2–4 s;
- chờ hết câu đầu để dò câu từ chối.

**Cách giảm (theo thứ tự hiệu quả)**
1. **Chạy song song:** gọi bộ phân tích và truy xuất bằng câu gốc cùng lúc (`asyncio.gather`). Nếu standalone khác câu gốc thì truy xuất bổ sung, bỏ kết quả câu gốc nếu điểm thấp. Lượt đầu phiên (không có lịch sử) có thể bỏ qua chờ.
2. **Prompt cache của llama.cpp:** đặt phần **không đổi** (quy tắc trả lời) ở đầu system prompt, ngữ cảnh ở sau, gửi `cache_prompt: true`. llama-server tái dùng KV cache của tiền tố, giảm prefill khoảng 1 s.
3. **Ngữ cảnh thích ứng theo loại câu:** câu hỏi điểm (không phải `wants_list`) giới hạn `RAG_CONTEXT_CHAR_BUDGET_POINT=3500`; câu liệt kê dùng nhánh A (tất định, không cần prompt dài).
4. **Bộ phân tích nhẹ:** lượt đầu phiên có câu hỏi đủ dài mà không có lịch sử thì chỉ cần intent. Thử model nhỏ (Qwen2.5-1.5B) cho bộ phân tích trên cùng GPU (khoảng 1 GB).
5. **Phần cứng / model:** Titan Xp (Pascal) prefill chậm. Mục tiêu < 3 s ổn định cần GPU mới hơn (≥ Ampere, 24 GB) hoặc vLLM. Ghi rõ để quyết định ngân sách.

**Đạt khi** chữ đầu tiên TB ≤ 3 s cho câu hỏi điểm, ≤ 5 s cho câu liệt kê.

## 5. Bảo mật dữ liệu và vận hành

1. **Cách ly tenant:**
   - `qdrant_adapter.py` (tìm kiếm) luôn gộp `["global", "proj_default"]` vào tenant hiện tại. Mọi tài liệu upload vào `proj_default` sẽ lộ cho **mọi** khách hàng (ở local G30-02 trả về tên tài liệu của tenant khác).
   - Sửa:
     - bỏ `proj_default` khỏi danh sách mặc định;
     - kho dùng chung `global` chỉ gộp khi tenant bật `RAG_SHARED_KB_ENABLED` (cấu hình theo tenant trong Mongo);
     - danh sách "Tài liệu hiện có" chỉ lấy tài liệu của tenant.
2. **llama-server bằng systemd:** :8011 đang chạy tay bằng `nohup -c 32768`, máy khởi động lại là mất. Tạo unit `llama-qwen.service` (cần sudo) cho 8011/8012/8013. Nên tăng thêm batch cho reranker (`-c 4096 -ub 1024`) rồi đặt `RAG_RERANKER_MAX_INPUT_TOKENS=1024`.
3. **Đĩa server 99% (811 MB trống).** Dọn ảnh/cache Docker và log; hoặc mở rộng LV (cần sudo). Script deploy nên dừng sớm nếu < 2 GB.
4. **Cấu hình tenant:** `RAG_ESCALATION_HOTLINE` (đang là 1900-xxxx), `RAG_OUT_OF_SCOPE_POLICY`.
5. **Worker local:** container `aip-rag-worker` cũ nghe CloudAMQP. Đang chạy tạm `aip-rag-worker-local`. Cần build lại image `rag-worker` và dọn container cũ.

## 6. Quy trình đo và chống thoái lui

1. **Mở rộng `scripts/eval_rag_testset.py`:**
   - `--repeat 3`: chạy mỗi câu 3 lần, báo độ nhất quán.
   - Kiểm tự động theo cột "Căn cứ":
     - `required_codes_hit` (tỷ lệ mã kỳ vọng có trong câu trả lời);
     - `forbidden_codes` (mã không có trong tài liệu);
     - `refusal_expected` (nhóm G14, G16);
     - `ARTEFACT_PATTERNS` thêm: tiếng Anh, header ngữ cảnh, mã hỏng `\[\d+\]\.[A-Z]`.
   - Xuất `So sánh` với lần trước (logic như `write_results.py` trong phiên này).
2. **Chấm điểm:** tự động ≈ 70% (mã, từ chối, định dạng); phần còn lại chấm tay hoặc dùng LLM-judge mạnh hơn (chạy ngoài server, chỉ trên đáp án test, không đụng dữ liệu khách).
3. **Cổng phát hành:** không deploy nếu tỷ lệ đạt giảm > 2 điểm hoặc có lỗi hiển thị mới.
4. Test đơn vị mỗi nhóm (đã liệt kê) thêm vào `tests/test_rag_answer_pipeline.py` hoặc file mới `tests/test_answer_verifier.py`, `tests/test_table_rows.py`.

## 7. Lộ trình đề xuất

| Đợt | Nội dung | Re-index | Kỳ vọng sau đợt |
|---|---|---|---|
| **1** | H, I, J, B, giảm dao động (temperature 0 + seed), kiểm chứng mã (F.1) | Không | ~105/151 (70%) |
| **2** | D (focus retrieval + kiểm chứng từ chối), G (bộ nhớ thực thể), F.3–F.5 (kiểm chứng câu, giữ quan điểm), E.1–E.2 (multi-query/HyDE khi yếu) | Không | ~120/151 (79%) |
| **3** | A + C (chỉ mục hàng bảng, self-query, render tất định), F.2 (`content_role`), E.3 (glossary theo tenant) | **Có** | ~136–140/151 (90–93%) |
| **4** | Độ trễ (mục 4), cách ly tenant, systemd, đĩa | Không | Giữ ≥ 90%, chữ đầu ≤ 3 s |

**Rủi ro**
- Qwen2.5-7B Q4 là giới hạn lớn nhất: bịa mã, lẫn tiếng Anh, hùa theo người dùng. Các lớp kiểm chứng (F) và nhánh tất định (A, B, D) được thiết kế để **không phụ thuộc** vào việc model tự làm đúng.
- Nếu sau Đợt 3 vẫn < 90%, phương án tiếp theo là nâng model sinh câu trả lời (Qwen2.5-14B/32B hoặc tương đương, cần GPU lớn hơn).
- Nhóm G29 cần dựng "bản cũ giả lập" theo kịch bản test (nạp văn bản cũ, đặt hết hiệu lực, xoá bản cũ). Logic hiệu lực văn bản (`effective_status`, `expiry_date` đã có trong metadata tài liệu) cần được dùng khi lọc truy xuất. Phải dựng dữ liệu trước khi chấm.

---

## Phụ lục A – 58 câu trượt trên server (04/11, `e6e9f46`) → nhóm

| Nhóm | Câu |
|---|---|
| A – Liệt kê/tổng hợp | G02-05, G04-01, G04-02, G04-03, G04-04, G04-05, G08-01, G17-03, G19-02, G19-03, G19-04, G19-05, G22-02, G23-02, G24-01, G24-02, G24-03 |
| B – Thiếu mã | G01-04, G07-01, G11-03, G11-05, G27-01 |
| C – Lọc loại mục | G06-04, G09-01 |
| D – Từ chối sai / lệch phạm vi | G03-04, G05-03, G09-04, G10-01, G10-02, G20-01, G21-05, G22-01, G22-04, G25-03, G25-05 |
| E – Đồng nghĩa/viết tắt | G02-01, G02-02, G02-04, G06-03 |
| F – Bịa / khẳng định sai | G12-01, G12-04, G13-04, G15-03, G19-01, G20-03, G23-05, G24-04, G27-05, G29-04, G29-05 |
| G – Mất ngữ cảnh | G08-03, G08-05, G25-02 |
| H – Hiển thị | G08-02, G17-02 |
| I – Định tuyến hỗ trợ | G20-04, G28-02 |
| J – Metadata/quy ước | G23-04 |

## Phụ lục B – Vị trí code chính

| Thành phần | File / hàm |
|---|---|
| Luồng chat | `solutions/rag/application/use_cases/chat_use_case.py`: `_plan_turn`, `_plan_support_turn`, `_plan_document_turn`, `_build_prompt_within_window`, `_make_refusal_plan`, `_finalize_answer`, `_generate_stream`, `stream_execute` |
| Phân tích câu hỏi | `components/query_analyzer.py`: `_system_prompt`, `build_messages` (cắt 400 ký tự), `parse` |
| Bằng chứng từ vựng | `components/lexical_evidence.py`: `score_evidence`, `IDENTIFIER_RE`, `absent_numeric_details` |
| Chọn ngữ cảnh / thẻ tài liệu | `components/context_selector.py`: `select_adaptive_context`, `build_document_card` |
| Prompt | `components/prompt_builder.py`: `ANSWER_RULES`, `extract_citations_and_blocks` |
| Hậu xử lý | `components/answer_postprocessor.py`: `AnswerStreamFilter`, `_MARKER_RE`, `is_llm_refusal`, `build_suggestions` |
| Hỗ trợ / ticket | `components/conversation_policy.py`: `SupportResponder` |
| Chunking / ingest | `components/chunker.py` (`_is_table_block`, `_extract_table_headers`, `chunk_document`), `use_cases/ingestion_use_case.py` |
| Viết tắt | `components/acronym_harvester.py` (`expand_query`, `glossary_for_prompt`) |
| Tìm kiếm / tenant | `infrastructure/adapters/qdrant_adapter.py` (`tenant_variants`, `fetch_document_chunks`) |
| LLM / reranker | `infrastructure/adapters/llm_adapter.py`, `reranker_adapter.py` |
| Cấu hình | `solutions/rag/config.py` |
| Đánh giá | `scripts/eval_rag_testset.py` |
