# Hướng dẫn Cấu hình HTTPS & Domain Nội bộ cho AIP Enterprise RAG (`rag.cyber.internal`)

Tài liệu này hướng dẫn chi tiết từng bước thiết lập **HTTPS (SSL/TLS)** với Reverse Proxy **Nginx** cho hệ thống Chatbot RAG và nền tảng AI Platform (AIP) chạy trên máy chủ LAB công ty (`172.16.20.2`), sử dụng domain nội bộ **`rag.cyber.internal`**.

---

## 1. Kiến trúc Tổng quan (Architecture)

```
[ Trình duyệt nhân viên / Client ]
             │  HTTPS (Port 443, TLS 1.3/1.2)
             ▼
┌────────────────────────────────────────────────────────┐
│  aip-nginx Container (Nginx Alpine, RAM cap: 64MB)     │
│  - Domain: rag.cyber.internal, aip.cyber.internal      │
│  - SAN IP: 172.16.20.2                                 │
│  - SSE Streaming: proxy_buffering off                  │
│  - File Upload: client_max_body_size 50M               │
└───────────────────────┬────────────────────────────────┘
                        │ HTTP nội bộ
                        ▼
┌────────────────────────────────────────────────────────┐
│  aip-gateway Container (FastAPI, Port 8000)            │
│  - Vẫn giữ nguyên port 8000 cho script/curl cũ         │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│  aip-rag-api (Port 8010) & Model Server (Port 8011/8012)│
└────────────────────────────────────────────────────────┘
```

### Ưu điểm kiến trúc:
1. **Không phá vỡ hệ thống cũ**: Port `8000` của Gateway vẫn mở, các script benchmark, curl test cũ vẫn chạy bình thường.
2. **Bảo mật & Trực quan**: Người dùng truy cập qua trình duyệt với `https://rag.cyber.internal` có **ổ khóa xanh bảo mật (Secure)**.
3. **Tiết kiệm tài nguyên**: Container Nginx Alpine chỉ tốn ~10–20 MB RAM, tuân thủ giới hạn RAM nghiêm ngặt của server 8GB.
4. **Hỗ trợ Chatbot SSE Stream**: Đã cấu hình `proxy_buffering off` để các token câu trả lời của LLM hiển thị tức thì (real-time stream).

---

## 2. Các Thành phần Đã Cấu hình Trên Repo

Hệ thống đã chuẩn bị sẵn các file cấu hình tại:

| File | Vị trí | Tác dụng |
| :--- | :--- | :--- |
| `generate_internal_certs.sh` | [`deploy/server/generate_internal_certs.sh`](file:///home/namle/AI-Projects/llm-apps/ai_platform/deploy/server/generate_internal_certs.sh) | Script tự động tạo Root CA & cấp chứng chỉ SSL Wildcard cho `*.cyber.internal` + `172.16.20.2` |
| `nginx.conf` | [`deploy/server/nginx.conf`](file:///home/namle/AI-Projects/llm-apps/ai_platform/deploy/server/nginx.conf) | Cấu hình Nginx SSL termination, proxy_pass vào gateway, tắt buffer cho SSE streaming |
| `docker-compose.server.yml` | [`deploy/docker-compose/docker-compose.server.yml`](file:///home/namle/AI-Projects/llm-apps/ai_platform/deploy/docker-compose/docker-compose.server.yml) | Service `nginx` lắng nghe port 80/443, gắn volume chứng chỉ và config |
| `deploy_server.sh` | [`scripts/deploy_server.sh`](file:///home/namle/AI-Projects/llm-apps/ai_platform/scripts/deploy_server.sh) | Script deploy 1-click qua SSH, tự đồng bộ certs và build container |

---

## 3. Hướng dẫn Chi tiết Từng Bước

### PHẦN I: Trên Máy trạm / Laptop Người Dùng (Client Windows)

Do `cyber.internal` là tên miền nội bộ công ty (không đăng ký trên Internet), máy tính của bạn cần 2 thiết lập đơn giản:

#### Bước 1: Cấu hình phân giải domain (File Hosts)
1. Bấm phím **Windows**, gõ `Notepad`.
2. Nhấp chuột phải vào Notepad → Chọn **Run as administrator** (Chạy với quyền quản trị viên).
3. Trong Notepad, bấm `Ctrl + O`, mở file theo đường dẫn:
   ```text
   C:\Windows\System32\drivers\etc\hosts
   ```
   *(Lưu ý: Chọn hiển thị "All Files (*.*)" ở góc dưới bên phải hộp thoại Open để thấy file hosts).*
4. Thêm dòng sau vào **cuối file**:
   ```text
   172.16.20.2   rag.cyber.internal aip.cyber.internal
   ```
5. Bấm `Ctrl + S` để lưu file.

> **Mẹo quản trị mạng:** Nếu Router / DNS Server nội bộ công ty (Pi-hole, Windows DNS Server) đã trỏ `*.cyber.internal -> 172.16.20.2` thì nhân viên **không cần** sửa file hosts thủ công.

---

#### Bước 2: Cài đặt Chứng chỉ Root CA (Xóa vĩnh viễn "Not Secure")
Để Chrome / Edge hiển thị ổ khóa xanh thay vì cảnh báo đỏ:

1. Mở File Explorer trên Windows, dán đường dẫn sau vào thanh địa chỉ:
   ```text
   \\wsl$\Ubuntu-22.04\home\namle\AI-Projects\llm-apps\ai_platform\deploy\server\certs
   ```
2. Nhấp đúp chuột vào file **`cyber_ca.crt`**.
3. Cửa sổ *Certificate* hiện ra, bấm nút **Install Certificate...**
4. Chọn **Local Machine** (Máy tính cục bộ) → Bấm **Next**.
5. Chọn ô thứ 2: **Place all certificates in the following store** (Đặt tất cả chứng chỉ vào kho sau).
6. Bấm **Browse...** → Chọn thư mục:
   ```text
   Trusted Root Certification Authorities (Nhà cung cấp chứng thực gốc đáng tin cậy)
   ```
7. Bấm **OK** → **Next** → **Finish** → Hiện thông báo *"The import was successful"* là xong!

---

### PHẦN II: Deploy và Khởi chạy trên Server (`172.16.20.2`)

#### Cách 1: Deploy tự động từ máy dev qua Script (Khuyến nghị)
Tại terminal WSL trên máy dev của bạn:

```bash
# 1. Chuyển vào thư mục dự án
cd /home/namle/AI-Projects/llm-apps/ai_platform

# 2. Cấp quyền thực thi cho script (nếu chưa có)
chmod +x scripts/deploy_server.sh deploy/server/generate_internal_certs.sh

# 3. Chạy lệnh deploy lên server msp (172.16.20.2)
./scripts/deploy_server.sh
```

Script này sẽ tự động:
- Đồng bộ mã nguồn và thư mục chứng chỉ `certs` sang server `msp`.
- Khởi động lại stack compose gồm `gateway`, `rag-api`, `rag-worker` và `nginx`.
- Nginx lắng nghe tại port `80` và `443`.

---

#### Cách 2: Chạy trực tiếp bằng tay trên Server (SSH)
Nếu bạn đang SSH trực tiếp trên server `172.16.20.2` (`lenam@msp`):

```bash
# 1. Chuyển vào thư mục chứa code
cd ~/aip/app

# 2. Tạo chứng chỉ nếu chưa có
./deploy/server/generate_internal_certs.sh

# 3. Khởi động lại stack
docker compose -f deploy/docker-compose/docker-compose.server.yml up -d
```

Kiểm tra trạng thái Nginx:
```bash
docker ps | grep aip-nginx
# Kết quả mong đợi: Up ... 0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
```

---

## 4. Kiểm tra Kết quả

Mở trình duyệt (Chrome, Edge) trên máy tính của bạn và truy cập:

👉 **`https://rag.cyber.internal`**

### Kết quả chuẩn:
- Giao diện Chatbot RAG hiển thị nhanh chóng.
- Bên trái thanh địa chỉ hiển thị biểu tượng **Ổ khóa bảo mật** (*Connection is secure / Kết nối an toàn*).
- Không còn bất kỳ cảnh báo đỏ nào về SSL.
- Chat thử một câu hỏi để kiểm tra: câu trả lời được stream từng token mượt mà qua HTTPS.

---

## 5. Bảng Tên Miền Nội bộ Đề xuất (`cyber.internal`)

Khi hệ thống mở rộng, bạn có thể tái sử dụng chứng chỉ wildcard `*.cyber.internal` này cho các dịch vụ khác:

| Dịch vụ | Domain nội bộ | Cổng backend thực tế |
| :--- | :--- | :--- |
| **Chatbot RAG** | `https://rag.cyber.internal` | Port 8000 (AIP Gateway) |
| **AIP Platform Portal** | `https://aip.cyber.internal` | Port 8000 (AIP Gateway) |
| **DCP Platform** | `https://dcp.cyber.internal` | Port 18000 (DCP Control-plane) |
| **API Gateway** | `https://api.cyber.internal` | Port 8000 (/v1/*) |
| **Grafana Monitoring** | `https://grafana.cyber.internal`| Port 3000 |
| **Qdrant Vector DB UI** | `https://qdrant.cyber.internal` | Port 6333 |

---

## 6. Xử lý Sự cố Thường Gặp (Troubleshooting)

### 1. Lỗi `-bash: ./deploy/server/generate_internal_certs.sh: No such file or directory`
- **Nguyên nhân**: Bạn đang đứng ở `/mnt/c/Users/ADMIN` chứ chưa vào thư mục repo.
- **Khắc phục**: Gõ `cd /home/namle/AI-Projects/llm-apps/ai_platform` trước khi chạy lệnh.

### 2. Lỗi `-bash: ./scripts/deploy_server.sh: Permission denied`
- **Khắc phục**: Chạy `chmod +x scripts/deploy_server.sh` để cấp quyền thực thi.

### 3. Trình duyệt vẫn báo "Not secure" sau khi cài file `.crt`
- **Nguyên nhân 1**: File `cyber_ca.crt` chưa được lưu vào mục **Trusted Root Certification Authorities** (mà bị lưu nhầm vào *Personal* hoặc *Intermediate*). Hãy mở `certmgr.msc` trên Windows để kiểm tra.
- **Nguyên nhân 2**: Trình duyệt Chrome lưu cache SSL cũ. Hãy đóng hoàn toàn Chrome rồi mở lại, hoặc mở thử bằng cửa sổ ẩn danh (*Incognito*).

### 4. Lỗi `client_loop: send disconnect: Broken pipe` khi SSH
- **Nguyên nhân**: Kết nối mạng đến server bị ngắt tạm thời hoặc server bị quá tải timeout.
- **Khắc phục**: SSH lại vào server: `ssh msp` (hoặc `ssh lenam@172.16.20.2`).
