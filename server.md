# Hướng dẫn Triển khai HTTPS, Domain Nội bộ & Cài đặt Chứng chỉ Client (`aip.cyber.internal`)

Tài liệu này cung cấp hướng dẫn đầy đủ từ **phía Quản trị viên (Admin/Server)** đến **phía Người dùng cuối (Client/Nhân viên nội bộ)** để truy cập nền tảng **AIP Enterprise Platform** và **RAG Chatbot** qua giao thức bảo mật HTTPS với domain nội bộ **`https://aip.cyber.internal`**.

---

## 1. Kiến trúc Tổng quan (Architecture)

```
[ Máy tính Nhân viên / Client ]
             │  HTTPS (Port 443, TLS 1.3 / 1.2)
             ▼
┌────────────────────────────────────────────────────────┐
│  aip-nginx Container (Nginx Alpine, RAM limit: 64MB)   │
│  - Domain chính: aip.cyber.internal                    │
│  - SAN IP: 172.16.20.2, Wildcard: *.cyber.internal     │
│  - SSE Streaming: proxy_buffering off                  │
│  - File Upload: client_max_body_size 50M               │
│  - Clean URLs: Tự động 301 Redirect mọi đuôi .html    │
└───────────────────────┬────────────────────────────────┘
                        │ HTTP nội bộ
                        ▼
┌────────────────────────────────────────────────────────┐
│  aip-gateway Container (FastAPI, Port 8000)            │
│  - Đường dẫn sạch: /auth/login, /dashboard, /projects  │
│  - RAG Service: /services/rag-chatbot                  │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│  aip-rag-api (Port 8010) & Model Server (Port 8011)    │
└────────────────────────────────────────────────────────┘
```

### Chuẩn hóa URL Production (Không đuôi `.html`):
- **Trang chủ / Portal**: `https://aip.cyber.internal`
- **Đăng nhập**: `https://aip.cyber.internal/auth/login`
- **Đăng ký**: `https://aip.cyber.internal/auth/signup`
- **Bảng điều khiển**: `https://aip.cyber.internal/dashboard`
- **Quản lý Dự án**: `https://aip.cyber.internal/projects`
- **Trợ lý AI RAG**: `https://aip.cyber.internal/services/rag-chatbot`

---

## 2. Vị trí File Chứng chỉ SSL & Root CA

Hệ thống sử dụng cơ chế **Root CA nội bộ (Cyber Internal Root CA)** để cấp chứng chỉ cho `aip.cyber.internal`.

### Vị trí các file trên máy tính Admin (WSL / Windows):
```text
\\wsl$\Ubuntu-22.04\home\namle\AI-Projects\llm-apps\ai_platform\deploy\server\certs\
├── Cyber-Internal-Root-CA.cer    <-- File chuẩn gửi cho Client / Nhân viên
├── cyber_ca.crt                  <-- File chứng chỉ Root CA gốc
├── cyber_ca.key                  <-- Private key của Root CA (Bảo mật, không gửi ra ngoài)
├── cyber_internal.crt            <-- Chứng chỉ Server cấp cho aip.cyber.internal
└── cyber_internal.key            <-- Private key Server Nginx dùng
```

### Vị trí trên Server LAB (`172.16.20.2`):
```text
/home/lenam/aip/app/deploy/server/certs/
```

---

## 3. Cách Xuất File Root CA `.cer` (Dành cho Quản trị viên)

Nếu bạn cần xuất lại file chứng chỉ Root CA từ máy tính Windows đã cài đặt:

1. Nhấn tổ hợp phím `Win + R` → Nhập:
   ```text
   certlm.msc
   ```
   *(Hoặc `certmgr.msc` nếu dùng quyền người dùng hiện tại)*
2. Điều hướng theo cây thư mục bên trái:
   ```text
   Trusted Root Certification Authorities (Nhà cung cấp chứng thực gốc đáng tin cậy)
   └── Certificates
   ```
3. Tìm chứng chỉ có tên: **`Cyber Internal Root CA`**.
4. Nhấp chuột phải vào chứng chỉ → Chọn **All Tasks** → **Export...**
5. Trong trình thuật sĩ:
   - Chọn: **No, do not export the private key** → Bấm **Next**.
   - Chọn định dạng: **Base-64 encoded X.509 (.CER)** → Bấm **Next**.
   - Bấm **Browse...** và đặt tên file: `Cyber-Internal-Root-CA.cer`.
   - Bấm **Next** → **Finish**.

> **Mẹo:** Bạn không nhất thiết phải làm bước xuất này vì file **`Cyber-Internal-Root-CA.cer`** đã được tạo sẵn ngay trong thư mục `deploy/server/certs/` của dự án!

---

## 4. HƯỚNG DẪN DÀNH CHO CLIENT / NHÂN VIÊN (Copy gửi cho người dùng)

> Bạn có thể sao chép toàn bộ phần khung bên dưới để gửi cho đồng nghiệp / nhân viên qua Email nội bộ, Slack, Zalo hoặc Teams:

```markdown
### 📢 Hướng dẫn Truy cập Hệ thống AIP Platform (`https://aip.cyber.internal`)

Để truy cập cổng AI Platform và Chatbot RAG của công ty với kết nối bảo mật HTTPS (ổ khóa xanh an toàn), bạn chỉ cần thực hiện 2 bước đơn giản:

---

#### BƯỚC 1: Cài đặt Chứng chỉ Bảo mật Nội bộ (Chỉ làm lần đầu)
1. Tải về file đính kèm: `Cyber-Internal-Root-CA.cer` (hoặc `cyber_ca.crt`).
2. Nhấp đúp chuột vào file vừa tải về.
3. Bấm nút **Install Certificate...**
4. Chọn **Local Machine** (Máy cục bộ) → Bấm **Next** (Cần xác nhận quyền Admin nếu có).
5. Tích chọn ô thứ hai: **Place all certificates in the following store** (Đặt tất cả chứng chỉ vào kho sau).
6. Bấm **Browse...** → Chọn thư mục:
   👉 **Trusted Root Certification Authorities** (Nhà cung cấp chứng thực gốc đáng tin cậy).
7. Bấm **OK** → **Next** → **Finish**. Xuất hiện thông báo *"The import was successful"* là xong!

---

#### BƯỚC 2: Cấu hình Phân giải Tên miền (DNS / File Hosts)

> **Lưu ý:** Nếu mạng WiFi/LAN công ty đã được quản trị viên cấu hình DNS tự động, bạn có thể bỏ qua bước này.

**Cách 1: Nhanh nhất qua PowerShell (Khuyến nghị)**
1. Bấm phím **Windows**, gõ `powershell`.
2. Nhấp chuột phải vào **Windows PowerShell** → Chọn **Run as administrator**.
3. Dán dòng lệnh sau và nhấn **Enter**:
   ```powershell
   Add-Content -Path "C:\Windows\System32\drivers\etc\hosts" -Value "`n172.16.20.2 aip.cyber.internal" -Force
   ```

**Cách 2: Sửa bằng Notepad thủ công**
1. Bấm phím **Windows**, gõ `Notepad`.
2. Nhấp chuột phải vào Notepad → Chọn **Run as administrator**.
3. Bấm `Ctrl + O`, mở file `C:\Windows\System32\drivers\etc\hosts` (chọn hiển thị Tất cả tệp `*.*`).
4. Thêm dòng sau vào cuối file và lưu lại (`Ctrl + S`):
   ```text
   172.16.20.2   aip.cyber.internal
   ```

---

#### BƯỚC 3: Truy cập Hệ thống
Mở trình duyệt (Chrome, Edge, Cốc Cốc) và truy cập:
👉 **https://aip.cyber.internal**

Trình duyệt sẽ hiển thị biểu tượng **Ổ khóa bảo mật** an toàn màu xám/xanh.
- Đăng nhập: `https://aip.cyber.internal/auth/login`
- Trợ lý AI Trực ban: `https://aip.cyber.internal/services/rag-chatbot`
```

---

## 5. Dành cho Quản trị viên: Triển khai & Vận hành Server

### 1. Kịch bản Deploy 1-Click
Trên terminal WSL máy tính của bạn:
```bash
cd /home/namle/AI-Projects/llm-apps/ai_platform
./scripts/deploy_server.sh
```
Script sẽ tự động:
- Đóng gói mã nguồn và đồng bộ certs sang server `msp`.
- Xử lý dọn dẹp an toàn các container cũ.
- Biên dịch image và khởi chạy stack:
  - `aip-nginx`: Reverse proxy HTTPS port 443 & HTTP port 80.
  - `aip-gateway`: API Gateway port 8000.
  - `aip-rag-api`: Backend RAG port 8010.
  - `aip-rag-worker`: Celery worker xử lý tác vụ nền.

### 2. Kiểm tra nhanh trạng thái dịch vụ trên Server
```bash
ssh msp "docker compose -f ~/aip/app/deploy/docker-compose/docker-compose.server.yml ps"
```

### 3. Kiểm tra chứng chỉ SSL từ dòng lệnh:
```bash
curl -k -I https://172.16.20.2/auth/login
```
Kết quả mong đợi: `HTTP/2 200` với Header `server: nginx/1.27.5`.

---

## 6. Xử lý Sự cố Thường Gặp (Troubleshooting)

### 1. Trình duyệt báo `DNS_PROBE_FINISHED_NXDOMAIN`
- **Nguyên nhân**: Máy tính chưa biết domain `aip.cyber.internal` trỏ về IP nào.
- **Khắc phục**: Làm lại Bước 2 (thêm `172.16.20.2 aip.cyber.internal` vào file hosts bằng PowerShell Administrator).

### 2. Trình duyệt báo "Not secure" / "Kết nối của bạn không phải là riêng tư"
- **Nguyên nhân**: File chứng chỉ Root CA chưa được import đúng vào thư mục **Trusted Root Certification Authorities** (mà bị đưa nhầm vào Personal hoặc tự động).
- **Khắc phục**: Mở `certlm.msc`, kiểm tra xem trong mục *Trusted Root Certification Authorities \ Certificates* đã có chứng chỉ tên **Cyber Internal Root CA** chưa. Nếu chưa, hãy import lại theo hướng dẫn ở Bước 1.
- Khởi động lại trình duyệt Chrome/Edge hoặc thử bằng cửa sổ Ẩn danh (Incognito).

### 3. Lỗi "Bạn không có cấp phép để lưu vào vị trí này" khi sửa file hosts
- **Nguyên nhân**: Notepad mở với quyền người dùng thông thường, không thể ghi vào thư mục hệ thống `System32\drivers\etc`.
- **Khắc phục**: Dùng lệnh PowerShell Run as Administrator như ở Bước 2.
