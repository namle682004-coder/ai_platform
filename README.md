# Everwin AI Platform (AIP)
> Enterprise AI Inference Middleware & Distributed Execution Engine

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-green.svg)](https://fastapi.tiangolo.com)
[![uv](https://img.shields.io/badge/Package_Manager-uv-blueviolet.svg)](https://astral.sh/uv)
[![RabbitMQ](https://img.shields.io/badge/Broker-RabbitMQ_AMQP-orange.svg)](https://rabbitmq.com)
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)]()

---

## 🌟 Overview

**Everwin AI Platform (AIP)** is an enterprise-grade, self-hosted AI inference middleware platform and developer console. Built with **Clean Architecture & Domain-Driven Design (DDD)**, it acts as an intelligent distribution, governance, and execution layer between downstream business clients and upstream heterogeneous AI compute nodes (NVIDIA GPUs & CPUs).

### Core Capabilities:
- 🚀 **Standardized `/v1` AI APIs**: Drop-in unified endpoints for 21 enterprise AI models across 13 specialized domains.
- 🛡️ **Zero-Trust Security & Governance**: Argon2id salted API key hashing, strict CIDR IP allowlisting, and project-based tenant isolation.
- ⚡ **Asynchronous Task Offloading**: Dynamic threshold detection offloading heavy inference (FLUX.1 image generation, Wan2.2 video, CogVideoX, LivePortrait) to distributed RabbitMQ workers.
- 🔄 **Event-Driven Resilience**: Native DLQ dead-lettering, TTL message expirations, Redis-backed idempotency protection, HMAC-SHA256 signed webhooks, and automatic stale job reconciliation.
- 📊 **Real-time Hardware Telemetry**: Native NVIDIA NVML integration monitoring real GPU core temperatures, VRAM consumption, and wattage with automated hardware allocation guards.
- 🖥️ **Developer & Staff Self-Service Portal**: Integrated Web Console, interactive API Sandbox, Key Management, and public System Status page.

---

## 🏛️ Clean Architecture Monorepo Structure

```text
ai_platform/
├── control-plane/                      # Tầng 1: Control-Plane
│   └── gateway/                        # API Gateway (FastAPI), Auth, Quotas, Rate Limiting, Web Console
│
├── data-plane/                         # Tầng 2: Data-Plane (Unified Inference Serving Nodes)
│   ├── vllm-engine/                    # vLLM High-Throughput Unified LLM & Embedding Server (:8001)
│   ├── translation-server/             # MarianMT En ↔ Vi Live on GPU (:8003)
│   ├── stt-server/                     # PhoWhisper Vietnamese Speech-to-Text (:8002)
│   ├── tts-adapter/                    # viTTS Multi-regional Speech Synthesis (:8004)
│   ├── ocr-server/                     # PaddleOCR Document & Identity Digitization (:8005)
│   ├── moderation-server/              # Llama Guard Safety & Content Moderation (:8006)
│   └── runtime-probe/                  # Hardware telemetry probe & NVML health checker
│
├── workers/                            # Tầng 3: Distributed Asynchronous Workers
│   ├── orchestration/                  # Nhóm Điều phối & Sự kiện
│   │   ├── dispatcher-worker/          # Job router, Priority Scheduler, Stale Job Auto-Reconciler
│   │   └── callback-worker/            # HMAC-SHA256 signed Webhook notification delivery
│   └── gpu-workloads/                  # Nhóm Tác vụ nặng GPU
│       ├── image-worker/               # FLUX.1 & SDXL High-Res Image Generation
│       ├── video-worker/               # Wan2.2 & CogVideoX Text-to-Video Generation
│       └── lipsync-worker/             # LivePortrait Audio-Driven Lip Synchronization
│
├── packages/                           # Shared Kernel Libraries
│   ├── common/                         # Core domain schemas, Argon2id security, Mongo & Redis repositories
│   ├── contracts/                      # AMQP messaging envelopes, event schemas & queue contracts
│   └── sdk/                            # Official Python Client SDK (`aip-sdk`)
│
├── infrastructure/                     # Observability & Monitoring
│   ├── prometheus/                     # Prometheus scrape configs & alert rules
│   ├── grafana/                        # Pre-configured Grafana dashboards & datasources
│   └── alertmanager/                   # Alertmanager notification routing
│
├── deploy/                             # Enterprise Deployment Manifests
│   ├── docker-compose/                 # Local stack (Mongo, Redis, RabbitMQ, MinIO, Monitoring)
│   ├── helm/                           # Kubernetes Helm Charts (aip-control, aip-runtimes, aip-infra)
│   └── k8s/                            # Raw K8s manifests, NetworkPolicies, Namespaces & Secrets
│
├── frontend/                           # Developer & Staff Web UI Portal (Vite + Vanilla JS)
├── sdks/                               # Multi-language Client SDKs (.NET 8 LTS C# Solution)
├── openapi/                            # OpenAPI 3.1 specifications & Postman Collection
├── migrations/                         # Database seeding & migration scripts
├── scripts/                            # Operational automation utilities
└── tests/                              # Automated Pytest CI/CD test suite (100% pass)
```

---

## 🎯 13 AI Services & 21-Model Catalog

| # | Service Domain | Route | Target Models / Engines | Mode |
|---|---|---|---|---|
| 1 | **Translation** | `/v1/nlp/translate` | Helsinki-NLP/opus-mt-en-vi (GPU-accelerated) | Sync / Async |
| 2 | **Speech-to-Text (STT)** | `/v1/audio/transcriptions` | PhoWhisper (Vietnamese ASR) | Sync / Async |
| 3 | **Text-to-Speech (TTS)** | `/v1/audio/speech` | viTTS Multi-regional Speech Engine | Sync / Async |
| 4 | **LLM Chat Completion** | `/v1/chat/completions` | Qwen/Qwen2.5-7B-Instruct, DeepSeek-V3 | Sync / Async |
| 5 | **Vector Embedding** | `/v1/embeddings` | BAAI/bge-m3 Multilingual Vector Embeddings | Sync |
| 6 | **Text Summarization** | `/v1/nlp/summarize` | VietAI/vit5-base-vietnews-summarization | Sync |
| 7 | **Content Moderation** | `/v1/moderations` | Meta Llama Guard 3, VietNamese Toxicity Classifier | Sync |
| 8 | **Image Generation** | `/v1/images/generations` | Black Forest FLUX.1-schnell, Stability SDXL Turbo | Async Worker |
| 9 | **Video Generation** | `/v1/videos/generations` | Wan2.2-T2V-14B, THUDM/CogVideoX-5b | Async Worker |
| 10 | **LipSync Synchronization** | `/v1/videos/lipsync` | Keling/LivePortrait Audio-Driven Facial Rigging | Async Worker |
| 11 | **OCR & Document Reading** | `/v1/ocr/id`, `/v1/ocr/dl` | PaddleOCR Vietnamese CCCD & Driver's License | Sync / Async |
| 12 | **FaceMatch eKYC** | `/v1/vision/facematch` | InsightFace ArcFace Biometric Recognition | Sync |
| 13 | **Liveness Detection** | `/v1/vision/liveness` | Silent-Face-Anti-Spoofing MiniFASNetV2 | Sync |

---

## ⚡ Quick Start

### 1. Prerequisites
- **OS**: Linux (Ubuntu 22.04 LTS) or Windows WSL2 (Ubuntu 22.04)
- **Python**: `>= 3.10`
- **uv**: Fast Rust-based Python package manager (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Docker & Docker Compose**: For local infrastructure services
- **NVIDIA GPU** *(Optional for local simulation, required for full inference)*: CUDA 12.x drivers

### 2. Monorepo Setup
```bash
# Setup virtual environment and link all monorepo packages in editable mode
make setup
```

### 3. Start Core Infrastructure (Docker)
```bash
# Option A: Start core data stores (MongoDB, Redis, RabbitMQ, MinIO)
make dev-env

# Option B: Start full infrastructure stack (+ Prometheus, Grafana, Alertmanager)
make dev-env-full
```

### 4. Run Services

#### Tầng 1: Control-Plane API Gateway
```bash
make dev-gateway
# API Gateway runs on http://localhost:8000
# Swagger Docs: http://localhost:8000/docs
```

#### Tầng 2: Data-Plane AI Microservices
```bash
# Terminal 2A: vLLM Unified Serving Engine (Qwen / Llama / Embeddings)
make dev-vllm

# Terminal 2B: Translation Service (GPU-accelerated MarianMT)
make dev-translation

# Terminal 2C: Speech-to-Text Service (PhoWhisper)
make dev-stt
```

#### Tầng 3: Distributed Asynchronous Workers
```bash
# Terminal 4: Dispatcher Worker & Stale Job Auto-Reconciler
make dev-dispatcher

# Terminal 5: Callback Worker (HMAC-SHA256 Webhook Deliveries)
make dev-callback

# Terminal 6: GPU Image Generation Worker (FLUX.1 / SDXL)
make worker-image
```

### 5. Run Web UI Portal (Vite)
```bash
make ui
# Portal URL: http://localhost:5173/staff/dashboard
```

---

## 🖥️ Developer & Staff Web Portal

Access the developer console directly in your browser:
- 📊 **Staff Dashboard**: [http://localhost:5173/staff/dashboard](http://localhost:5173/staff/dashboard) — Live GPU telemetry, active request counters, and credit balances.
- 🧪 **API Playground & Sandboxes**: [http://localhost:5173/staff/apis](http://localhost:5173/staff/apis) — Test all 13 AI services directly in your browser.
- 🔑 **API Key Management**: [http://localhost:5173/staff/keys](http://localhost:5173/staff/keys) — Generate and revoke secure Argon2id API keys.
- 📈 **Usage & Cost Reports**: [http://localhost:5173/staff/report](http://localhost:5173/staff/report) — Historical invocation graphs and breakdown by model.
- 🚦 **System Status Page**: [http://localhost:5173/status.html](http://localhost:5173/status.html) — Public cluster uptime and component health status.

---

## 💻 API Integration Examples

### Mandatory Authentication Header
All requests must include an active API key:
```http
Authorization: Bearer aip_live_your_api_key_here
Content-Type: application/json
```

### 1. Synchronous Translation (cURL)
```bash
curl -X POST "http://localhost:8000/v1/nlp/translate" \
  -H "Authorization: Bearer aip_live_testkey123" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Artificial Intelligence is transforming enterprise software.",
    "source_lang": "en",
    "target_lang": "vi"
  }'
```

**Response (HTTP 200)**:
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

### 2. Python SDK (`packages/sdk`)
```python
from aip_sdk import AIPClient

client = AIPClient(
    api_key="aip_live_testkey123",
    base_url="http://localhost:8000"
)

# Text Translation
translation = client.translate(
    text="Hệ thống trí tuệ nhân tạo vận hành rất mượt mà trên card đồ họa.",
    source_lang="vi",
    target_lang="en"
)
print("Result:", translation.translated_text)
```

### 3. C# .NET 8 SDK (`sdks/dotnet`)
```csharp
using Everwin.AIPlatform.SDK;

var client = new AIPClient("aip_live_testkey123", "http://localhost:8000");

var response = await client.CreateChatCompletionAsync(
    model: "chat-general-standard",
    prompt: "Xin chào từ ứng dụng .NET 8!"
);
```

### 4. Standard SRS Error Envelope
In case of errors, the Gateway guarantees a standardized SRS Error Envelope:
```json
{
  "error": {
    "code": "INVALID_API_KEY",
    "message": "The provided API key is invalid or revoked",
    "details": {},
    "request_id": "req_650fa89b-fbf7-42c2-8419-74d754b2d189",
    "timestamp": "2026-09-22T13:45:00.000Z"
  }
}
```

---

## 🛡️ Reliability & Distributed Messaging Architecture

```mermaid
flowchart LR
    Client([Downstream Client]) -->|HTTP POST| Gateway[AIP Gateway]
    Gateway -->|Lightweight / Real-time| Services[Services: MarianMT / PhoWhisper]
    Gateway -->|Heavy Tasks| ExTasks[Exchange: ex.aip.tasks]
    
    ExTasks -->|q.aip.tasks.image| ImageWorker[Image Worker FLUX.1]
    ExTasks -->|q.aip.tasks.video| VideoWorker[Video Worker Wan2.2]
    ExTasks -->|q.aip.tasks.lipsync| LipSyncWorker[LipSync Worker LivePortrait]
    
    ImageWorker -->|Result Event| ExEvents[Exchange: ex.aip.events]
    VideoWorker -->|Result Event| ExEvents
    LipSyncWorker -->|Result Event| ExEvents
    
    ExEvents -->|q.aip.events.callbacks| CallbackWorker[Callback Worker]
    CallbackWorker -->|HMAC-SHA256 Webhook| WebhookUrl([Client Webhook URL])
    
    ExTasks -.->|Failure / Reject| DLQ[Queue: q.aip.tasks.dlq]
    Reconciler[Stale Job Auto-Reconciler] -.->|Scan Stale Tasks| MongoDB[(MongoDB Atlas)]
```

- **Topic Routing**: Tasks route through `ex.aip.tasks` with routing keys like `task.image.generate`, `task.video.render`.
- **Dead-Letter Queue (DLQ)**: Failed tasks after retry are routed to `q.aip.tasks.dlq` without blocking the pipeline.
- **SSRF NetGuard**: Strict private IP range protection preventing attackers from targeting internal loopbacks/metadata endpoints via webhooks.
- **HMAC-SHA256 Webhook Signatures**: Webhook payloads are signed with a shared secret and timestamp header `X-AIP-Signature: t=...,v1=...` to prevent tampering and replay attacks.
- **Self-Healing Reconciler**: Background cron identifies jobs stuck in `processing` beyond their timeout and automatically marks them failed or re-enqueues them.

---

## 🚢 Kubernetes & Helm Deployment

For enterprise container orchestration, use the included Helm charts in `deploy/`:

```bash
# 1. Apply Kubernetes Namespaces
kubectl apply -f deploy/k8s/namespaces/namespaces.yaml

# 2. Deploy Core Infrastructure (MongoDB, Redis, RabbitMQ, MinIO)
helm upgrade --install aip-infra deploy/helm/aip-infra \
  --namespace aip-infra \
  --create-namespace \
  --wait

# 3. Deploy Control Plane API Gateway
helm upgrade --install aip-control deploy/helm/aip-control \
  --namespace aip-control \
  --create-namespace \
  --wait

# 4. Deploy AI Workload Runtimes (GPU-accelerated pods)
helm upgrade --install aip-runtimes deploy/helm/aip-runtimes \
  --namespace aip-multimodal \
  --create-namespace \
  --wait
```

---

## 🧪 Testing & Quality Assurance

The codebase includes a comprehensive 32-test automated test suite covering all architecture tiers:
```bash
# Run the complete test suite (100% Pass)
make test

# Run code linter
make lint

# Auto-format and fix lint issues
make fmt
```

---

*Everwin AI Platform — Mission-Critical Enterprise AI Middleware.*
