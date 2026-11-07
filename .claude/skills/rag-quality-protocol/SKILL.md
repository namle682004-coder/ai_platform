---
name: rag-quality-protocol
description: MUST be read first, before writing or changing any code of the AIP RAG (solutions/rag, benchmarks/rag) — bug reports, wrong/incomplete/fabricated answers, new document types, new question types, tuning. Defines the coverage matrix (data shape × question type), the class-level fix protocol, the no-fabrication invariants, the definition of done and how to report back. Other rag-* skills are loaded after this one for the layer concerned.
---

# RAG Quality Protocol (đọc trước mọi thay đổi RAG)

Mục tiêu sản phẩm: **trả lời đúng và đủ theo tài liệu, không bịa**. Chất lượng được đo theo từng ô của ma trận bao phủ, không đo bằng cảm giác từ vài câu hỏi thử.

Ma trận và trạng thái hiện tại: [coverage-matrix.md](coverage-matrix.md). Đọc nó trước khi làm.

## Nguyên tắc 1: sửa theo LOẠI, không sửa theo TÀI LIỆU

Mỗi lỗi phải được gọi tên theo **loại**, ví dụ "bảng có tiêu đề gộp nhiều tầng", "câu đính chính bị hiểu thành câu hỏi mới", "tài liệu bị nạp trùng". Không gọi tên kiểu "bản tin Đắk Lắk trả lời sai".
- Một bản sửa đúng phải làm đúng cho **mọi** tài liệu cùng dạng.
- Cấm: từ khóa, regex, tên cột, tên mục hay ngưỡng chỉnh riêng theo một tài liệu hay một tenant. Nếu cần tri thức theo miền thì lấy từ cấu hình tenant hoặc từ chính tài liệu (thống kê, cấu trúc), không viết cứng vào code.
- Test của một loại lỗi dùng **dữ liệu tổng hợp** có cùng cấu trúc (fixture tự tạo), không chép nội dung tài liệu của khách.

## Nguyên tắc 2: không bịa (bất biến của mọi route)

1. **Số liệu do code tính**, LLM không được tự cộng hay tự đếm. Đếm, tổng, lớn nhất/nhỏ nhất, xếp hạng phải đi qua dữ liệu có cấu trúc (route `numeric` / `structured`).
2. **Mọi mã, số, tên riêng trong câu trả lời** phải có trong context hoặc là kết quả code tính được. Không thỏa thì bỏ hoặc sinh lại.
3. **Liệt kê phải đủ**: câu "liệt kê tất cả" chỉ được trả lời từ nguồn đã đọc toàn bộ (cả bảng hoặc cả danh sách). Không đủ thì nói rõ là chưa đủ, không được trả về một phần mà giả như là toàn bộ.
4. **Không có căn cứ thì từ chối và chuyển hỗ trợ.** Không bao giờ xin mật khẩu hay thông tin truy cập của người dùng.
5. **Nhất quán trong phiên**: cùng một số liệu thì các lượt phải trả lời giống nhau, vì nguồn là dữ liệu có cấu trúc chứ không phải văn sinh lại.

## Quy trình bắt buộc (mọi task RAG)

1. **Xếp ô**: task thuộc ô nào trong ma trận (dạng dữ liệu × loại câu hỏi), route nào xử lý ô đó (xem cột route).
2. **Bằng chứng**: tái hiện bằng trace hoặc API (`rag-debugging`). Đọc dữ liệu đã index (Qdrant `scroll` theo `doc_id`) để biết lỗi nằm ở dữ liệu hay ở thuật toán, **trước** khi đoán.
3. **Gọi tên loại lỗi** và liệt kê các ô hoặc tài liệu khác cũng dính lỗi đó.
4. **Baseline**: chạy benchmark của các ô bị ảnh hưởng (`rag-evaluation`). Ô chưa có bộ test thì tạo bộ test trước (ít nhất 5 câu một ô, có đáp án do người duyệt).
5. **Sửa** ở tầng của nguyên nhân gốc: dữ liệu (`rag-data-engineering`), thuật toán (`rag-retrieval`), kiến trúc (`rag-architecture`).
6. **Test loại lỗi**: unit test với fixture tổng hợp, cộng với case benchmark.
7. **Chặn hồi quy**: không ô nào được tụt so với baseline. Câu từng đạt mà nay hỏng thì chưa xong.
8. **Cập nhật** `coverage-matrix.md` (trạng thái ô, số đo, ngày).
9. **Báo cáo** theo mẫu bên dưới.

Đổi cách parse hoặc chunk thì phải **re-index** các tài liệu bị ảnh hưởng và ghi rõ điều đó.

## Definition of done

- [ ] Có bằng chứng nguyên nhân gốc (trace hoặc dữ liệu index), không phải phỏng đoán.
- [ ] Lỗi được gọi tên theo loại; bản sửa không chứa tri thức riêng của một tài liệu.
- [ ] Có test của loại lỗi; `make rag-eval-test` và các test RAG liên quan đều pass.
- [ ] Benchmark các ô bị ảnh hưởng: tăng hoặc giữ nguyên, 0 hồi quy. Nếu không chạy được (ví dụ thiếu LLM runtime) thì **ghi rõ là chưa kiểm chứng**.
- [ ] Ma trận đã được cập nhật.

## Mẫu báo cáo cho người dùng

1. **Loại lỗi** và ô ma trận.
2. **Bằng chứng** (trace, dữ liệu index, số liệu).
3. **Đã sửa gì** (file:line) và vì sao bản sửa tổng quát.
4. **Đã kiểm chứng**: test, benchmark trước và sau. **Chưa kiểm chứng**: liệt kê rõ.
5. **Cần người dùng cung cấp** (tài liệu, câu hỏi kèm đáp án, quyền deploy…).

Không nói "đã ổn" hay "đạt X%" khi số đo đến từ một bộ dữ liệu khác với tài liệu đang bàn.

## Ràng buộc môi trường

- Model sinh hiện tại khoảng 7B lượng tử hóa. Thiết kế phải **giảm việc giao cho LLM**: tính toán và liệt kê bằng code, context ngắn và đúng, kiểm tra sau khi sinh. Không dựa vào việc model tự suy luận nhiều bước.
- LLM runtime ở máy dev có thể không chạy; khi đó unit test là bằng chứng tối thiểu, còn kiểm chứng với model thật phải ghi là việc còn lại.
