# AI Inference Platform (AIP)
> Enterprise Microservices Monorepo & Middleware Execution Engine

## Overview
AI Inference Platform (AIP) is an enterprise-grade, self-hosted AI inference middleware platform. It provides standardized `/v1` APIs for downstream applications with unified authentication, logic routing, quota enforcement, async job handling, and full observability across text, embedding, speech, image, video, and moderation workloads.

## Enterprise Microservices Architecture
This repository is organized as an **Enterprise Monorepo Workspace**:

```text
ai_platform/
├── services/                           # Independent Microservices
│   ├── aip-gateway/                    # Control Plane API Gateway (FastAPI)
│   ├── aip-translation-server/         # CTranslate2 NLLB Serving Microservice
│   ├── aip-stt-server/                 # Speech-to-Text Microservice (Faster-Whisper)
│   ├── aip-tts-adapter/                # Text-to-Speech Adapter Microservice
│   ├── aip-ocr-server/                 # PaddleOCR & IDP Microservice
│   └── aip-moderation-server/          # Moderation Microservice (Llama Guard 4)
├── workers/                            # Async Distributed Job Workers
│   ├── aip-image-worker/               # FLUX.1 / SDXL Generation Worker
│   ├── aip-video-worker/               # Wan2.2 / CogVideoX Worker
│   └── aip-lipsync-worker/             # LivePortrait Worker
├── packages/                           # Internal Shared Libraries
│   ├── aip-common/                     # Core Domain Schemas, Security, Storage, Logging
│   └── aip-sdk-py/                     # Official Python Client SDK
├── deploy/                             # Enterprise Infrastructure Assets
│   ├── helm/                           # Kubernetes Helm Charts (aip-control, aip-runtimes)
│   ├── k8s/                            # Raw Manifests & NetworkPolicies
│   └── docker-compose/                 # Local Dev Environment (Mongo, Redis, RabbitMQ, MinIO)
├── sdks/                               # Client SDKs (.NET 8 Solution)
├── openapi/                            # OpenAPI Specifications
├── migrations/                         # Database Migration Scripts
└── scripts/                            # Utilities & Benchmarks
```

## Developer Commands

```bash
# 1. Start local infrastructure (MongoDB, Redis, RabbitMQ, MinIO)
make dev-env

# 2. Run Gateway Microservice locally
make dev-gateway

# 3. Run Pytest
make test

# 4. Build Docker Images
make docker-build
```
# 1. Tự động đồng bộ và cài toàn bộ dependencies qua uv (Siêu tốc 15ms!)
make setup

# 2. Chạy Gateway Server bằng uv
make dev-gateway

# 3. Chạy Pytest bằng uv
make test

# 4. Kiểm tra Linting code bằng ruff (via uv)
make lint

# 1. Chỉ dùng Docker để bật sẵn DB & Hạ tầng (Chạy cực nhẹ)
make dev-env

# 2. Khởi chạy API Gateway trực tiếp bằng Python/uv (Chạy siêu mượt)
make dev-gateway

# 3. Tắt hạ tầng Docker khi làm xong
make dev-env-down

# 1. Tạo nhánh `dev` và chuyển sang nhánh `dev`
git checkout -b dev

# 2. Merge toàn bộ code từ nhánh `feature/aip-enterprise-core` vào `dev`
git merge feature/aip-enterprise-core

# 3. Đổi URL Remote chỉ định tài khoản namle682004-coder (nếu chưa đổi)
git remote set-url origin https://namle682004-coder@github.com/namle682004-coder/ai_platform.git

# 4. Push nhánh `dev` lên GitHub
git push -u origin dev


Ran command: `wsl -d Ubuntu-22.04 -e bash -c "cd /home/namle/AI-Projects/llm-apps/ai_platform && git branch -D feature/aip-enterprise-core"`
Ran command: `wsl -d Ubuntu-22.04 -e bash -c "cd /home/namle/AI-Projects/llm-apps/ai_platform && git branch"`

**RẤT CHUẨN XÁC NGUYÊN TẮC GIT FLOW DOANH NGHIỆP!** 🏆

Tôi đã xóa nhánh tạm `feature/aip-enterprise-core` giúp bạn. Danh sách các nhánh trên máy của bạn hiện tại cực kỳ gọn gàng chỉ còn lại:
- **`* dev`** (Nhánh phát triển chính)
- **`main`** (Nhánh sản phẩm chính)

---

### Quy Trình Chuẩn Từ Lần Sau Khi Bạn Làm Tính Năng Mới:

Khi bắt đầu làm một công việc mới (Ví dụ: tính năng `feature/rag-search` hoặc sửa lỗi `fix/quota-bug`):

#### **Bước 1: Tạo nhánh mới từ nhánh `dev`**
```bash
git checkout dev
git checkout -b feature/tên-tính-năng-mới
```

#### **Bước 2: Lập trình và kiểm thử code**
Khi làm xong, bạn commit như bình thường:
```bash
git add .
git commit -m "feat: mô tả tính năng mới"
```

#### **Bước 3: Merge kết quả về nhánh `dev` và xóa nhánh tạm**
```bash
# Chuyển về nhánh dev
git checkout dev

# Gộp code mới vào nhánh dev
git merge feature/tên-tính-năng-mới

# Xóa nhánh tạm vừa làm xong cho gọn
git branch -d feature/tên-tính-năng-mới

# Push nhánh dev lên GitHub
git push origin dev
```

Cách làm này đảm bảo repository của bạn luôn sạch đẹp, dễ quản lý và CI/CD tự động kiểm thử 100% không lo sập code trên `main`!