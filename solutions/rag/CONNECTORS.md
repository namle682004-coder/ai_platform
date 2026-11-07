# Connector nguồn dữ liệu (thiết kế)

## Vấn đề

Hiện nay dữ liệu chỉ vào AIP bằng cách upload file. Với dữ liệu sống ở hệ thống khác (bản tin MXH, website nội bộ của khách) thì:
- dữ liệu **cũ** ngay khi upload;
- phải có người xuất file và upload tay;
- bảng phải đọc lại từ docx/pdf, và đó là nguồn lỗi đếm/liệt kê.

## Phương án

Một tầng connector **đọc trực tiếp** nguồn theo lịch, chuẩn hóa nội dung, rồi **đưa vào đúng pipeline ingestion hiện có**: lưu file chuẩn hóa vào MinIO, tạo bản ghi tài liệu, gọi `DocumentIngestionUseCase.ingest_document`. Nhờ vậy nội dung từ connector có đủ mọi thứ của upload: bảng chuẩn, kho bảng, che PII, OCR, chống trùng, re-index, xem file gốc, xóa sạch.

```
rag_sources (cấu hình theo tenant)
   │  scheduler trong worker (lease Mongo: một nguồn chỉ một worker chạy)
   ▼
Connector ── json_api: API JSON có phân trang / cursor / since
          └─ web: website nội bộ (HTML → markdown, bảng → bảng chuẩn; file pdf/docx/xlsx được liên kết)
   │  SourceItem (khóa ổn định, nội dung, hash)
   ▼
SourceSyncUseCase
   • json_api: bản ghi lưu ở rag_source_items, gom theo partition (vd. ngày) → 1 tài liệu bảng markdown / partition
   • web: 1 tài liệu / trang hoặc / file
   • hash nội dung không đổi → bỏ qua; đổi → nạp lại (cùng doc_id); mất khỏi nguồn (lần đọc đầy đủ) → xóa
   • ghi lịch sử chạy (rag_source_runs)
   ▼
MinIO + rag_documents (source_id, source_url) → ingest_document → Qdrant + rag_tables
```

`doc_id` của tài liệu từ connector là cố định (băm `source_id` + khóa), nên đồng bộ lại thì **cập nhật tại chỗ**, không sinh bản trùng.

## Trade-off đã chọn

| Lựa chọn | Lý do |
|---|---|
| Đi qua MinIO + ingestion có sẵn thay vì luồng nạp riêng | Một đường duy nhất, dễ kiểm chứng (cổng dữ liệu áp dụng y như upload); đổi lại tốn thêm một lần ghi MinIO (nhỏ) |
| Bản ghi JSON → bảng markdown theo partition | Tận dụng parser bảng + kho bảng; câu đếm/liệt kê chạy bằng code. Partition giới hạn kích thước mỗi tài liệu |
| Bộ chuyển HTML viết bằng thư viện chuẩn | Không thêm dependency vào image |
| Scheduler trong worker, lease trong Mongo | Không thêm dịch vụ; nhiều worker không chạy trùng một nguồn |

## An toàn

- **Chỉ admin** tạo/sửa nguồn. Mọi tài liệu sinh ra thuộc tenant của nguồn, quyền xem theo `allowed_roles` của nguồn.
- **Bí mật không lưu trong DB**: cấu hình chỉ ghi *tên* biến môi trường, và tên đó bắt buộc bắt đầu bằng `AIP_SOURCE_SECRET_`, để connector không thể đọc các bí mật khác của dịch vụ.
- **Chống SSRF**: chỉ truy cập host đã khai báo (`allowed_hosts`). Redirect ra ngoài các host đó bị chặn. Chỉ cho phép `http`/`https`.
- **Giới hạn**: số trang/bản ghi mỗi lần chạy, dung lượng mỗi phản hồi, timeout, giãn cách giữa các request, tôn trọng `Retry-After`. Website của khách không bị dồn tải.
- Lỗi một trang/bản ghi không dừng cả lần chạy. Lần chạy bị cắt ngang thì **không xóa** tài liệu (tránh xóa nhầm khi nguồn tạm lỗi).

## Phát hiện thay đổi

- Bản ghi JSON: hash từng bản ghi; chỉ partition có bản ghi đổi/mới/mất mới được dựng lại.
- Trang/file: so **dấu vân tay nội dung**, không so byte. File sinh lại mỗi lần tải (export Excel/Word/PDF) mang thời điểm tạo trong `docProps/`, timestamp zip, `/CreationDate`, `/ModDate`, `/ID`; các phần này bị bỏ khi so. `content_sha256` vẫn là hash byte gốc để chống trùng với file upload.
- File tải về được nhận dạng theo thứ tự: content-type → tên trong `Content-Disposition` → đuôi URL → chữ ký byte (`%PDF`, zip có `word/` hoặc `xl/`). Vì vậy link kiểu `/download?id=5` trả `application/octet-stream` vẫn được nạp.

## Thời gian và phân trang (rút ra từ API thật)

- **Múi giờ**: API thường trả thời gian theo UTC (`2026-11-02T23:43:34+00:00`). Gom theo ngày bằng ngày UTC sẽ xếp bài đăng lúc 0h–7h sáng giờ Việt Nam sang hôm trước, làm câu đếm theo ngày bị lệch. Vì vậy ngày được tính theo múi giờ của người dùng (`config.timezone`, mặc định `RAG_CONNECTOR_TIMEZONE=+07:00`), và giờ trong bảng cũng hiển thị theo múi đó, kèm ghi chú "Thời gian theo múi giờ …".
- **Con trỏ trong header**: có API trả con trỏ trang sau trong header (vd. `x-next-cursor`). Khi đó đặt `pagination.cursor_path = "header:x-next-cursor"`. Nút "Thử kết nối" tự phát hiện header loại này và cho bấm "Dùng để phân trang".

Đã thử với API thu thập bài đăng fbx (07/11/2026), trên stack cô lập: đọc đủ 61/61 bài qua 4 trang, ra 6 tài liệu theo ngày giờ Việt Nam. Số bài từng ngày trong kho bảng khớp với số tự tính từ fbx, và đồng bộ lại không nạp lại gì.

## Giao diện

**Màn hình**: khung "Quản lý & Nạp tài liệu" → tab **Nguồn dữ liệu** (`…/knowledge/sources`), theo kho đang chọn. Gồm:
- danh sách nguồn với kết quả lần chạy gần nhất, số tài liệu, cảnh báo thiếu biến môi trường bí mật;
- các nút Đồng bộ (theo dõi tới khi xong), Lịch sử, Sửa, Tạm dừng lịch, Xóa (hỏi có xóa luôn tài liệu không);
- form thêm/sửa, có nút **Thử kết nối**: đọc thử một lần mà không lưu gì. Với API JSON, nút này chỉ ra các danh sách bản ghi có trong phản hồi, các trường kèm giá trị mẫu (bấm để chọn làm mã / gom theo / cột), kiểm tra mã có đủ và không trùng, và cho xem trước tài liệu sẽ nạp. Với website, nút này liệt kê trang/file đọc được, số bảng, và nội dung đọc được của trang có bảng.

Chỉ admin dùng được. Ngoài production, sandbox key gửi `X-User-Role: admin`; ở production role lấy từ API key.

**API**: `/v1/knowledge/sources`: tạo, liệt kê (kèm số tài liệu), xem, sửa, xóa (`?purge=true` xóa luôn tài liệu); `POST /preview` đọc thử; `POST /{id}/sync` chạy ngay; `GET /{id}/runs` xem lịch sử chạy.

Bí mật (`AIP_SOURCE_SECRET_*`) phải có ở **cả rag-api** (Thử kết nối) **và rag-worker** (đồng bộ). Trên server cả hai đọc chung `$AIP_ENV_FILE`.

Ví dụ nguồn API JSON có Bearer (bí mật đặt ở env của worker: `AIP_SOURCE_SECRET_FBX=<token>`):

```json
{"name": "Bản tin MXH", "type": "json_api", "schedule_minutes": 60,
 "auth": {"type": "bearer", "token_env": "AIP_SOURCE_SECRET_FBX"},
 "config": {"url": "http://10.0.0.5:8080/api/posts", "allowed_hosts": ["10.0.0.5"],
            "records_path": "data.items", "id_field": "id", "partition_field": "published_at",
            "pagination": {"type": "page", "param": "page", "size_param": "limit", "size": 100},
            "columns": [{"field": "source.name", "label": "Nguồn"}, {"field": "sentiment", "label": "Sắc thái"}]}}
```

## Kiểm chứng

- Unit: `tests/test_rag_connectors.py` (HTTP giả lập, không ra mạng).
- E2E: `make rag-connectors-e2e`. Lệnh này dựng stack cô lập (`docker-compose.loadtest.yml` + `docker-compose.connectors-e2e.yml`) với nguồn giả lập `scripts/fake_source.py`, chạy `scripts/e2e_connectors.py` qua API và worker thật, kiểm tra Mongo, Qdrant và kho bảng, rồi gỡ stack. Kết quả 07/11/2026: **26/26**.
