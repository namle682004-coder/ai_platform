# AIP Platform
> Enterprise AI Inference Middleware & Distributed Execution Engine

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-green.svg)](https://fastapi.tiangolo.com)
[![gRPC](https://img.shields.io/badge/RPC-gRPC_Protobuf-244c5a.svg)](https://grpc.io)
[![uv](https://img.shields.io/badge/Package_Manager-uv-blueviolet.svg)](https://astral.sh/uv)
[![RabbitMQ](https://img.shields.io/badge/Broker-RabbitMQ_AMQP-orange.svg)](https://rabbitmq.com)
[![Tests](https://img.shields.io/badge/Tests-112%2F112_Passing-brightgreen.svg)]()
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)]()

---

## Overview

**AIP Platform** is an enterprise-grade, self-hosted AI inference middleware platform and developer console. Built with **Clean Architecture & Domain-Driven Design (DDD)**, it acts as an intelligent distribution, governance, and execution layer between downstream business applications and upstream heterogeneous AI compute nodes (NVIDIA GPUs & CPUs).

### Core Capabilities:
- **Standardized `/v1` AI APIs**: Drop-in unified endpoints for 7 verified core AI models aligned with local 4GB VRAM GPU hardware.
- **Dual Arterial Communication Protocols**: High-throughput multiplexed **gRPC binary data-plane** (:50051–:50056) for sub-millisecond inference combined with **RabbitMQ message queuing** for resilient asynchronous task offloading.
- **Zero-Trust Security & Governance**: Argon2id salted API key hashing with Master Pepper, strict CIDR IP allowlisting, and project-based tenant isolation.
- **Intelligent Task Routing & Dispatch**: Modular DCP-pattern `dispatcher-worker` with dynamic task resolution (`task_resolver`), gRPC client execution (`inference_client`), jittered exponential backoff (`retry`), and dead-letter queue routing (`DLQ`).
- **Event-Driven Resilience**: Native DLQ dead-lettering, TTL message expirations, Redis-backed idempotency protection, HMAC-SHA256 signed webhooks, and automatic stale job reconciliation.
- **Real-time Hardware Telemetry**: Native NVIDIA NVML integration monitoring real GPU core temperatures, VRAM consumption, and wattage with automated hardware allocation guards.
- **Developer & Staff Self-Service Portal**: Integrated Web Console, interactive API Sandbox, Key Management, and public System Status page.

### Implementation Status & Deployment Readiness

| Tier / Component | Target Artifact | Implementation State | Deployment Target | Notes |
| --- | --- | :---: | :---: | --- |
| **Control Plane** | `apps/control-plane` | Production Implemented | Render PaaS / K8s `aip-control` | FastAPI, Argon2id, Quota Lua scripts, Active `/health/ready` probe, Model Aliases, Dynamic UUID Routing |
| **Developer Console** | `apps/frontend` | Production Implemented | Render PaaS / Vite Static | Inter/Monochrome Enterprise UI, `/project/{id}/apis/{id}` routing, Sandbox playgrounds |
| **Text & Audio Runtimes** | `apps/data-plane` | Production Implemented | Docker Compose / K8s `aip-text`, `aip-multimodal` | CTranslate2 MarianMT, Faster-Whisper, EasyOCR, PhoBERT, vi-VN-Neural (Dual HTTP + gRPC) |
| **Dispatcher Worker** | `apps/dispatcher-worker` | Production Implemented | Docker Compose / K8s `aip-infra` | Modular DCP Consumer, TaskResolver, gRPC Client, Jittered Retry, Stale Reconciler |
| **Callback Worker** | `apps/callback-worker` | Production Implemented | Docker Compose / K8s `aip-infra` | HMAC-SHA256 Signed Webhook Delivery with exponential backoff |
| **Image Worker** | `apps/image-worker` | Implemented (Diffusers / MinIO) | Docker Compose / K8s `aip-multimodal` | Async task consumer for FLUX.1 / SDXL image generation |
| **Video & LipSync Workers**| `apps/{video,lipsync}-worker` | Specification / Blueprint | Future GPU Nodes (`aip-video`) | AMQP schema and task envelope contracts defined in `packages/contracts` |
| **Storage & Messaging** | MongoDB, Redis, RabbitMQ, MinIO | Production Implemented | Atlas (Mongo) / Docker / K8s `aip-infra` | Native priority queues, dead-letter exchanges, multi-namespace synchronized secrets |

---

## Clean Architecture Monorepo Structure (`apps/` Layout)

The codebase follows the enterprise monorepo workspace standard, consolidating all runnable microservices and workers cleanly under `apps/` with shared kernels in `packages/`:

```text
ai_platform/
├── apps/                               # Core Monorepo Deployable Applications
│   ├── control-plane/                  # Tier 1: API Gateway (FastAPI), Auth (Argon2id), Quotas, Model Aliases, Web Console
│   │   ├── src/api/                    # REST routers (/v1/chat, /v1/nlp, /v1/audio, /v1/vision, /v1/jobs, etc.)
│   │   ├── src/auth/                   # Argon2id hasher, key validation, Master Pepper security
│   │   ├── src/quota/                  # Redis Lua atomic rate limits (RPM, TPM, in-flight concurrency)
│   │   ├── src/aliases/                # Logical-to-physical model alias resolution & Mongo Atlas loader
│   │   ├── src/publisher/              # RabbitMQ AMQP 0-9-1 topology & task publisher
│   │   └── src/grpc_helpers/           # Control Plane gRPC client manager & channel pooling
│   │
│   ├── data-plane/                     # Tier 2: Unified Inference Serving Nodes (Dual HTTP & gRPC)
│   │   ├── vllm-engine/                # High-Throughput LLM & Embedding Server (HTTP :8001 / gRPC :50051)
│   │   ├── stt-server/                 # Faster-Whisper Speech-to-Text (HTTP :8002 / gRPC :50052)
│   │   ├── translation-server/         # MarianMT/CTranslate2 En <-> Vi Live on GPU (HTTP :8003 / gRPC :50053)
│   │   ├── ocr-server/                 # EasyOCR Document & Identity Digitization (HTTP :8004 / gRPC :50054)
│   │   ├── moderation-server/          # PhoBERT Safety & Content Moderation (HTTP :8006 / gRPC :50055)
│   │   ├── tts-adapter/                # vi-VN-Neural Speech Synthesis (HTTP :8007 / gRPC :50056)
│   │   └── runtime-probe/              # Hardware telemetry probe & NVML health checker
│   │
│   ├── dispatcher-worker/              # Tier 3: Modular DCP Task Dispatcher & Reconciler
│   │   └── src/
│   │       ├── consumer/               # AMQP queue listener with prefetch=5 & connection recovery
│   │       ├── resolver/               # Dynamic TaskResolver mapping domain/alias to gRPC endpoints
│   │       ├── grpc_client/            # Asynchronous InferenceClient invoking compiled Protobuf stubs
│   │       ├── retry/                  # Jittered exponential backoff & DLQ error classifier
│   │       ├── publisher/              # CallbackPublisher emitting lifecycle events to aip.events
│   │       ├── reconciler/             # StaleReconciler auto-healing orphan/stuck jobs (> 15m)
│   │       └── main.py                 # Single unified async entrypoint with graceful shutdown
│   │
│   ├── callback-worker/                # Tier 3: HMAC-SHA256 Signed Webhook Notification Delivery
│   ├── image-worker/                   # Tier 3: FLUX.1 & SDXL High-Res Image Generation Worker
│   ├── video-worker/                   # Tier 3: Wan2.2 & CogVideoX Text-to-Video Generation Worker
│   ├── lipsync-worker/                 # Tier 3: LivePortrait Audio-Driven Lip Synchronization Worker
│   └── frontend/                       # Developer & Staff Web UI Portal (Vite + Vanilla JS)
│
├── packages/                           # Shared Kernel Libraries
│   ├── common/                         # Core domain schemas, Argon2id security, Mongo & Redis repositories
│   ├── contracts/                      # Protobuf contracts (inference.proto, jobs.proto), compiled stubs & AMQP schemas
│   └── sdk/                            # Official Python Client SDK (`aip-sdk`)
│
├── migrations/                         # Database Schema & Data Migrations (SRS Section 11.2)
│   ├── 001_initial_mongo_indexes.py    # Production indexes for API keys, users, jobs TTL, audit logs
│   ├── 002_seed_catalogs.py            # Idempotent seed for verified 7 core model catalog
│   └── runner.py                       # Migration runner tracking execution state in _migrations_meta
│
├── infrastructure/                     # Observability & Monitoring
│   ├── prometheus/                     # Prometheus scrape configs & alert rules
│   ├── grafana/                        # Pre-configured Grafana dashboards & datasources
│   └── alertmanager/                   # Alertmanager notification routing
│
├── deploy/                             # Enterprise Deployment Manifests (SRS Section 11.1 & 11.3)
│   ├── docker-compose/                 # Local multi-service stack (Mongo, Redis, RabbitMQ, MinIO, Monitoring)
│   ├── helm/                           # Kubernetes Helm Charts (aip-control, aip-runtimes, aip-infra)
│   └── k8s/                            # Raw K8s manifests, NetworkPolicies, Namespaces & Secrets
│
├── sdks/                               # Multi-language Client SDKs (.NET 8 LTS C# Solution - AIP.Platform.SDK)
├── openapi/                            # OpenAPI 3.1 specifications & Postman Collection
├── scripts/                            # Core operational automation utilities
│   ├── export_api_assets.py            # OpenAPI JSON, Postman Collection & Redoc documentation generator
│   ├── manage_services.sh              # 1-Click native lifecycle management (start/stop/status/restart)
│   ├── prepare_translation_model.py    # MarianMT model weight conversion for CTranslate2
│   └── quick_check.sh                  # Instant health probe across all AI runtimes and gateway
└── tests/                              # Automated Pytest CI/CD test suite (112 tests, 100% pass)
```

---

## Core Model Catalog (Local 4GB VRAM Hardware Baseline)

In strict adherence to real local hardware capabilities (**4GB VRAM GPU baseline**), the platform standardizes on **7 core production models** optimized for low footprint and sub-millisecond response:

| # | Logical Alias | Route | Physical Model / Runtime Engine | VRAM | Ports | Mode |
|---|---|---|---|:---:|:---:|---|
| 1 | `chat-general-standard` | `/v1/chat/completions` | `Qwen2.5-1.5B-Instruct` (vLLM) | 2GB | `:8001` / `:50051` | Sync / SSE Stream |
| 2 | `embed-standard` | `/v1/embeddings` | `Qwen2.5-1.5B-Instruct` (Mean-pooled) | 0GB | `:8001` / `:50051` | Sync |
| 3 | `translate-vi-standard` | `/v1/nlp/translate` | `opus-mt-vi-en` (CTranslate2) | 1GB | `:8003` / `:50053` | Sync / Async |
| 4 | `stt-whisper-small` | `/v1/audio/transcriptions` | `faster-whisper-small` (ASR) | 1GB | `:8002` / `:50052` | Sync / Async |
| 5 | `tts-vi-standard` | `/v1/audio/speech` | `vi-VN-Neural` (tts-adapter) | 0.5GB | `:8007` / `:50056` | Sync / Async |
| 6 | `ocr-vietnamese-id` | `/v1/ocr/id` | `EasyOCR-Vietnamese-ID` (EasyOCR) | 1GB | `:8004` / `:50054` | Sync / Async |
| 7 | `moderation-standard` | `/v1/moderations` | `PhoBERT-base + Rules` (Safety Engine) | 0.5GB | `:8006` / `:50055` | Sync |

> [!NOTE]
> Heavy asynchronous workloads (Image generation with FLUX.1, Video generation with Wan2.2, and LipSync with LivePortrait) are structurally defined in `apps/image-worker`, `apps/video-worker`, and `apps/lipsync-worker`. Their task contracts and queues (`q.aip.jobs.*`) are fully wired, ready for execution when dedicated high-VRAM GPU compute nodes (>= 40GB VRAM) are added to the cluster.

---

## Two Arterial Protocols: RabbitMQ & gRPC

AIP Platform integrates two complementary arterial communication protocols to achieve high throughput, strict governance, and zero data loss:

```mermaid
flowchart TD
    Client([Downstream Client]) -->|HTTP / REST Bearer Token| Gateway[apps/control-plane<br/>API Gateway :8000]

    subgraph FastLane["Fast-Lane: Sub-Millisecond Binary gRPC / HTTP"]
        Gateway -->|gRPC :50051 / HTTP :8001| VLLM["vLLM Engine (Qwen2.5-1.5B)"]
        Gateway -->|gRPC :50053 / HTTP :8003| Trans["Translation Server (opus-mt-vi-en)"]
        Gateway -->|gRPC :50052 / HTTP :8002| STT["STT Server (faster-whisper)"]
        Gateway -->|gRPC :50054 / HTTP :8004| OCR["OCR Server (EasyOCR-ID)"]
        Gateway -->|gRPC :50055 / HTTP :8006| Mod["Moderation Server (PhoBERT)"]
        Gateway -->|gRPC :50056 / HTTP :8007| TTS["TTS Adapter (vi-VN-Neural)"]
    end

    subgraph SlowLane["Slow-Lane: Asynchronous Event-Driven Messaging"]
        Gateway -->|Publish Task| ExTasks["Exchange: aip.tasks (Priority 1-10)"]
        ExTasks -->|q.aip.tasks.*| Dispatcher["apps/dispatcher-worker<br/>(TaskConsumer + TaskResolver)"]
        
        Dispatcher -->|gRPC Predict| FastLane
        Dispatcher -->|Delegate Heavy GPU| ImgW["apps/image-worker (FLUX.1)"]
        Dispatcher -->|Delegate Heavy GPU| VidW["apps/video-worker (Wan2.2)"]
        Dispatcher -->|Delegate Heavy GPU| LipW["apps/lipsync-worker (LivePortrait)"]
        
        ImgW -->|Store Artifact| MinIO[("MinIO S3")]
        VidW -->|Store Artifact| MinIO
        LipW -->|Store Artifact| MinIO
        
        Dispatcher -->|Publish Event| ExEvents["Exchange: aip.events"]
        ExEvents -->|q.aip.events.callbacks| CallbackW["apps/callback-worker"]
        CallbackW -->|HMAC-SHA256 Webhook| WebhookUrl([Client Webhook URL])
        
        Dispatcher -.->|Terminal Error| DLQ["Queue: q.aip.tasks.dlq"]
        Reconciler["StaleReconciler (>15m)"] -.->|Audit Stuck Jobs| Mongo[("MongoDB Atlas")]
    end
```

### 1. RabbitMQ (AMQP 0-9-1) — Asynchronous Resilience & Decoupling
- **Decoupling**: Heavy tasks (image synthesis, video rendering, document batch OCR) are acknowledged in `< 50ms` with `202 Accepted` while execution proceeds in the background.
- **Backpressure & Load Leveling**: Workers pull tasks based on actual GPU memory availability (`prefetch_count=5`), eliminating VRAM saturation.
- **Durability & At-least-once**: All task envelopes are published with `delivery_mode=2` (persistent) to quorum queues.
- **Priority Scheduling**: Native RabbitMQ `x-max-priority: 10` drains interactive UI requests ahead of batch offline workloads.
- **Dead-Letter Routing (DLX)**: Retries exceeding the backoff threshold are routed to `q.aip.tasks.dlq` for post-mortem inspection.

### 2. gRPC (HTTP/2 + Protobuf) — Binary Data-Plane Topology
- **Binary Serialization**: Zero JSON parsing overhead for large embedding vectors, token streams, and audio buffers using Protobuf contracts defined in `packages/contracts/contracts/inference.proto`.
- **Multiplexing**: A single persistent TCP connection handles concurrent bi-directional RPC streams.
- **Dedicated Port Mapping**:
  - `:50051`: `vllm-engine` (`InferenceService.Predict`, `InferenceService.PredictStream`)
  - `:50052`: `stt-server` (`InferenceService.Predict`)
  - `:50053`: `translation-server` (`InferenceService.Predict`)
  - `:50054`: `ocr-server` (`InferenceService.Predict`)
  - `:50055`: `moderation-server` (`InferenceService.Predict`)
  - `:50056`: `tts-adapter` (`InferenceService.Predict`, `InferenceService.PredictStream`)

---

## Quick Start

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

#### Tier 1: Control-Plane API Gateway
```bash
make dev-gateway
# API Gateway runs on http://localhost:8000
# Interactive Swagger: http://localhost:8000/docs
```

#### Tier 2: Data-Plane AI Microservices (1-Click or Individual)
```bash
# 1-Click start all native data-plane services
make start-all

# Or start individually:
make dev-vllm         # vLLM Serving Engine (:8001 / :50051)
make dev-translation  # MarianMT Translation (:8003 / :50053)
make dev-stt          # Speech-to-Text (:8002 / :50052)
make dev-ocr          # EasyOCR Vietnamese ID (:8004 / :50054)
make dev-moderation   # PhoBERT Content Moderation (:8006 / :50055)
make dev-tts          # vi-VN-Neural TTS Adapter (:8007 / :50056)
```

#### Tier 3: Distributed Asynchronous Workers
```bash
# Dispatcher Worker (Domain Tasks & Stale Reconciler)
make dev-dispatcher

# Callback Worker (HMAC-SHA256 Webhook Deliveries)
make dev-callback

# Specialized GPU Workers
make worker-image     # FLUX.1 / SDXL Image Generation Worker
```

### 5. Run Web UI Portal (Vite)
```bash
make ui
# Portal URL: http://localhost:5173/staff/dashboard
```

---

## Developer & Staff Web Portal

Access the developer console directly in your browser:
- **Staff Dashboard**: [http://localhost:5173/staff/dashboard](http://localhost:5173/staff/dashboard) — Live GPU telemetry, active request counters, and credit balances.
- **API Playground & Sandboxes**: [http://localhost:5173/staff/apis](http://localhost:5173/staff/apis) — Test verified core AI services directly in your browser.
- **API Key Management**: [http://localhost:5173/staff/keys](http://localhost:5173/staff/keys) — Generate and revoke secure Argon2id API keys.
- **Usage & Cost Reports**: [http://localhost:5173/staff/report](http://localhost:5173/staff/report) — Historical invocation graphs and breakdown by model.
- **System Status Page**: [http://localhost:5173/status.html](http://localhost:5173/status.html) — Public cluster uptime and component health status.

---

## API Integration Examples

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

### 3. C# .NET 8 SDK (`sdks/dotnet/AIP.Platform.SDK`)
```csharp
using AIP.Platform.SDK;

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
    "timestamp": "2026-09-29T11:45:00.000Z"
  }
}
```

---

## Kubernetes & Helm Deployment

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

## Testing & Quality Assurance

The codebase includes a comprehensive 112-test automated test suite covering all architecture tiers:
```bash
# Run the complete test suite (112/112 Pass)
make test

# Run code linter
make lint

# Auto-format and fix lint issues
make fmt
```

---

*AIP Platform — Mission-Critical Enterprise AI Middleware.*
