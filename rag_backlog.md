# AIP RAG – Việc cần giải quyết (backlog)

Cập nhật: 06/11/2026. Server msp đang tắt: ưu tiên các việc **Local** trước.
Mức độ sẵn sàng của từng bước: xem [rag_readiness.md](rag_readiness.md). Ma trận lỗi:
[.claude/skills/rag-quality-protocol/coverage-matrix.md](.claude/skills/rag-quality-protocol/coverage-matrix.md).

Ký hiệu: **Local** = làm và đo được trên máy này · **Server** = cần msp (model, dữ liệu thật) · **Duyệt** = cần chủ dự án đồng ý.

---

## 0. Đã làm, CHƯA commit, CHƯA deploy

Không mất các thay đổi này. Commit sau khi review.

| Việc | File chính | Đo |
|---|---|---|
| Chặn upload trùng (SHA-256 theo tenant + quyền) | `knowledge_use_case.py`, `mongo_document_repo.py`, `knowledge_router.py`, 3 trang frontend | test `test_rag_document_dedup.py` |
| Chào hỏi / phàn nàn không lặp lại câu trả lời cũ | `query_analyzer.py` | test `test_rag_restated_turns.py` |
| Bỏ hotline giả và yêu cầu mật khẩu UltraViewer | `config.py` | test `test_rag_support_defaults.py` |
| Bảng đủ tên cột cho docx/xlsx/pdf (header nhiều tầng, caption, biểu mẫu, PDF phân trang theo cột/dòng) | `parsers/table_grid.py`, `docx_parser.py`, `excel_parser.py`, `pdf_parser.py` | DQ2 82% → **100%** |
| Không mất heading; câu dài đánh số không bị coi là heading | `chunker.py` | DQ1 97,7% → **99,6%** |
| Cấu trúc văn bản con (H9): cấp heading từ outline Word | `docx_parser.py`, `chunker.py` | breadcrumb "Điều 7" đúng văn bản |
| Mở upload `.xlsx` | `knowledge_use_case.py` | test |
| OCR: Tesseract best, OCR ảnh gốc, lọc nhiễu, hài hòa dấu | `pdf_parser.py`, `parsers/ocr_text.py`, `Dockerfile` | 0% → **85%** khớp nguyên câu |
| Cổng dữ liệu + bộ test DG233 (49 câu) | `benchmarks/rag/src/rag_benchmark/data_audit.py`, `make rag-data-gate`, `datasets/acceptance/dg233_v1*` | |
| Skill quy trình, ma trận, tiêu chuẩn dữ liệu | `.claude/` | |
| Cấu hình model ứng viên Qwen3-14B | `deploy/onprem/host/models/chat-qwen3-14b.env` | chưa chạy thử |
| **Connector nguồn dữ liệu** (07/11): đọc trực tiếp API JSON (kiểu fbx_runner) và website nội bộ theo lịch, đi qua đúng pipeline ingestion; chống SSRF, bí mật chỉ qua biến môi trường `AIP_SOURCE_SECRET_*`, chỉ admin; chỉ nạp lại phần đổi; chỉ xóa khi đọc đủ | `solutions/rag/CONNECTORS.md`, `infrastructure/connectors/`, `use_cases/source_sync_use_case.py`, `api/sources_router.py`, worker | 17 unit test; **e2e 26/26** (`make rag-connectors-e2e`, stack cô lập + nguồn giả lập). Chưa thử với nguồn thật của khách |
| **Nối thử nguồn thật fbx** (07/11): hỗ trợ con trỏ phân trang trong header (`header:x-next-cursor`), ngày và giờ theo múi người dùng (`RAG_CONNECTOR_TIMEZONE`, mặc định +07:00), Thử kết nối gợi ý header phân trang | `domain/sources.py`, `connectors/json_api.py`, `connectors/preview.py`, `source_sync_use_case.py`, UI | 21 unit test; stack cô lập + fbx thật: 61/61 bài, 6 tài liệu, số bài/ngày khớp fbx, đồng bộ lại 0 nạp lại. Chưa tạo nguồn trên môi trường dev |
| **Phiếu khảo sát DVKH – nhóm làm được ở local** (07/11; một phần do phiên khác viết song song, đã soát và sửa): #3 ảnh đặt dưới bước (theo số bước, không có thì theo câu trước ảnh; sửa lỗi mất dòng Nguồn/gợi ý khi chèn ảnh; bỏ thẻ ảnh giả trong prompt) · #2 thay phiên bản (bản cũ chỉ bị gỡ khi bản mới INDEXED; nạp lỗi thì giữ bản cũ) · #5 nhập Hỏi – Đáp Excel (nhận cột theo cả từ, bỏ qua câu đã có; nút tải mẫu có kèm API key) · #4 cấu hình liên hệ theo dự án (dùng cho cả câu ngoài phạm vi) · #12 phòng ban (lấy từ tài liệu, không viết cứng; lọc = phòng đó + tài liệu chung) · #7 hướng dẫn chuẩn bị tài liệu (bỏ hứa 100%, tách bộ nghiệm thu khỏi Hỏi – Đáp) | `media_assets.py`, `chat_use_case.py`, `ingestion_use_case.py`, `knowledge_use_case.py`, `qdrant_adapter.py`, `knowledge_router.py`, `index.html`, `docs/HUONG_DAN_CHUAN_BI_TAI_LIEU_CHATBOT.md` | 276 test RAG; Chrome headless: phòng ban 7/7, Library 15/15, Nguồn 17/17, Phản hồi 12/12. **Chưa đo với model thật** (quy tắc định dạng theo loại câu hỏi, ảnh trên tài liệu HDSD thật) |
| **Library thành trang** (07/11): "Quản lý & Nạp Tài Liệu Tri Thức" chiếm vùng làm việc thay khung chat (`…/knowledge[/documents|/qa|/sources]`), nút ← Trò chuyện, Back của trình duyệt; chỉ một trang (Library / Hộp thư) mỗi lúc; form Nguồn dữ liệu và kết quả Thử kết nối đặt cạnh nhau (3:2), hàng nhiều ô tự xuống dòng; tài liệu mở toàn trang | `index.html` | **11/11** Chrome headless (cả điện thoại); Nguồn dữ liệu 17/17, Phản hồi 12/12 |
| **Hộp thư = CSKH phản hồi khách** (07/11): bỏ "Thêm Hỏi – Đáp" khỏi hộp thư (Hỏi – Đáp đóng đinh câu trả lời cho mọi lần hỏi sau, khác với trả lời một khách); thêm ô Phản hồi → tin "Nhân viên hỗ trợ" vào đúng cuộc trò chuyện của khách (`POST /v1/rag/tickets/{id}/reply`, vai trò support/agent/cskh/admin), khách thấy ngay (`GET /v1/rag/sessions/{id}/agent-replies`, chỉ hỏi khi còn câu chờ); bot không coi tin của nhân viên là câu trả lời từ tài liệu (loại khỏi lịch sử) | `chat_router.py`, `identity.py`, `mongo_session_repo.py`, `chat_use_case.py`, `dtos.py`, `index.html` | 9 test endpoint; **12/12** Chrome headless (hai phía CSKH ↔ khách) |
| **Hộp thư thành trang riêng** (07/11): `…/inbox` thay chỗ khung chat; danh sách + chi tiết (hội thoại dẫn tới câu đó, qua `GET /v1/rag/tickets/{id}/conversation`, chỉ admin, chặn phiên khác tenant); trả lời bằng Hỏi – Đáp mở Library đè lên trang và quay lại đúng trang; điện thoại: danh sách ↔ chi tiết | `index.html`, `chat_router.py`, `mongo_session_repo.py` | 4 test endpoint; **18/18** Chrome headless (cả màn điện thoại); tab Nguồn dữ liệu 17/17 |
| **Hộp thư ra thanh trên cùng** (07/11): bỏ tab "Chưa trả lời" khỏi Library (Library chỉ còn 4 tab dữ liệu); nút 📥 có số đỏ cạnh Search, bảng thả xuống 8 mục mới nhất + "Xem tất cả" (`…/inbox`, link cũ `…/knowledge/inbox` vẫn mở được); hộp thư theo dự án đang chọn; "Thêm Hỏi – Đáp" mở Library đúng kho | `frontend/solutions/rag/index.html` | **13/13** kiểm tra Chrome headless (kho riêng dự án); tab Nguồn dữ liệu vẫn 17/17 |
| **Màn hình Nguồn dữ liệu** (07/11): tab thứ 5 trong "Quản lý & Nạp tài liệu"; thêm/sửa/xóa, Thử kết nối (chọn trường bằng cách bấm), Đồng bộ có theo dõi, lịch sử, tạm dừng | `frontend/solutions/rag/index.html`, `POST /v1/knowledge/sources/preview` | **17/17** kiểm tra trên Chrome headless với stack cô lập; không có lỗi JS |
| **D1+T1+T2: kho bảng + truy vấn bảng bằng code** (lọc / đếm / liệt kê / tổng; đọc cùng mẫu bảng ở mọi tài liệu; loại dòng tổng; ô gộp không cộng trùng) | `components/table_store.py`, `components/table_query.py`, `repositories/mongo_table_repo.py`, ingestion, xóa tài liệu, route `table_query` trong chat | **15/15** câu bảng DG233 đúng đáp án (khi kế hoạch đúng); 8 test. Planner LLM chưa đo (cần server); cần re-index để có kho bảng |
| **#3 / #21: Chữ và ảnh đi liền theo bước** (07/11): loại bỏ việc gom ảnh xuống cuối ("Hình ảnh trong tài liệu"); đan xen ảnh minh họa ngay dưới từng bước/đoạn theo ngữ cảnh và markdown inline | `media_assets.py`, `prompt_builder.py`, `chat_use_case.py` | 14 test `test_rag_document_images.py` PASS |
| **#11 / #22: Thay phiên bản tài liệu** (07/11): upload thay thế bản cũ (`replaces_doc_id`), tự tăng version, chuyển bản cũ sang `SUPERSEDED`, dọn sạch vector Qdrant và bảng của bản cũ tránh trả lời nhầm | `knowledge_use_case.py`, `knowledge_router.py`, `dtos.py`, `index.html` | test `test_rag_document_versioning.py` PASS |
| **#17: Cấu hình kênh hỗ trợ theo tenant** (07/11): lưu hotline, kênh điều khiển từ xa (UltraViewer/AnyDesk) và hướng dẫn kết nối; giao diện cấu hình trực quan; cấm xin mật khẩu UltraViewer trong chat | `support_config.py`, `mongo_support_repo.py`, `knowledge_router.py`, `chat_use_case.py`, `index.html` | test `test_rag_support_config.py` PASS |
| **#19: Nhập Hỏi – Đáp hàng loạt từ Excel** (07/11): tải file mẫu `.xlsx`, upload nạp hàng loạt cặp Hỏi – Đáp vào Mongo và Vector DB | `knowledge_use_case.py`, `knowledge_router.py`, `index.html` | test `test_rag_qa_excel_import.py` PASS |
| **#37 & #12: Quy tắc định dạng câu hỏi & Chọn phòng ban** (07/11): bộ chọn phòng ban (DVKH, QLDV, Kỹ thuật) trên thanh chat; quy tắc trình bày: câu lỗi/HDSD có checklist + hotline nổi bật, câu nâng cấp có căn cứ/nội dung mới | `prompt_builder.py`, `index.html` | test pipeline PASS |
| **#5: Hướng dẫn chuẩn bị tài liệu gửi DVKH** (07/11): tài liệu markdown 8 phần chuẩn mực cho khách hàng (quy chuẩn Word/PDF/Excel, ảnh minh họa từng bước, bảng, từ viết tắt, checklist 6 bước) | `docs/HUONG_DAN_CHUAN_BI_TAI_LIEU_CHATBOT.md` | Tài liệu hoàn chỉnh gửi DVKH |

---

## 1. Tầng dữ liệu (bước 1): phải xong trước bước 2

| # | Việc | Vì sao | Cách làm | Tiêu chí đạt | Loại |
|---|---|---|---|---|---|
| D1 | ✅ (code xong, chờ re-index) **Trích dữ liệu bảng có cấu trúc lúc nạp** (A6) | Bảng chỉ lưu dạng text; lúc hỏi mới parse lại → đếm/liệt kê thiếu (lỗi 34 tin), bị giới hạn 2 tài liệu / 300 chunk | Lúc ingest: mỗi bảng → các dòng (tài liệu, mục/breadcrumb, tên cột phẳng, giá trị, cờ dòng tổng, cột gộp dọc) lưu vào kho riêng (Mongo collection theo tenant). Re-index | Mọi bảng của DG233 + bản tin có trong kho; số dòng khớp bản gốc 100% | Local · **Duyệt** (kiến trúc) |
| D2 | ⏳ còn 3/20 câu sai dấu ("chỉ cục", "tôi đa"); câu hỏi ND-01..04 đã có căn cứ | OCR ≥ 95% khớp nguyên câu | Tesseract dừng ở 85% (nhầm "chi cục" → "chỉ cục", "tối" → "tôi") | Phương án: VietOCR (cần PyTorch CPU) hoặc mô hình ngôn ngữ tiếng Việt cho hậu xử lý. Bị chặn cài ở local | DQ4 ≥ 95% trên `dg233_v1.index_checks.json` | Server/Local · **Duyệt** (dependency) |
| D3 | ✅ (image `aip-rag:ocr-test`, 962 MB: DQ1 99,6% · DQ2 100% · DQ3 22/22 · DQ5 25/25 · DQ4 85%) Build lại image RAG có Tesseract | Dockerfile đã sửa, chưa build | `docker compose build rag-worker rag-api` | DQ3 = 100% trong container | Local |
| D4 | Chạy cổng dữ liệu cho **Khung AI** và **bản tin Đắk Lắk** | Hai tài liệu gây lỗi thật chưa qua cổng | Cần 2 file gốc (đang ở MinIO msp) | DQ1–DQ5 đạt | Local (cần file) |
| D5 | Dọn tài liệu trùng cũ | Bản tin bị index 2 lần (5+5=10) | `scripts/backfill_rag_content_hash.py --write-hash`, rồi `--delete-duplicates` | 0 nhóm trùng | Server · **Duyệt** (xóa dữ liệu) |
| D6 | Deploy các bản sửa + re-index toàn bộ | Bản sửa chưa có tác dụng trên dữ liệu đang chạy | `make deploy-server`, re-index tài liệu | Cổng dữ liệu đạt trên server | Server · **Duyệt** |
| D7 | Thêm điểm kiểm tra cho cổng | DQ5 mới có 25 điểm; DQ2 chỉ kiểm tra "có tên cột", chưa kiểm tra "tên cột đúng" | Rút điểm kiểm tra từ 151 câu Khung AI + 49 câu DG233; kiểm tra tên cột so với nguồn gốc | ≥ 100 điểm kiểm tra | Local |

---

## 2. Thuật toán (bước 2): không cần model

| # | Việc | Bằng chứng | Cách làm | Tiêu chí đạt | Loại |
|---|---|---|---|---|---|
| T1 | ✅ (code xong; planner chưa đo trên LLM thật) **Đếm / liệt kê / so sánh bằng code trên kho bảng** (dùng D1) | Lỗi 34 tin; câu trên nhiều tài liệu không trả lời đủ | Route `numeric`/`structured` truy vấn kho bảng thay vì parse chunk; bỏ giới hạn 2 tài liệu / 300 chunk cho câu loại này | ≥ 99% câu đếm/liệt kê của DG233 + bản tin | Local · sau D1 |
| T2 | ✅ Không cộng trùng giá trị ô gộp dọc và dòng Tổng | "Số tin/bài" lặp mỗi dòng; dòng "Tổng" lẫn vào dữ liệu | Dùng cờ ô gộp / dòng tổng từ D1 | Test với bảng mô phỏng | Local · sau D1 |
| T3 | ✅ Fallback khi analyzer timeout không ghép câu trước vào | "HI" → "câu trước — HI" | Thử truy xuất câu gốc trước; chỉ ghép khi câu gốc không có căn cứ | Test | Local |
| T4 | ✅ (5/5 trên quy chế thật) Câu tham chiếu mơ hồ → hỏi lại | "Điều 7" có 2 nghĩa (QC-10) | Khi kết quả tốt nhất thuộc ≥ 2 văn bản con khác nhau cùng tên mục → hỏi lại / nêu cả hai | QC-10 đạt | Local |
| T5 | Hai nguồn mâu thuẫn → nêu cả hai | Excel "trên 70%" so với Quy chế "100%" (QC-15) | Phát hiện cùng mục, khác số liệu giữa các tài liệu → trả lời kèm cả hai nguồn | QC-15 đạt | Local (logic) / Server (đo) |
| T6 | ⚠️ Đổi hướng (xem 3b): không giảm nhiễu; A/B **nới** context khi có model lớn – Giảm context nhiễu (precision 39,8%) | iter5 | Đo vì sao từng passage được chọn hay bị loại; chỉnh ngưỡng chọn context | Precision ≥ 80%, recall không giảm | **Server** (cần embedding + reranker) |
| T7 | ✅ đã đo: không phải nguyên nhân (xem 3b) – Kiểm tra mã / số sau khi sinh | 61 câu có mã lạ (iter5) | Đo `answer_verifier` bỏ sót trường hợp nào rồi siết lại | Mã lạ ≈ 0 | Local (logic) / Server (đo) |
| T8 | Đo độ nhất quán ("túi mù") | Chưa từng đo | Mỗi câu hỏi 5 lần (và 2–3 cách diễn đạt) → tỷ lệ cùng đáp án | ≥ 95% nhất quán | **Server** |

---

## 3. Model và hội thoại (cần LLM)

| # | Việc | Ghi chú | Loại |
|---|---|---|---|
| M1 | A/B model: Qwen2.5-7B (baseline) → Gemma 3 12B → Qwen3-14B | Cùng benchmark; so tỷ lệ đúng, bước sinh câu trả lời, thời gian. Nhớ `RAG_QUERY_ANALYSIS_TIMEOUT=30`, `RAG_LLM_MAX_CONCURRENT=1` | **Server** |
| M2 | Tách model chấm (judge) khỏi model trả lời; chấm tay 120 câu còn thiếu | Điểm hiện tại không đủ tin cậy | **Server** + người chấm |
| M3 | Câu đính chính bị hiểu thành câu hỏi mới (H3: "thiểu 22 mà") | Bản sửa "HI" không bắt được ca này | Server (đo) |
| M4 | ✅ Analyzer đổi "voi" thành "với" khi viết lại câu | Thấy trong trace phiên 41ba0c1d | Local (logic) |
| M5 | Kiểm chứng bản sửa "HI" với model thật | Mới có unit test | **Server** |

---

## 3b. Kết luận phân tích offline trên trace iter5 (Khung AI, 06/11/2026)

Đo bằng dữ liệu đã ghi, không cần server. Script: `scratchpad` (ctx_analysis, fail_taxonomy, missing_points, widen_replay).

| Giả thuyết | Kết quả đo | Quyết định |
|---|---|---|
| Context nhiễu (precision 29–40%) gây trả lời sai | **Bác bỏ**: trong các lượt context đã có căn cứ, context nhiễu đạt 47%, context sạch 29% (mẫu nhỏ). Thu gọn context làm recall giảm 96% → 87–92% | **Không** thu gọn context |
| 69 câu trượt do đâu | 64% thiếu ý chính · 13% từ chối dù có căn cứ · 10% liệt kê thiếu · 6% sai mã · 3% chỉ ngầm trong mã · 4% khác | |
| 80 ý chính bị thiếu nằm ở đâu | **57% có trong context nhưng model bỏ qua** · 36% đã truy xuất nhưng không được chọn vào context · 6% không truy xuất được | Nút cổ chai chính là **bước sinh của model 7B** |
| Nới chọn context có cứu được ý bị thiếu | Nới ngưỡng điểm: 72% → 75%. Lấy thêm 16 đoạn bất kể điểm: 92%, nhưng context dài ×3,6 (~10k ký tự) | **A/B khi có model 12k context** (T6): thử `RAG_CONTEXT_MAX_CHUNKS`, cutoff thấp hơn |
| 8 câu "từ chối dù có căn cứ" do gate | **Không**: cả 8 đều qua gate; căn cứ đứng hạng 1–2; model tự từ chối (`generation_refusal`) | Sửa ở model/prompt (M1), không chỉnh gate |
| "61 câu có mã lạ" là lỗi bịa | **Không**: chủ yếu là khối gợi ý do code thêm (75 câu) và hotline giả (25 câu, đã gỡ). Khối "Ngoài ra…" đúng chủ đề 81% | Không đổi verifier (T7 đóng) |

## 3c. Đợt sửa 07/11/2026

| Việc | Kết quả đo |
|---|---|
| Truy xuất BM25 trên dữ liệu đã xử lý (DG233, 22 câu có căn cứ, ~1.380 chunk) | Recall@5 36% → **68%**, Recall@10 45% → **95%**, Recall@20 55% → **100%**, MRR 0,235 → 0,462 |
| Tài liệu cùng mẫu: chunk không mang tên tài liệu → đưa tên tài liệu vào text tìm kiếm (`chunk_search_text`) | VT-08 hạng 35 → 6, VT-01 23 → 7. **Cần re-index** |
| Bảng bản tin dựng lại từ 42 dòng thật (header 2 tầng, ô gộp, dòng Tổng) qua kho bảng | **5/5**: tích cực 5, tiêu cực 3, trung tính 34, liệt kê đủ 34 tiêu đề, tổng số bài 42 (route cũ: 10, 20, liệt kê tên nguồn) |
| Ô gộp: hai nguồn liền nhau cùng số bài; dòng Tổng của bảng chỉ có cột gộp | Đã sửa (`merged_heads`) |
| Công cụ re-index | `scripts/reindex_rag_documents.py` (mặc định chỉ liệt kê; `--apply` để gửi vào hàng đợi worker). **Dọn trùng (D5) trước rồi mới re-index** |
| Đính chính "thiểu 22 mà" (M3) | Trace cho thấy bot giữ 3 tin tiêu cực là **đúng tài liệu**; lỗi thật của phiên đó là các con số sai của route cũ (10, 20), đã sửa bằng kho bảng. Analyzer không gắn cờ phản bác → cần đo với model mới |

## 3d. Hạ tầng (server msp) – trạng thái 07/11/2026

| Việc | Trạng thái | Ghi chú |
|---|---|---|
| Chống sập sau sự cố 05/11 (RAM 8 GB cạn, model 7B mmap giữ 81% RAM, ổ gần đầy) | **Code có** (commit c08e6b6): MemoryMax + tự khởi động lại từng model, earlyoom, giới hạn RAM container, `--no-mmap`, kiểm tra ổ/RAM trước deploy, swap 2 GB | **Chưa xác minh đã cài trên msp** (`deploy/onprem/host/scripts/install.sh` cần sudo). Kiểm tra: `systemctl status earlyoom`, `systemctl show aip-model@chat -p MemoryMax`, `docker inspect aip-rag-worker --format '{{.HostConfig.Memory}}'`, `swapon --show` |
| Đo hiệu suất sau khi gia cố | **Công cụ xong, diễn tập local PASS** | Một lệnh: `deploy/testing/scripts/server_gate.sh` (preflight → steady → burst → nạp tài liệu dưới tải → OOM/restart). Diễn tập không GPU: `scripts/loadtest_local.sh <thư mục 3 tài liệu>`. Tiêu chuẩn: `.claude/skills/rag-production-quality/infra-standard.md` |
| Kubernetes | **Không dùng cho lab** | msp chạy docker compose + systemd. `deploy/kubernetes/helm`, `deploy/kubernetes/manifests` có sẵn nhưng chưa chạy/kiểm thử; không liên quan vụ sập. Xét lại khi lên server lớn |
| OCR trong worker | **Đã đo**: đỉnh ~247 MB / giới hạn 768 MB; 22 trang scan 44 s (CPU laptop) | Không cần nâng giới hạn |
| Image RAG lớn hơn | 729 MB → **962 MB** (+Tesseract) | Ổ msp từng gần đầy: `deploy_server.sh` chặn khi < 6 GB trống; chạy `deploy/onprem/host/scripts/disk_report.sh` trước |
| Model 14B / 12B | VRAM ~11,5 GB / 12 GB (ước tính) | 1 slot; nếu không khởi động được → embedding/rerank sang CPU (`-ngl 0`) |
| Re-index | Tải lên embedding runtime | `reindex_rag_documents.py --apply --delay 2`, theo dõi RAM/VRAM khi chạy |

### Lỗi hạ tầng tìm ra nhờ diễn tập (07/11)

| Lỗi | Sửa |
|---|---|
| Worker thoát khi RabbitMQ chưa nhận kết nối lúc khởi động | Chính sách `restart: unless-stopped` (đã có trên server, thiếu ở diễn tập); cổng phát hiện container dừng |
| **Circuit breaker LLM mở sau mỗi đợt đông người** dù runtime khỏe: lời gọi bị chính RAG huỷ vì quá hạn (CancelledError) bị tính là lỗi runtime → mọi người bị báo "bận" thêm thời gian cooldown | `runtime_guard.py`: huỷ từ phía gọi không tính là lỗi; timeout HTTP thật vẫn tính. Test `test_calls_cancelled_by_their_caller_do_not_open_the_breaker` |
| OCR không giới hạn (file scan vài trăm trang giữ worker) | `RAG_OCR_MAX_PAGES` (300), `RAG_OCR_PAGE_TIMEOUT_SECONDS` (60); trang bỏ qua ghi lên tài liệu; quá giờ không rơi sang OCR dự phòng không giới hạn |
| Giới hạn lượt chat (6) không khớp model 1 slot | `RAG_CHAT_MAX_INFLIGHT=3` trong `chat-qwen3-14b.env` |

## 4. Thứ tự đề xuất khi làm ở local

1. **D1 → T1 → T2** (kho bảng có cấu trúc + đếm/liệt kê bằng code): kéo điểm nhiều nhất.
2. **D3, D7, T3, T4, M4**: nhỏ, làm nhanh.
3. **D4**: khi có file Khung AI + bản tin.
4. Khi server bật: **D5, D6 → M1 → T6, T7, T8, M2**, chạy benchmark trước/sau ở mỗi bước.
