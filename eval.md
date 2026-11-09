# Hướng dẫn đo chất lượng RAG chatbot

Tài liệu này hướng dẫn cách đo chất lượng chatbot, cách biết chất lượng đang tăng hay giảm, và cách quyết định khi nào được go-live. Chi tiết kỹ thuật của công cụ nằm ở [benchmarks/rag/README.md](benchmarks/rag/README.md).

## 1. Nguyên tắc

1. **Đo trước, sửa sau.** Không sửa vì "thấy câu này sai". Mọi thay đổi phải bắt đầu từ báo cáo đo, nhắm vào bước có nhiều lỗi nhất, rồi đo lại toàn bộ.
2. **Một con số không đủ.** Mỗi lần chạy phải xem đồng thời:
   - tỷ lệ đạt và khoảng tin cậy của nó;
   - lỗi nằm ở bước nào;
   - recall theo từng bước;
   - hồi quy so với lần chạy trước.
3. **Không tối ưu riêng cho bộ đang test.** Bộ 151 câu là bộ phát triển. Kết luận go-live phải dựa trên **bộ test mù** (xem mục 6).
4. **Giữ cố định mọi thứ khi so sánh:**
   - cùng dataset (kiểm tra sha256);
   - cùng tài liệu đã index;
   - cùng model judge và cùng phiên bản rubric;
   - cùng chế độ stream hoặc không stream.

   Thông tin này được ghi trong `run.json` của mỗi lần chạy.

## 2. Hệ thống đo gồm những gì

| Lớp | Trả lời câu hỏi | Ở đâu |
|---|---|---|
| Trace từng lượt | Câu này sai ở bước nào? | `GET /v1/rag/traces/{trace_id}` (trace_id có trong header `X-Trace-ID` của mỗi câu trả lời) |
| Bộ nghiệm thu offline | Bot đạt bao nhiêu %? Lỗi tập trung ở đâu? Có hồi quy không? | `benchmarks/rag`, lệnh `make rag-eval` |
| Danh sách ý chính | Câu trả lời phải nêu được những gì thì Đạt? | `make rag-eval-checklist`, đội nghiệm thu duyệt file `.checklist.xlsx` |
| Hiệu chỉnh cách chấm | Có tin được máy chấm không? | `make rag-eval-calibrate` |
| Cổng go-live | Được phát hành chưa? | `benchmarks/rag/configs/gate.yaml` |
| Giám sát online | Sau go-live, chất lượng có tụt không? | Grafana "AIP RAG – Chất lượng & Pipeline", alert `aip_rag_quality_alerts` |

Một câu trả lời đi qua các bước sau. Mỗi bước được ghi vào trace:

```
câu hỏi → query_analysis → retrieval → rerank → gate → (numeric | structured | context → generation → verification → correction) → câu trả lời
```

## 3. Chạy một lần đo

```bash
# 0. Nếu đổi code RAG local: nạp code mới (container mount trực tiếp solutions/rag)
docker restart aip-rag-api

# 1. (Một lần, hoặc khi workbook đổi) chuyển xlsx thành golden JSONL
make rag-eval-import PYTHON=.venv/bin/python

# 2. (Một lần, hoặc khi đáp án kỳ vọng đổi) rút ý chính của từng câu, rồi cho đội nghiệm thu duyệt (mục 3.1)
make rag-eval-checklist PYTHON=.venv/bin/python

# 3. Chạy bộ nghiệm thu: stream giống giao diện thật, xoá cache trước khi chạy
curl -X POST http://localhost:8010/v1/rag/cache/clear -H "X-Tenant-ID: <project_id>"
cd benchmarks/rag/src && PYTHONPATH=../../..:../../../packages/common ../../../.venv/bin/python -m rag_benchmark.cli suite \
  --dataset ../datasets/acceptance/khung_ai_v2.jsonl --api http://localhost:8010 --tenant <project_id> --stream \
  --judge-url http://172.16.20.2:8011/v1 --out-dir ../runs --run-id <tên_lần_chạy> \
  --baseline ../runs/<lần_chạy_trước> --gate ../configs/gate.yaml --calibration ../runs/calibration_khung_ai_checklist.json \
  --grades-from ../datasets/acceptance/khung_ai_v2.calibration.jsonl --grades-from ../runs/<lần_chạy_trước>

# 4. Người chấm các câu xếp đầu review.xlsx (cột "Cần người chấm"), rồi nhập lại
python -m rag_benchmark.cli import-grades --run ../runs/<tên_lần_chạy> --grades ../runs/<tên_lần_chạy>/review.xlsx \
  --gate ../configs/gate.yaml --calibration ../runs/calibration_khung_ai_checklist.json
```

Chạy thử vài câu bằng `--only G01-01,G08` (theo mã câu hoặc mã nhóm) hoặc `--limit 10`.

Chấm lại một lần chạy cũ mà không gọi bot (sau khi đổi cách chấm hoặc duyệt thêm ý chính): `cli regrade --run ../runs/<lần_chạy>`. Kết quả ra thư mục mới `<lần_chạy>-checklist`.

### 3.1. Máy chấm thế nào, người chấm phần nào

Bot và máy chấm dùng chung Qwen2.5-7B. Model 7B không chấm nổi cả câu trả lời trong một lần (khớp với người 53%, kappa 0.03). Vì vậy máy chấm theo kiểu **danh sách ý chính** (`--grader checklist`, mặc định):

1. **Ý chính của từng câu:** đáp án kỳ vọng được rút thành tối đa 3 ý bắt buộc (lớp nào, mã nào, có hay không, con số…). Lệnh `checklist` cho model nháp; **đội nghiệm thu duyệt** trong `datasets/acceptance/<bộ>.checklist.xlsx`:
   - sửa cột "Ý chính", mỗi dòng một ý;
   - đánh `x` vào cột "Đã duyệt";
   - nhập lại: `cli checklist --dataset … --import-xlsx …checklist.xlsx`.

   Ý đã duyệt không bao giờ bị máy ghi đè. Người chấm tay cũng dựa vào đúng danh sách này, nên tiêu chuẩn "Đạt" là một, máy và người như nhau.
2. **Chấm từng ý:**
   - **so khớp trước**: ý có mã thì mã phải có trong phần trả lời chính (bỏ phần Nguồn / Gợi ý); ý chữ thì chữ đã chuẩn hoá phải nằm trong câu trả lời;
   - **chỉ khi so khớp không quyết được** mới hỏi model một câu có / không / mâu thuẫn cho đúng ý đó.

   Đủ mọi ý thì Đạt. Thiếu hoặc mâu thuẫn một ý thì Không đạt.
3. **Câu tài liệu không có thông tin:** quyết bằng code, không cần model. Đạt khi bot từ chối hoặc chuyển hỗ trợ (có mã `ticket_…`).
4. **Kiểm tra cứng mặc định:** `wrongly_refused`, `artefacts`. Thiếu mã không còn tự động trượt, vì người chấm vẫn cho Đạt khi câu trả lời đúng ý mà thiếu một mã. Mã lạ (mã không có trong câu hỏi hay đáp án) chỉ đưa câu vào hàng chờ chấm tay, không đánh trượt: bật thành kiểm tra cứng thì độ khớp tụt từ 73% xuống 61%.

**Phần người chấm.** `review.xlsx` xếp lên đầu các câu có cột "Cần người chấm" khác rỗng:
- máy chưa có kết luận;
- kết luận dựa vào model (ý nào đó phải hỏi 7B);
- câu trả lời có mã lạ.

Câu do so khớp quyết thì máy đã khá chắc (khớp người 85%).

**Giữ điểm người chấm.** `--grades-from` (file calibration, hoặc thư mục một lần chạy đã nhập điểm tay): câu trả lời **giống hệt** câu đã có người chấm thì dùng lại điểm đó, sau khi bỏ khoảng trắng thừa và che mã ticket. Mỗi câu trả lời khác nhau chỉ cần người chấm một lần. Sau vài vòng, mỗi lần sửa bot chỉ còn vài chục câu mới phải chấm.

`--grader rubric` là cách cũ: judge chấm cả câu một lần, chỉ dùng khi có model judge mạnh. Lần chạy và calibration phải dùng **cùng** cách chấm, model, kiểm tra cứng và `--id-policy`. Cổng go-live tự kiểm tra điều này.

Kết quả nằm trong `benchmarks/rag/runs/<tên_lần_chạy>/`:

| File | Đọc để làm gì |
|---|---|
| `report.md` | Báo cáo chính: tỷ lệ đạt, **hạn chế chính** (câu trượt gom theo loại lỗi, kèm ví dụ và chỗ cần xem), bước lỗi, recall theo bước, nhóm, latency, danh sách câu trượt kèm trace id |
| `summary.json` | Toàn bộ số liệu dạng máy đọc được (dùng để so sánh nhiều lần chạy) |
| `gate.json` | Kết luận GO / NO-GO và từng tiêu chí |
| `review.xlsx` | Chấm tay những câu máy chưa quyết được, hoặc câu muốn kiểm tra lại |
| `traces/<mã câu>/s<phiên>_t<lượt>.json` | Trace đầy đủ của từng lượt, để mổ xẻ lỗi |

## 4. Đọc báo cáo: lỗi nằm ở đâu

### 4.1. Bảng "Lỗi nằm ở bước nào"

Mỗi câu trượt được quy về bước **đầu tiên làm mất căn cứ** (mã bắt buộc hoặc trích dẫn):

| Bước | Nghĩa là | Thường sửa ở |
|---|---|---|
| `ingestion` | Căn cứ không có trong chunk nào đã index | Parser hoặc chunker, rồi index lại |
| `routing` | Câu bị hiểu là chit-chat / hỗ trợ / không rõ, nên không truy xuất tài liệu | Query analyzer |
| `retrieval` | Có trong index nhưng không lọt vào ứng viên tìm kiếm | Hybrid search, BM25, multi-query, focus retrieval |
| `rerank` | Có trong ứng viên nhưng bị xếp dưới top-k | Reranker, câu truy vấn đưa vào rerank |
| `gate` | Đã tìm thấy căn cứ nhưng gate vẫn từ chối | Ngưỡng gate |
| `context` | Qua gate nhưng không được đưa vào prompt, hoặc bị nhét lẫn đoạn nhiễu | Chọn context, window fitting |
| `verification` | Model viết đúng nhưng bộ kiểm chứng cắt mất câu | answer_verifier |
| `generation` | Prompt đã có đủ căn cứ mà model vẫn trả lời sai, thiếu hoặc lẫn | Prompt, đường xử lý bằng code (bảng, danh sách, số liệu), model mạnh hơn |
| `undiagnosed` | Câu không có căn cứ vàng, hoặc không lấy được trace | Bổ sung mã căn cứ vào dataset |

**Cách dùng:** bước nào có nhiều câu trượt nhất thì sửa bước đó trước. Một thay đổi ở bước `context` có thể sửa hàng chục câu một lúc. Sửa từng câu một thì không làm được như vậy.

### 4.2. Recall theo từng bước

Bảng "Truy xuất theo từng bước" cho biết căn cứ vàng còn lại bao nhiêu phần trăm sau mỗi bước:

```
Index 100% → Retrieval 98% → Rerank@k 95% → Context 93% → Answer 80%
```

Chỗ tụt mạnh nhất là chỗ cần sửa. Ví dụ trên tụt mạnh từ Context xuống Answer, tức lỗi nằm ở khâu sinh câu trả lời. Ngoài ra:

- **Context precision thấp** (ví dụ 20%) nghĩa là prompt có quá nhiều đoạn không liên quan. Model 7B rất dễ bị lẫn khi context nhiễu.
- **MRR rerank** cho biết căn cứ đúng có đứng đầu danh sách không.

### 4.3. Mổ xẻ một câu

Lấy trace id trong `report.md` hoặc `review.xlsx`, rồi mở `traces/<mã câu>/...json` hoặc gọi:

```bash
curl -s http://localhost:8010/v1/rag/traces/<trace_id> -H "X-User-Role: admin" -H "X-Tenant-ID: <project_id>"
```

Những gì cần xem trong trace:

| Stage | Xem gì |
|---|---|
| `query_analysis` | `intent`, `standalone_query`, `focus` / `scope`: bot hiểu câu hỏi thế nào |
| `retrieval` / `rerank` | Từng chunk kèm `ids` (mã có trong chunk), `score`, `heading` |
| `gate` | `decision`, `top_rerank`, `best_lexical` so với ngưỡng |
| `context` | Các chunk thật sự đưa vào prompt, và `user_content` (kèm các ghi chú kiểm tra tiền đề) |
| `generation` | `raw_answer`: model viết gì trước khi kiểm chứng |
| `verification` / `correction` | Câu bị cắt kèm lý do (`identifier:…`, `number:…`, `unit:…`), gợi ý sửa, và bản sinh lại có được chấp nhận không |

### 4.4. Người dùng chê câu trả lời trên production

Khi người dùng bấm dislike, feedback được gắn vào trace tương ứng. Lấy danh sách:

```bash
curl -s "http://<host>:8010/v1/rag/traces?feedback=negative&limit=100" -H "X-User-Role: admin" -H "X-Tenant-ID: <project_id>"
```

Mỗi trace có sẵn chẩn đoán bước lỗi. **Mỗi tuần, chuyển các câu bị chê thành case mới trong golden set.** Bộ test vì thế lớn dần theo câu hỏi thật của người dùng.

## 5. Biết chất lượng đang lên hay xuống

### 5.1. Mỗi thay đổi code hoặc cấu hình

1. Chạy bộ đầy đủ, truyền `--baseline` là lần chạy tốt gần nhất.
2. Đọc phần "So với lần chạy trước" trong `report.md`:
   - **Hồi quy** (trước đạt, nay trượt): phải bằng 0. Nếu có thì xem trace và sửa trước khi merge.
   - **Đã sửa** (trước trượt, nay đạt): đây là phần tăng thật.
3. Tỷ lệ đạt tăng nhưng có hồi quy thì **chưa phải tiến bộ**. Có thể bạn chỉ đổi lỗi chỗ này sang chỗ khác.

### 5.2. Phân biệt tiến bộ thật với dao động ngẫu nhiên

LLM không cho kết quả giống hệt nhau mỗi lần chạy (temperature, batch phía runtime). Trước khi tin một mức tăng nhỏ:

- **Đo độ dao động một lần:** chạy cùng một phiên bản code 2 lần, lần sau dùng `--baseline` là lần trước. Câu nào đổi kết quả giữa hai lần là **câu chập chờn**. Số câu chập chờn chính là sai số tự nhiên của bộ test.
- **Một thay đổi chỉ được coi là tiến bộ khi:**
  - số câu "đã sửa" lớn hơn số câu chập chờn;
  - không có hồi quy;
  - nhóm liên quan tăng;
  - recall ở bước bạn sửa tăng.
- **Khoảng tin cậy:** báo cáo in khoảng tin cậy Wilson 95%. Với 151 câu, mức đạt 95% có cận dưới khoảng 90%. Muốn khẳng định chắc chắn mức ≥ 95%, cần bộ test lớn hơn (từ 300 câu trở lên) hoặc dùng thêm tiêu chí `min_pass_rate_ci_low` trong `gate.yaml`.

### 5.3. Theo dõi xu hướng

Giữ một bảng (hoặc so `summary.json`) cho mỗi lần chạy. Mỗi lần chạy là một dòng, gồm các cột:

| Cột | Ý nghĩa |
|---|---|
| Lần chạy | Tên lần chạy |
| Commit | Mã commit của code |
| Tỷ lệ đạt | Kèm khoảng tin cậy |
| Bước lỗi top 3 | Ba bước có nhiều câu trượt nhất |
| Recall theo bước | Index → Retrieval → Rerank → Context → Answer |
| Context precision | Tỷ lệ đoạn liên quan trong prompt |
| Hồi quy / Đã sửa | Số câu mỗi loại so với lần trước |
| p95 latency, p95 TTFT | Độ trễ tổng và thời gian ra chữ đầu |

Chất lượng đang lên khi:
- tỷ lệ đạt tăng đều;
- các bước lỗi top 3 thu nhỏ dần;
- hồi quy luôn bằng 0.

## 6. Quy trình go-live (≥ 95%)

1. **Hiệu chỉnh cách chấm:** chạy `make rag-eval-calibrate` (chạy lại mỗi khi danh sách ý chính được duyệt thêm). Kết luận của máy chỉ được dùng cho go-live khi:
   - mức khớp với chấm tay ≥ 85%;
   - tỷ lệ cho đạt sai (người chấm Không đạt, máy cho Đạt) ≤ 10%.

   Với Qwen-7B hiện chưa đạt mức này (73%, mục 7.3). Vì vậy **kết luận go-live phải là điểm của người** cho mọi câu: máy chỉ để biết nhanh đang tốt lên hay xấu đi. Nhờ giữ điểm cho câu trả lời không đổi, đợt chấm cuối chỉ gồm các câu mới thay đổi.
2. **Bộ phát triển** (151 câu): đạt cổng `gate.yaml`, gồm:
   - tổng ≥ 95%;
   - mỗi nhóm ≥ 80%;
   - nhóm bắt buộc (G11, G14, G15, G16, G30) đạt 100%;
   - không bịa khi tài liệu không có thông tin;
   - không hồi quy.
3. **Chấm tay phần còn lại:** mở `review.xlsx`, điền cột "Chấm tay", rồi chạy `cli import-grades --run … --grades …`. Cổng được đánh giá lại với kết luận của người chấm.
4. **Bộ test mù:** chạy đúng **một lần** trên bộ câu hỏi đội nghiệm thu tự viết, chưa ai trong đội phát triển xem. Kết quả lần này mới là con số dùng để go-live.
5. **Sau go-live:** theo dõi dashboard và alert. Mỗi tuần đưa các câu bị chê vào golden set, rồi chạy lại bộ đầy đủ trước mỗi lần deploy.

## 7. Baseline ngày 05/11/2026 (local, Qwen2.5-7B Q4, chế độ stream)

Lần chạy: `benchmarks/rag/runs/baseline_khung_ai_20261105/` và `baseline_enterprise_20261105/`. Cổng go-live: **NO-GO**.

### 7.1. Bộ KHUNG AI (151 câu)

| Chỉ số | Kết quả | Ghi chú |
|---|---|---|
| Tỷ lệ đạt, quy tắc mã `all` | **43.0%** (KTC 95%: 35–51%) | 65 đạt / 86 trượt |
| Tỷ lệ đạt, quy tắc mã `any` | 49.7% | Nếu chỉ cần có ít nhất 1 mã căn cứ |
| Trượt do kiểm tra cứng (chắc chắn đúng) | 60 câu | Phần lớn là thiếu mã bắt buộc, 8 câu từ chối sai |
| Trượt chỉ do judge | 26 câu | Không đáng tin, xem mục 7.3 |
| Nhóm bắt buộc trượt | G11-03/04/05, G15-02/03, G16-03/04/05 | |
| p95 tổng / p95 ra chữ đầu | 13.1s / 12.1s | Bộ verifier giữ chữ lại đến cuối câu, nên chữ đầu ra gần như cùng lúc với câu trả lời hoàn chỉnh |

Recall theo từng bước (111 lượt có mã căn cứ):

| Index | Retrieval | Rerank@k | MRR | Context | Context precision | Answer |
|---|---|---|---|---|---|---|
| 100% | 97.3% | 94.8% | 0.887 | **80.3%** | **22%** | **50.9%** |

Câu trượt theo bước:

| Bước | Số câu |
|---|---|
| `generation` | 55 |
| `context` | 17 |
| `verification` | 9 |
| `routing` | 3 |
| `rerank` | 1 |

**Đọc kết quả:** parse, index và tìm kiếm đã tốt. Điểm mất nằm ở 3 chỗ, xếp theo mức ảnh hưởng:

1. **Bước sinh câu trả lời (`generation`) mất khoảng 30 điểm recall.** Prompt có căn cứ mà model 7B chỉ viết ra khoảng nửa số mã, hoặc lẫn mã giữa các lớp. Ví dụ "RAG học lớp mấy" bị trả lời thành "lớp 12".
2. **Bước dựng context mất 15 điểm recall và có 78% đoạn nhiễu** (context precision 22%).
   - Bước này làm rơi căn cứ mà rerank đã xếp lên đầu.
   - Nó còn nhét thêm các đoạn ít liên quan: document card, `min_k`, focus passages.
   - Model 7B rất dễ bị lẫn khi context nhiễu.
3. **Đường structured listing trượt 28/46 lượt.**
   - Bộ lập kế hoạch 7B trả `applicable: true` cho gần như mọi câu, kể cả "Có bao nhiêu mạch?" hay "QĐ 2422 nói về gì?".
   - Nó còn chọn sai nhóm, ví dụ chọn B3 thay vì A2 khi hỏi "nguyên tắc đạo đức".

Lỗi khác tìm thấy:
- **Bản sinh lại sau kiểm chứng** vẫn được đánh dấu "accepted" dù vẫn sai lớp (trace của câu "RAG học lớp mấy").
- **Câu trả lời có token rác:** `ent_diplomacy_001` kết thúc bằng "…2 triệu USD.peci".
- **G16-05:** câu hỏi đòi thông tin cá nhân không bị từ chối.
- **G28-03:** câu hỏi mơ hồ nhiều lượt không được chuyển hỗ trợ.

### 7.2. Bộ enterprise (20 câu, trong đó 8 câu bẫy ngoài tài liệu)

- **8/8 câu bẫy được từ chối đúng,** kể cả câu prompt-injection.
- Judge cho đạt 20/20, nhưng con số này **không có giá trị**: bộ này không có mã căn cứ nên chỉ judge quyết định.
- Recall theo bước, tính lại theo `required_facts`:

| Rerank@k | Context | Context precision | Answer |
|---|---|---|---|
| 75% | 92% | 52% | 72% |

### 7.3. Công cụ đo chưa đủ chuẩn để quyết định go-live

So bộ chấm tự động với 151 câu đã chấm tay (câu trả lời của lần chạy 03–04/11):

| Bộ chấm | Khớp với người chấm | Cho đạt sai | Đánh trượt sai |
|---|---|---|---|
| Chỉ judge Qwen-7B | 53% (kappa 0.03, tức gần như ngẫu nhiên) | 58% | 38% |
| Kiểm tra cứng + judge, quy tắc `all` | 56% | 22% | 62% |
| Chỉ kiểm tra cứng, quy tắc `any` | 60% | 71% | 17% |

Mục tiêu là khớp ≥ 85% và cho đạt sai ≤ 10%. Hai nguyên nhân khiến chưa đạt:

1. **Judge 7B quá yếu,** sai theo cả hai chiều:
   - cho đạt câu bot từ chối sai, chỉ vì tin lời bot rằng "tài liệu không có";
   - đánh trượt câu bot chuyển hỗ trợ đúng (G20-05, G27-04, G28-04, G28-05).

   Judge lại cùng model với bot, nên không khách quan.
2. **Tiêu chuẩn "Đạt" chưa thống nhất.** Có 28 câu người chấm cho Đạt dù thiếu một phần mã căn cứ. Câu "phải nêu đủ mọi mã trong cột Căn cứ" hay "chỉ cần nêu căn cứ" là quyết định của đội nghiệm thu, cần chốt trước khi đo tiếp.

Vì vậy tỷ lệ đạt 43–50% của baseline chỉ là ước lượng; recall theo bước vẫn dùng được để định hướng sửa.

### 7.4. Chấm theo danh sách ý chính, vẫn dùng Qwen-7B (05/11/2026)

Không có kinh phí nâng model judge, nên cách chấm được đổi (mục 3.1) và đo lại trên cùng 151 câu đã chấm tay. File: `runs/calibration_khung_ai_checklist.json`.

| Cách chấm (cùng Qwen-7B) | Khớp với người | Kappa | Cho đạt sai | Đánh trượt sai |
|---|---|---|---|---|
| Judge chấm cả câu (cách cũ) | 53% | 0.03 | 58% | 38% |
| **Danh sách ý chính, ý nháp chưa duyệt** | **73.5%** | **0.48** | **15%** | 35% |
| – riêng 21 câu không có đáp án (chỉ dùng code) | 95% | | | |
| – riêng 61 câu quyết bằng so khớp | 85% | 0.66 | | 7.5% |
| – riêng 89 câu phải hỏi model | 65% | 0.31 | | 59% |
| Thêm "thiếu mã thì trượt" | 69% | 0.41 | 6% | 50% |
| Thêm "có mã lạ thì trượt" | 61% | 0.28 | 8% | 62% |

Đã thử bổ sung so khớp theo tỉ lệ từ trùng trước khi hỏi model. Độ khớp không tăng (72% khi chọn ngưỡng trên một nửa, đo trên nửa còn lại), chỉ đổi đánh trượt sai thành cho đạt sai, nên không dùng.

**Đọc kết quả:**
- Đã tăng từ mức đoán bừa lên mức đồng thuận vừa phải. Nhưng 73% vẫn dưới mục tiêu 85%, nên máy là **tín hiệu phát triển**, không phải trọng tài go-live.
- Chỗ yếu còn lại là các ý phải hỏi model: 7B hay trả lời "không có" cho ý được diễn đạt khác.
- Phần còn lệch còn do **người chấm chưa nhất quán**. Ví dụ G07-01 và G21-01 cùng thiếu 11.C3.MR3, một câu Không đạt, một câu Đạt. Khi đội nghiệm thu duyệt danh sách ý chính, cả người lẫn máy chấm theo cùng một chuẩn. Sau đó chạy lại `make rag-eval-calibrate`: độ khớp sẽ phản ánh đúng năng lực máy chấm.
- Muốn bớt phần người chấm thì hướng hiệu quả nhất là viết ý chính dạng **mã hoặc cụm từ nguyên văn** của tài liệu (ví dụ "11.C3.MR4", "6 nguyên tắc"). Khi đó so khớp quyết được nhiều ý hơn, không cần hỏi model.

## 8. Dữ liệu và tài nguyên cần bổ sung

Xếp theo thứ tự ưu tiên:

1. **Đội nghiệm thu duyệt danh sách ý chính** trong `datasets/acceptance/khung_ai_v2.checklist.xlsx`: 130 câu, mỗi câu khoảng 1 phút. Đây là việc quan trọng nhất hiện nay, vì nó thống nhất tiêu chuẩn Đạt cho cả người lẫn máy. Máy nháp có chỗ sai, ví dụ G08-01 nháp ra một câu hỏi thay vì một ý.
2. **Chấm tay lần chạy mới theo hàng chờ** (các câu đầu `review.xlsx`), rồi `import-grades`. Điểm tay được giữ cho lần sau nếu câu trả lời không đổi.
3. **Model judge mạnh hơn** (Qwen2.5-32B/72B trên server, hoặc API ngoài nếu chính sách dữ liệu cho phép): chưa có kinh phí, nên tạm thời thay bằng mục 1–2. Khi có, chỉ cần chạy lại `make rag-eval-calibrate` với `--judge-url` mới. Nếu khớp ≥ 85% thì máy được quyết go-live.
4. **Quy tắc chấm rõ ràng cho từng nhóm,** do đội nghiệm thu chốt:
   - thiếu một phần mã thì có trượt không;
   - câu đóng tối đa bao nhiêu câu;
   - khi nào bắt buộc đưa kênh liên hệ.

   Ghi vào cột "FAIL nếu" thật cụ thể. Judge chấm theo đúng cột này.
5. **Bộ test mù 50–100 câu** cho tài liệu KHUNG AI, do người khác viết, không đưa cho đội phát triển. Bộ `enterprise/frozen_test` hiện là **bản sao y hệt** `internal_golden_v2`, nên chưa phải holdout.
6. **Mã căn cứ cho 25 câu còn trống** (G04, G13, G05, G12, G15, G23, G30…). Chỉ cần ghi mã hoặc cụm từ mà câu trả lời bắt buộc phải có. Có căn cứ thì máy mới quy lỗi về đúng bước.
7. **Tài liệu gây nhiễu thật:** nạp thêm 5–10 tài liệu khác vào **cùng project** với KHUNG AI. Production luôn có nhiều tài liệu; hiện mỗi project chỉ có một tài liệu nên retrieval đang được đo trong điều kiện dễ.
8. **Bộ test cho tài liệu dạng bảng và số liệu,** ví dụ bản tin Đắk Lắk: 30–50 câu hỏi về max, min, tổng, chênh lệch, đếm, đơn vị. Đường tính số bằng code đã có nhưng chưa có bộ test nào kiểm tra.
9. **Câu hỏi thật của người dùng** (đã ẩn danh) từ server, khoảng 100 câu, để bộ test phản ánh cách người dùng thật hỏi.

## 9. Thêm bộ test mới

1. Chuẩn bị file xlsx, mỗi câu một dòng, gồm các cột:
   - mã câu, mã nhóm, loại (một lượt / nhiều lượt / 3 phiên riêng);
   - câu hỏi (nhiều lượt viết dạng `Lượt 1: … / Lượt 2: …`);
   - đáp án kỳ vọng;
   - căn cứ: mã hoặc số hiệu, hoặc `—` nếu tài liệu không có thông tin;
   - FAIL nếu.
2. Tạo file `benchmarks/rag/configs/datasets/<tên>.yaml` theo mẫu `khung_ai.yaml`, trong đó ánh xạ tên cột và khai báo nhóm bắt buộc.
3. Chạy `cli import-xlsx`, rồi `cli suite` với tenant chứa đúng tài liệu đó.
