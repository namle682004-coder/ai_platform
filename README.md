# AI Inference Platform (AIP)
> Enterprise Microservices Monorepo & Inference Middleware Execution Engine

---

## 🌟 Overview
**Everwin AI Platform (AIP)** is an enterprise-grade, self-hosted AI inference middleware platform and developer console. Built with **Clean Architecture & Domain-Driven Design (DDD)**, it provides standardized `/v1` APIs for downstream applications with unified authentication, quota enforcement, real-time hardware telemetry, and interactive developer sandboxes across 13 specialized AI workloads.

---

## 📚 Documentation & User Guides
- 📖 **[Hướng Dẫn Sử Dụng & Vận Hành Toàn Diện (USER_GUIDE.md)](./USER_GUIDE.md)**: Hướng dẫn chi tiết từng bước cài đặt, vận hành Web Portal, tương tác GPU Sandbox và tích hợp API cho lập trình viên.
- 📐 **[Enterprise System Architecture Blueprint](./enterprise_architecture_v2.md)**: Thiết kế kiến trúc kỹ thuật cấp cao (Hexagonal Ports & Adapters, Zero-Trust Security, HA/DR).
- 🌐 **[OpenAPI Specifications & Postman Collection](./openapi/)**: Tài liệu đặc tả API chuẩn OpenAPI 3.1 & Postman Collection.

---

## 🏛️ Enterprise Monorepo Structure

```text
ai_platform/
├── services/                           # Independent Microservices
│   ├── gateway/                        # Control Plane API Gateway (FastAPI) & Static Web Console
│   ├── translation-server/             # Translation Serving Node (MarianMT - Live on GPU)
│   ├── stt-server/                     # Speech-to-Text Microservice (PhoWhisper)
│   ├── tts-adapter/                    # Text-to-Speech Adapter Microservice (viTTS)
│   ├── ocr-server/                     # OCR & Document Digitization (PaddleOCR)
│   └── moderation-server/              # Content Moderation Microservice (Llama Guard)
├── workers/                            # Async Distributed Job Workers (RabbitMQ)
│   ├── image-worker/                   # FLUX.1 / SDXL Image Generation Worker
│   ├── video-worker/                   # Wan2.2 / CogVideoX Video Generation Worker
│   └── lipsync-worker/                 # LivePortrait Video Sync Worker
├── packages/                           # Internal Shared Libraries
│   ├── common/                         # Core Domain Schemas, Security (Argon2id), Repositories
│   └── sdk-py/                         # Official Python Client SDK (`aip-sdk`)
├── deploy/                             # Enterprise Infrastructure Assets
│   ├── helm/                           # Kubernetes Helm Charts (aip-control, aip-runtimes)
│   ├── k8s/                            # Raw Manifests & NetworkPolicies
│   └── docker-compose/                 # Local Infrastructure (Mongo, Redis, RabbitMQ, MinIO)
├── sdks/                               # Multi-language Client SDKs (.NET 8 Solution)
├── openapi/                            # OpenAPI Specifications & Postman Collections
├── migrations/                         # Database Migration & Seeding Scripts
├── scripts/                            # Operational Utilities & Benchmark Tools
└── tests/                              # Automated Pytest CI/CD Test Suite
```

---

## ⚡ Quick Start

### 1. Setup Environment
```bash
# Setup virtual environment and lock all dependencies in monorepo via uv
make setup
```

### 2. Start Infrastructure
```bash
# Start MongoDB, Redis, RabbitMQ, MinIO with Docker Compose
make dev-env
```

### 3. Run Microservices & Gateway
```bash
# Terminal 1: Run Live GPU Translation Node
cd services/translation-server && uv run python translation_app.py

# Terminal 2: Run Gateway Control Plane
make dev-gateway
```

### 4. Run Automated Quality Assurance (Pytest & Ruff)
```bash
# Run full test suite (100% pass)
make test

# Run code linter
make lint
```

---

## 🔒 Enterprise Security & Hardware Telemetry
- **Argon2id API Key Hashing**: Plaintext keys (`aip_live_...`) are returned only once upon creation.
- **Hardware Telemetry**: Direct NVIDIA NVML integration reading real GPU temperatures, VRAM consumption, and wattage.
- **Hardware Allocation Guard**: Prevents enabling services when dedicated GPU/VRAM hardware has not been provisioned.

---
*Everwin AI Platform — Built for Mission-Critical Enterprise AI Workloads.*