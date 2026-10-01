# AIP Platform
> Enterprise AI Inference Middleware & Distributed Execution Engine

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-green.svg)](https://fastapi.tiangolo.com)
[![gRPC](https://img.shields.io/badge/RPC-gRPC_Protobuf_v2-244c5a.svg)](https://grpc.io)
[![uv](https://img.shields.io/badge/Package_Manager-uv-blueviolet.svg)](https://astral.sh/uv)
[![RabbitMQ](https://img.shields.io/badge/Broker-RabbitMQ_Quorum_Queues-orange.svg)](https://rabbitmq.com)
[![Tests](https://img.shields.io/badge/Tests-124%2F124_Passing-brightgreen.svg)]()
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)]()

---

## Overview

**AIP Platform** is an enterprise-grade, self-hosted AI inference middleware platform and developer console. Built with **Clean Architecture & Domain-Driven Design (DDD)**, it acts as an intelligent distribution, governance, and execution layer between downstream business applications and upstream heterogeneous AI compute nodes (NVIDIA GPUs & CPUs).

### Core Capabilities:
- **Standardized `/v1` AI APIs**: Drop-in unified endpoints for verified core AI models aligned with local GPU hardware.
- **Dual Arterial Communication Architecture**:
  - **Synchronous gRPC Fast-Lane**: Sub-millisecond direct multiplexed gRPC connection from Control Plane API Gateway to inference runtimes, bypassing queue delay for real-time applications.
  - **Asynchronous Quorum Queues (AMQP 0-9-1)**: High-resilience, Raft-consensus messaging pipeline for heavy batch jobs with automatic broker-level retry and dead-letter protection.
- **Dedicated gRPC Proto Contracts (ISP Compliant)**: Granular, service-segregated protobuf definitions (`llm.proto`, `stt.proto`, `translation.proto`, `ocr.proto`, `tts.proto`) providing clean bounded contexts and independent service lifecycles.
- **Broker-Level Delayed Retry (`x-delayed-message`)**: Zero in-process blocking `asyncio.sleep()`. Failed transient tasks are parked in RabbitMQ delayed exchange with exponential jittered backoff, keeping Worker event loops 100% available.
- **Thin Task Envelopes**: Large payloads (documents, raw audio, base64 images) are stored directly in MongoDB Atlas (`job_record.payload`). Only minimal metadata and IDs traverse the AMQP broker, preventing memory ballooning.
- **Hardware & VRAM Lifecycle Management**: Real `Cancel` RPC integration aborts running GPU asyncio coroutines immediately upon client disconnect, preventing VRAM waste.
- **Zero-Trust Security & Governance**: Argon2id salted API key hashing with Master Pepper, strict CIDR IP allowlisting, and project-based tenant isolation.
- **Developer & Staff Self-Service Portal**: Integrated Web Console, interactive API Sandbox, Key Management, and public System Status page.

---

### Implementation Status & Deployment Readiness

| Tier / Component | Target Artifact | Implementation State | Deployment Target | Architecture Highlights |
| --- | --- | :---: | :---: | --- |
| **Control Plane** | `apps/control-plane` | Production Implemented | Render PaaS / K8s `aip-control` | FastAPI, Argon2id, Quota Lua scripts, Active `/health/ready` probe, Model Aliases, Dynamic UUID Routing, **gRPC Fast-Lane** |
| **Developer Console** | `apps/frontend` | Production Implemented | Render PaaS / Vite Static | Inter/Monochrome Enterprise UI, `/project/{id}/apis/{id}` routing, Sandbox playgrounds |
| **Data-Plane Runtimes** | `apps/data-plane` | Production Implemented | Docker Compose / K8s `aip-text`, `aip-multimodal` | **Dual-Port Runtimes** (HTTP & dedicated gRPC per modality), GPU task cancellation, typed health checks |
| **Dispatcher Worker** | `apps/dispatcher-worker` | Production Implemented | Docker Compose / K8s `aip-infra` | Modular DCP Consumer, `prefetch_count=1`, TaskResolver, gRPC Client, Broker-delayed Retry, Stale Reconciler |
| **Callback Worker** | `apps/callback-worker` | Production Implemented | Docker Compose / K8s `aip-infra` | HMAC-SHA256 Signed Webhook Delivery with exponential backoff |
| **Image Worker** | `apps/image-worker` | Implemented (Diffusers / MinIO) | Docker Compose / K8s `aip-multimodal` | Async task consumer for FLUX.1 / SDXL image generation |
| **Messaging & Storage** | MongoDB, Redis, RabbitMQ, MinIO | Production Implemented | Atlas (Mongo) / Docker / K8s `aip-infra` | **Quorum Queues (Raft)**, Physical Priority Queues, `x-delayed-message` plugin, DLQ governance |

---

## Clean Architecture Monorepo Structure (`apps/` & `packages/`)

The codebase follows the enterprise monorepo workspace standard, consolidating all runnable microservices cleanly under `apps/` with shared decoupling kernels in `packages/`:

```text
ai_platform/
├── apps/                               # Deployable Applications & Services
│   ├── control-plane/                  # Tier 1: API Gateway (FastAPI), Auth (Argon2id), Quotas, Model Aliases, Fast-Lane
│   │   ├── src/api/                    # REST routers (/v1/chat, /v1/nlp, /v1/audio, /v1/vision, /v1/jobs)
│   │   ├── src/auth/                   # Argon2id hasher, key validation, Master Pepper security
│   │   ├── src/quota/                  # Redis Lua atomic rate limits (RPM, TPM, in-flight concurrency)
│   │   ├── src/aliases/                # Logical-to-physical model alias resolution & Mongo Atlas loader
│   │   └── src/grpc_helpers/           # Control Plane gRPC Client Manager with channel pooling & Fast-Lane
│   │
│   ├── data-plane/                     # Tier 2: AI Serving Runtimes (Dual HTTP & Dedicated gRPC)
│   │   ├── vllm-engine/                # High-Throughput LLM & Embedding (HTTP :8001 / gRPC :50051)
│   │   ├── stt-server/                 # Faster-Whisper Speech-to-Text (HTTP :8002 / gRPC :50052)
│   │   ├── translation-server/         # MarianMT/CTranslate2 En <-> Vi (HTTP :8003 / gRPC :50053)
│   │   ├── ocr-server/                 # EasyOCR / PaddleOCR-VL Document Server (HTTP :8004 / gRPC :50054)
│   │   └── tts-adapter/                # viXTTS Neural Speech Synthesizer (HTTP :8005 / gRPC :50055)
│   │
│   ├── dispatcher-worker/              # Tier 3: Modular Asynchronous Task Consumer
│   │   ├── src/consumer/               # RabbitMQ consumer (prefetch_count=1, Quorum Queue binding)
│   │   ├── src/resolver/               # TaskResolver mapping task types to execution handlers
│   │   ├── src/client/                 # gRPC inference client with strict typed error handling
│   │   └── src/retry/                  # DelayedRetryPublisher publishing to x-delayed-message exchange
│   │
│   ├── callback-worker/                # Webhook Delivery Worker (HMAC-SHA256 signature verification)
│   └── frontend/                       # Developer & Staff Web Console (React / Vite)
│
├── packages/                           # Shared Monorepo Kernels & Libraries
│   ├── common/                         # Core Kernel (shared across all apps and workers)
│   │   └── common/messaging/           # Decoupled Messaging Kernel: Topology, Quorum Queues, Publisher
│   └── contracts/                      # Enterprise Protobuf & Data Transfer Contracts
│       ├── contracts/proto/            # Dedicated Proto definitions: common, llm, stt, translation, ocr, tts
│       └── contracts/generated/        # Pre-compiled Python gRPC stubs and message types
```

---

## Dual Arterial Execution Architecture

AIP incorporates an enterprise-grade **Dual Arterial Execution Model** that bridges synchronous low-latency inference with resilient asynchronous batch processing:

```mermaid
flowchart TD
    Client(["Enterprise Client / Frontend"]) -->|HTTP REST / SSE| CP["apps/control-plane (FastAPI)"]
    
    subgraph ARTERIAL_1 ["Arterial 1: Synchronous gRPC Fast-Lane"]
        CP -->|Direct gRPC (:50051-:50055)| DP["Data-Plane AI Serving Nodes"]
        DP -->|Sub-millisecond Binary Stream| CP
        CP -->|Immediate Response / SSE| Client
    end

    subgraph ARTERIAL_2 ["Arterial 2: Asynchronous Quorum Queue Pipeline"]
        CP -->|Thin Task Envelope| ExJobs["Exchange: aip.jobs (Topic)"]
        CP -->|Store Payload Data| Mongo[("MongoDB Atlas")]
        
        ExJobs -->|Raft Consensus| QQ["Quorum Queues: q.aip.tasks.{domain}.{priority}"]
        QQ -->|Fair Dispatch (prefetch=1)| DispW["apps/dispatcher-worker"]
        
        DispW -->|Dedicated gRPC Execution| DP
        DispW -->|Update Status & Result| Mongo
        
        DispW -.->|Transient Error| ExDelay["Exchange: aip.jobs.delayed (x-delayed-message)"]
        ExDelay -.->|Delayed Repush| QQ
        
        DispW -.->|Terminal Error / Max Deliveries (4)| DLQ["Quorum Queue: q.aip.tasks.dlq"]
        
        DispW -->|Task Complete Event| ExEvents["Exchange: aip.events"]
        ExEvents --> CallbackW["apps/callback-worker"]
        CallbackW -->|HMAC-SHA256 Webhook| WebhookUrl([Client Webhook URL])
    end
```

### 1. RabbitMQ Messaging & Topology Highlights
- **Quorum Queues (`x-queue-type: quorum`)**: Built on the Raft consensus algorithm, guaranteeing zero message loss even if a RabbitMQ broker node restarts.
- **Thin Task Envelopes**: Full heavy payloads are stored in MongoDB. The AMQP message envelope carries only job routing keys and IDs (`job_id`, `task_id`, `domain`, `priority`), keeping message sizes < 1KB.
- **Physical Priority Queues**: Separate physical queues per priority level (`.high`, `.normal`, `.batch`) prevent head-of-line blocking by long batch jobs.
- **Broker-Level Delayed Retry**: Leverages the official `rabbitmq_delayed_message_exchange-3.13.0` plugin. Failed tasks are parked in the broker with exponential delay (30s, 60s, 120s, 240s) without consuming Worker compute cycles.
- **Dead-Letter Queue Governance**: Standardized `q.aip.tasks.dlq` configured with a 14-day message TTL and a 10GB storage limit.

### 2. Dedicated Data-Plane gRPC Topology
- **Dedicated Proto Per Modality**: Adheres to the **Interface Segregation Principle (ISP)**. Each service has its own dedicated contract:
  - `:50051`: `vllm-engine` (`LlmService`: `ChatCompletion`, `StreamChatCompletion`, `GetHealth`, `Cancel`)
  - `:50052`: `stt-server` (`SttService`: `TranscribeAudio`, `GetHealth`, `Cancel`)
  - `:50053`: `translation-server` (`TranslationService`: `Translate`, `GetHealth`, `Cancel`)
  - `:50054`: `ocr-server` (`OcrService`: `ExtractDocument`, `GetHealth`, `Cancel`)
  - `:50055`: `tts-adapter` (`TtsService`: `SynthesizeSpeech`, `GetHealth`, `Cancel`)
- **Lifecycle Triad**: Every gRPC service supports `GetHealth` for active probes and `Cancel` for aborting running GPU tasks.
- **VRAM Leak Prevention**: Calling `Cancel` directly calls `asyncio.Task.cancel()` on the running GPU coroutine, freeing compute and memory instantly.
- **Strict Typed Errors**: Categorizes exceptions into `InferenceTransientError` (retried) vs `InferenceTerminalError` (immediately sent to DLQ).

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
# Start core data stores with delayed message exchange plugin
make dev-env
```

### 4. Run Services

#### Tier 1: Control-Plane API Gateway
```bash
make dev-gateway
# API Gateway runs on http://localhost:8000
# Interactive Swagger: http://localhost:8000/docs
```

#### Tier 2: Data-Plane AI Microservices
```bash
# Start all data-plane services with Dual HTTP & gRPC ports
make start-all

# Or start individually:
make dev-vllm         # vLLM Engine (:8001 / gRPC :50051)
make dev-stt          # Speech-to-Text (:8002 / gRPC :50052)
make dev-translation  # Translation (:8003 / gRPC :50053)
make dev-ocr          # OCR Server (:8004 / gRPC :50054)
make dev-tts          # TTS Adapter (:8005 / gRPC :50055)
```

#### Tier 3: Distributed Asynchronous Workers
```bash
# Dispatcher Worker (Quorum Queue Consumer & gRPC Dispatcher)
make dev-dispatcher

# Callback Worker (HMAC-SHA256 Webhook Deliveries)
make dev-callback
```

### 5. Run Web UI Portal (Vite)
```bash
make ui
# Portal URL: http://localhost:5173/staff/dashboard
```

---

## Testing & Quality Assurance

The codebase includes a comprehensive 124-test automated test suite covering all architecture tiers:
```bash
# Run the complete test suite (124/124 Pass)
pytest tests/ -v

# Run gRPC data-plane integration tests
pytest tests/test_grpc_client.py tests/test_grpc_inference_client_errors.py
```

---

*AIP Platform — Mission-Critical Enterprise AI Middleware.*
