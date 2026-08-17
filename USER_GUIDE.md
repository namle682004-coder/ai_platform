# 🚀 Hướng Dẫn Sử Dụng & Vận Hành Toàn Diện
## Everwin AI Platform (AIP) — Enterprise Inference Middleware & Developer Console

---

## 📑 Mục Lục
1. [Giới Thiệu Tổng Quan](#1-giới-thiệu-tổng-quan)
2. [Kiến Trúc Hệ Thống & 13 Dịch Vụ AI](#2-kiến-trúc-hệ-thống--13-dịch-vụ-ai)
3. [Yêu Cầu Môi Trường & Cài Đặt](#3-yêu-cầu-môi-trường--cài-đặt)
4. [Hướng Dẫn Khởi Chạy Hệ Thống](#4-hướng-dẫn-khởi-chạy-hệ-thống)
5. [Hướng Dẫn Sử Dụng Web Portal](#5-hướng-dẫn-sử-dụng-web-portal)
6. [Hướng Dẫn Tích Hợp API Cho Lập Trình Viên](#6-hướng-dẫn-tích-hợp-api-cho-lập-trình-viên)
7. [Kiểm Thử & Đảm Bảo Chất Lượng (CI/CD)](#7-kiểm-thử--đảm-bảo-chất-lượng-cicd)
8. [Quy Trình Git Flow Chuẩn Doanh Nghiệp](#8-quy-trình-git-flow-chuẩn-doanh-nghiệp)

---

## 1. Giới Thiệu Tổng Quan

**Everwin AI Platform (AIP)** là nền tảng Middleware AI Inference và Developer Console được xây dựng theo chuẩn kiến trúc Doanh nghiệp (**Clean Architecture & Domain-Driven Design**). 

Hệ thống đóng vai trò làm trung gian điều phối, chuẩn hóa và bảo vệ tài nguyên AI, cung cấp:
- **Cổng API chuẩn hóa (`/v1`)**: Tích hợp thống nhất cho các ứng dụng downstream (Web, Mobile, Enterprise App).
- **Cơ chế bảo mật Zero-Trust**: Quản lý API Key mã hóa **Argon2id**, phòng thủ nội dung xấu (**Guardrails**).
- **Hệ thống Quota & Rate Limiting**: Kiểm soát số lượng request (RPM/TPM), trừ số dư theo credit/token/block.
- **Giám sát GPU Real-time**: Đo lường trực tiếp phần cứng GPU (NVIDIA CUDA, VRAM Usage, Nhiệt độ core, Công suất tiêu thụ).
- **Developer Sandbox tích hợp**: Thử nghiệm trực tiếp các mô hình AI ngay trên giao diện web console trước khi tích hợp vào code.

---

## 2. Kiến Trúc Hệ Thống & 13 Dịch Vụ AI

```text
ai_platform/
├── services/
│   ├── gateway/                 # API Gateway điều phối trung tâm (FastAPI, Auth, Static Web Console)
│   ├── translation-server/      # Dịch thuật thời gian thực (Helsinki-NLP MarianMT - LIVE on GPU)
│   ├── stt-server/              # Nhận dạng giọng nói tiếng Việt (PhoWhisper)
│   ├── tts-adapter/             # Tổng hợp tiếng nói tiếng Việt đa vùng miền (viTTS)
│   ├── ocr-server/              # Nhận dạng giấy tờ: CCCD, GPLX, Hộ chiếu (PaddleOCR)
│   └── moderation-server/       # Kiểm duyệt nội dung & lọc ngôn từ độc hại (Llama Guard)
├── workers/                     # Hệ thống xử lý tác vụ bất đồng bộ (RabbitMQ + Celery/Async)
│   ├── image-worker/            # Sinh ảnh nghệ thuật (Stable Diffusion XL)
│   ├── video-worker/            # Sinh video AI (Wan2.2 / CogVideoX)
│   └── lipsync-worker/          # Đồng bộ khẩu hình video (LivePortrait)
├── packages/
│   ├── common/                  # Shared domain entities, MongoDB/Redis repositories, Security
│   └── sdk-py/                  # Python Client SDK chính thức (`aip-sdk`)
├── sdks/                        # Client SDK đa ngôn ngữ (.NET 8 SDK, etc.)
├── deploy/                      # Cấu hình triển khai Docker Compose, Helm Charts, K8s manifests
├── migrations/                  # Database seeding & migration scripts
├── scripts/                     # Operational utilities & automation tools
└── tests/                       # Bộ kiểm thử tự động pytest CI/CD
```

### Danh Mục 13 Dịch Vụ AI:
1. **Translation API** *(LIVE on GPU)*: Dịch thuật chất lượng cao En ↔ Vi bằng Helsinki-NLP MarianMT.
2. **Speech to Text API**: Chuyển giọng nói tiếng Việt thành văn bản bằng PhoWhisper.
3. **Text to Speech API**: Chuyển văn bản thành giọng đọc tự nhiên đa vùng miền.
4. **LLM Chatbot API**: Suy luận ngôn ngữ lớn Qwen3-8B & 14B.
5. **Image Generation API**: Tạo ảnh nghệ thuật từ mô tả văn bản bằng Stable Diffusion XL.
6. **Content Moderation API**: Quét phát hiện và chặn ngôn từ thù địch, độc hại, PII.
7. **Driver's License Recognition**: Trích xuất dữ liệu Giấy phép lái xe (GPLX).
8. **ID Recognition (CCCD)**: Trích xuất thông tin Căn cước công dân gắn chip.
9. **Passport Recognition**: Nhận dạng thông tin hộ chiếu quốc tế.
10. **FaceMatch**: So khớp khuôn mặt xác thực sinh trắc học eKYC.
11. **Liveness Detection v3**: Kiểm tra thực thể sống chống giả mạo deepfake.
12. **Text Embedding API**: Tạo vector dense embeddings cho hệ thống RAG & Semantic Search.
13. **Text Summarization API**: Tóm tắt tự động văn bản, bài báo dài thành ý chính.

---

## 3. Yêu Cầu Môi Trường & Cài Đặt

### Phần Cứng & Hệ Điều Hành:
- **Hệ điều hành**: Linux (Ubuntu 22.04 LTS) hoặc Windows qua **WSL2 Ubuntu 22.04**.
- **GPU**: NVIDIA GeForce RTX / Tesla / A100 / H100 hỗ trợ **NVIDIA CUDA Toolkit 12.x**.
- **RAM**: Tối thiểu 16GB RAM.

### Công Cụ Phần Mềm:
- **Python**: `>= 3.10`
- **uv**: Trình quản lý package và virtualenv siêu tốc của Rust (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Docker & Docker Compose**: Quản lý database (MongoDB, Redis, RabbitMQ, MinIO)
- **Git**: Quản lý phiên bản mã nguồn

---

## 4. Hướng Dẫn Khởi Chạy Hệ Thống

### Bước 1: Thiết lập môi trường và dependencies
```bash
# Cài đặt toàn bộ dependencies của Monorepo siêu tốc qua uv
make setup
```

### Bước 2: Bật các dịch vụ hạ tầng Database (Docker)
```bash
# Khởi chạy MongoDB, Redis, RabbitMQ, MinIO ở chế độ nền
make dev-env
```

### Bước 3: Khởi chạy GPU Translation Engine (Service Node)
```bash
# Mở terminal và chạy Translation Microservice trên GPU
cd services/translation-server
uv run python translation_app.py
# Server sẽ tự động detect NVIDIA CUDA và load model Helsinki-NLP lên VRAM
```

### Bước 4: Khởi chạy API Gateway (Control Plane)
```bash
# Mở một terminal khác và khởi chạy Gateway
make dev-gateway
# Hoặc: cd services/gateway && uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Sau khi khởi chạy thành công:
- **Web Console / Portal**: `http://localhost:8000/staff/dashboard` hoặc `http://localhost:8000/staff/apis`
- **Tài liệu API Swagger**: `http://localhost:8000/docs`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

---

## 5. Hướng Dẫn Sử Dụng Web Portal

### 1. Bảng Điều Khiển Tổng Quan (`/staff/dashboard`)
- **Giám Sát Phần Cứng GPU**: Hiển thị tên GPU thực tế (`NVIDIA GeForce RTX 3050 Laptop GPU`), dung lượng **VRAM thực tế** đang sử dụng (MB / %), **Nhiệt độ nhân GPU (°C)** và **Công suất tiêu thụ (W)**.
- **Bảng Trạng Thái Dịch Vụ**: Theo dõi các API đang bật, hạn mức quota còn lại và số dư tín dụng (Credit Balance).

### 2. Quản Lý Danh Mục Dịch Vụ (`/staff/apis`)
- **Bật / Tắt API**: Nhấp vào công tắc của từng dịch vụ để kích hoạt hoặc vô hiệu hóa.
- **Cơ Chế Bảo Vệ Phần Cứng**:
  - Đối với dịch vụ đã triển khai GPU (**Translation API**): Người dùng có thể bật/tắt và sử dụng bình thường.
  - Đối với các dịch vụ chưa cấp phát đủ tài nguyên GPU: Hệ thống **tự động ngăn chặn hành động bật** và hiển thị thông báo cảnh báo chuyên nghiệp:
    > *"Hạ tầng phần cứng (GPU/VRAM) hiện tại chưa cấp phát đủ tài nguyên để kích hoạt môi trường Sandbox cho dịch vụ này. Hệ thống sẽ sớm mở lại sau khi hoàn thành nâng cấp hạ tầng."*

### 3. Thử Nghiệm Tại Sandbox Playground (`/staff/service-...`)
Truy cập vào trang chi tiết của từng dịch vụ (ví dụ: `/staff/service-nlp-translation`):
- **Tab OVERVIEW**: Giới thiệu công nghệ, kiến trúc mô hình và thông số kỹ thuật.
- **Tab SERVICE (Playground)**:
  - Chọn API Key hợp lệ.
  - Chọn chiều ngôn ngữ dịch (English ➔ Vietnamese hoặc Tiếng Việt ➔ Tiếng Anh).
  - Nhập văn bản nguồn và bấm **"Chạy Dịch Thuật"** ➔ Nhận kết quả trực tiếp từ GPU Engine trong vài trăm miligiây.
- **Tab DOCUMENT**: Mẫu code gọi API hoàn chỉnh bằng **cURL, Python, .NET (C#), JavaScript**.
- **Tab PRICING**: Bảng giá, đơn vị tính phí (characters, tokens, requests) và chính sách hạn mức.

### 4. Quản Lý API Keys (`/staff/keys`)
- Tạo API Key mới với tiền tố chuẩn `aip_live_...`.
- Key chỉ hiển thị **1 lần duy nhất** khi tạo và được hash bảo mật bằng thuật toán **Argon2id** trong cơ sở dữ liệu.
- Cho phép thu hồi (Revoke) hoặc tạm ngưng key khi phát hiện nguy cơ rò rỉ.

---

## 6. Hướng Dẫn Tích Hợp API Cho Lập Trình Viên

### Header Xác Thực Bắt Buộc
Mọi request gửi tới API Gateway đều cần kèm theo API Key tại header:
```http
Authorization: Bearer aip_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
Content-Type: application/json
```

### Ví Dụ 1: Gọi Dịch Thuật Bằng cURL
```bash
curl -X POST "http://localhost:8000/v1/nlp/translate" \
  -H "Authorization: Bearer YOUR_AIP_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Artificial Intelligence is transforming enterprise software.",
    "source_lang": "en",
    "target_lang": "vi"
  }'
```

**Phản hồi thành công (HTTP 200)**:
```json
{
  "status": "success",
  "source_lang": "en",
  "target_lang": "vi",
  "original_text": "Artificial Intelligence is transforming enterprise software.",
  "translated_text": "Trí tuệ nhân tạo đang biến đổi phần mềm doanh nghiệp.",
  "engine": "Helsinki-NLP/opus-mt-en-vi (GPU-Accelerated)"
}
```

### Ví Dụ 2: Tích Hợp Bằng Python SDK (`aip-sdk`)
```python
from aip_sdk import AIPClient

client = AIPClient(api_key="aip_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", base_url="http://localhost:8000")

# Gọi dịch thuật En -> Vi
response = client.translate(
    text="Hệ thống trí tuệ nhân tạo vận hành rất mượt mà trên card đồ họa.",
    source_lang="vi",
    target_lang="en"
)
print("Kết quả dịch:", response.translated_text)
```

### Bảng Mã Lỗi Chuẩn (Standard HTTP Status Codes):
| Mã Lỗi | Ý Nghĩa | Mô Tả Xử Lý |
|---|---|---|
| **`200 OK`** | Thành công | Yêu cầu được xử lý trọn vẹn bởi AI Engine. |
| **`400 Bad Request`** | Dữ liệu không hợp lệ | Kiểm tra lại payload JSON đầu vào. |
| **`401 Unauthorized`** | Sai hoặc thiếu API Key | Kiểm tra header `Authorization: Bearer <key>`. |
| **`403 Forbidden`** | Chưa bật dịch vụ | Dịch vụ này chưa được kích hoạt trong Project của bạn. |
| **`429 Rate Limit`** | Vượt quá hạn mức | Quá số lượt gọi trong 1 phút (RPM) hoặc hết Credit. |
| **`502 Bad Gateway`** | Service Node Offline | Service backend của model này đang bảo trì hoặc chưa khởi chạy. |

---

## 7. Kiểm Thử & Đảm Bảo Chất Lượng (CI/CD)

Hệ thống được trang bị bộ kiểm thử tự động toàn diện theo chuẩn doanh nghiệp:

```bash
# 1. Chạy toàn bộ 14 bài kiểm thử tự động (Unit & Integration Tests)
make test
# hoặc: uv run pytest

# 2. Kiểm tra chất lượng và chuẩn format mã nguồn (Ruff Linter)
make lint

# 3. Xuất tài liệu OpenAPI JSON, Postman Collection và HTML Spec
make export
```

---

## 8. Quy Trình Git Flow Chuẩn Doanh Nghiệp

Để đảm bảo repository luôn sạch, ổn định và sẵn sàng cho môi trường Production:

1. **Nhánh `main`**: Nhánh ổn định cao nhất, chỉ merge khi release phiên bản chính thức.
2. **Nhánh `dev`**: Nhánh phát triển chính nơi tích hợp các tính năng đã kiểm thử.
3. **Quy trình làm tính năng mới**:
   ```bash
   # Bước 1: Kéo code mới nhất từ dev và tạo nhánh tính năng
   git checkout dev
   git pull origin dev
   git checkout -b feature/ten-tinh-nang

   # Bước 2: Lập trình, kiểm thử pass 100% tests
   uv run pytest

   # Bước 3: Commit và merge về dev
   git add .
   git commit -m "feat: mô tả tính năng vừa hoàn thiện"
   git checkout dev
   git merge feature/ten-tinh-nang
   git branch -d feature/ten-tinh-nang
   git push origin dev
   ```

---
*Everwin AI Platform — Built for Mission-Critical Enterprise AI Workloads.*
