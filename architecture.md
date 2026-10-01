# AIP Platform Architecture

**Status:** Enterprise Implementation Map (Dual Arterial & Decoupled Clean Architecture) · **Last updated:** October 1, 2026  
**Scope:** Self-hosted AI inference gateway, high-throughput synchronous/asynchronous data-plane runtimes, modular DCP-pattern workers, and distributed storage.  
**Hardware Baseline:** Local multi-model deployment standardized and optimized for local GPU and CPU fallback.  
**Core Protocols:** **Dedicated gRPC binary data-plane topology** (`:50051`–`:50055`) and **RabbitMQ Quorum Queues & Delayed Messaging** (`aip.jobs`, `aip.jobs.delayed`, `aip.jobs.dlx`, `aip.events`).

This document describes the actual, implemented architecture of the **AIP Platform** as it exists in this codebase. It adheres strictly to **Architectural Truthfulness**: reflecting real code, actual model weights, active Docker Compose services, and working Kubernetes manifests.

**Related source-of-truth documents and code**

- [README](README.md) — repository overview, quick start, and local development.
- [Docker Compose stack](deploy/docker-compose/docker-compose.yml) — local services, profiles, ports, and dependencies.
- [Static model catalog](packages/common/common/models/catalog.py) — official verified core models catalog.
- [RabbitMQ Decoupled Kernel](packages/common/common/messaging/topology.py) — Quorum Queues, Physical Priority Matrix, and Dead-Letter Governance.
- [Broker-level Delayed Retry](apps/dispatcher-worker/src/retry/delayed_retry.py) — Native `x-delayed-message` publisher with jittered backoff.
- [Protobuf Service Contracts](packages/contracts/contracts/proto/) — Dedicated ISP Proto files (`llm.proto`, `stt.proto`, `translation.proto`, `ocr.proto`, `tts.proto`, `common.proto`).
- [Modular Dispatcher Worker](apps/dispatcher-worker/src/) — DCP-pattern consumer, resolver, gRPC client, delayed retry, and reconciler.
- [Control Plane Fast-Lane](apps/control-plane/src/grpc_helpers/client.py) — Sub-millisecond direct gRPC execution bypassing queue overhead.

---

## 1. Overview & Architectural Boundaries

AIP is an **enterprise-grade, self-hosted AI inference middleware platform** that provides standardized AI APIs for downstream enterprise applications. It is a pure inference gateway layer — it contains **no prompt templates, no RAG orchestration, and no training pipelines**.

### 1.1 What AIP Does (In-Scope)
- Ingests inference requests from downstream applications via a unified `/v1` API gateway.
- Authenticates clients via Bearer API keys (`aip_live_*` / `aip_test_*`) with **Argon2id** hashing and Master Pepper.
- Dynamically resolves logical model aliases to physical local runtime targets using Redis cache and MongoDB Atlas registry.
- Enforces multi-tenant rate limits (RPM, TPM), binary media upload quotas, and active background job concurrency via atomic Redis Lua scripts.
- **Dual Arterial Execution**:
  - **Fast-Lane**: Forwards synchronous requests directly to private data-plane services via multiplexed binary gRPC (`:50051`–`:50055`) or HTTP for zero-queue sub-millisecond latency.
  - **Batch Queue**: Dispatches heavy asynchronous jobs to RabbitMQ **Quorum Queues** with physical priority tiers for reliable background execution.
- Streams Server-Sent Events (SSE) token chunks back to clients without buffering.
- Records usage asynchronously to MongoDB without blocking inference responses.
- Executes async tasks via the modular `dispatcher-worker` using dedicated gRPC Protobuf stubs or delegating to specialized GPU workers.
- Protects GPU compute and VRAM via the **Lifecycle Triad (`GetHealth`, `ExecuteTask`, `CancelTask`)** with real coroutine cancellation on the GPU.

### 1.2 What AIP Does NOT Do (Explicit Out-of-Scope Boundaries)
- **No Prompt Management:** Does not store, inject, or optimize prompt templates — owned entirely by downstream apps.
- **No RAG Pipelines:** Does not perform document chunking, vector ingestion, or retrieval logic — downstream apps retrieve context and send it in the request payload.
- **No Business Logic:** Pure stateless inference proxy; does not orchestrate business transactions.
- **No Model Training:** No fine-tuning, training, LoRA merges, or dataset curation.
- **No End-User Consumer UI:** Serves raw APIs; the web portal is strictly for developer testing and admin governance.

### 1.3 Implementation Status & Deployment Readiness Matrix

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

## 2. Monorepo Organization & Component Mapping (`apps/` Layout)

All deployable applications are consolidated under `apps/`, accompanied by shared decoupled libraries in `packages/`:

```text
ai_platform/
├── apps/                               # Deployable Applications
│   ├── control-plane/                  # Tier 1: API Gateway (FastAPI :8000), Auth, Quotas, Model Aliases, Fast-Lane
│   ├── frontend/                       # Developer & Staff Web UI Portal (Vite + Vanilla JS :5173)
│   ├── data-plane/                     # Tier 2: Dedicated AI Serving Nodes (Dual HTTP & Dedicated gRPC)
│   │   ├── vllm-engine/                # LLM & Embedding Server (HTTP :8001 / gRPC :50051)
│   │   ├── stt-server/                 # Faster-Whisper Speech-to-Text (HTTP :8002 / gRPC :50052)
│   │   ├── translation-server/         # MarianMT/CTranslate2 En <-> Vi (HTTP :8003 / gRPC :50053)
│   │   ├── ocr-server/                 # EasyOCR / PaddleOCR-VL Document Server (HTTP :8004 / gRPC :50054)
│   │   ├── tts-adapter/                # viXTTS Neural Speech Synthesis (HTTP :8005 / gRPC :50055)
│   │   └── runtime-probe/              # Hardware telemetry probe & NVML health checker
│   ├── dispatcher-worker/              # Tier 3: Modular DCP Task Dispatcher, Resolver, gRPC Client & Reconciler
│   │   └── src/                        # consumer/, resolver/, client/, retry/, publisher/, reconciler/
│   ├── callback-worker/                # Tier 3: HMAC-SHA256 Signed Webhook Notification Delivery
│   ├── image-worker/                   # Tier 3: FLUX.1 & SDXL High-Res Image Generation Worker
│   ├── video-worker/                   # Tier 3: Wan2.2 & CogVideoX Text-to-Video Generation Worker
│   └── lipsync-worker/                 # Tier 3: LivePortrait Audio-Driven Lip Synchronization Worker
│
├── packages/                           # Shared Decoupled Libraries
│   ├── common/                         # Core Kernel (shared across all apps and workers)
│   │   ├── common/messaging/           # Monorepo Messaging Kernel: Topology, Quorum Queues, Thin Envelope, Publisher
│   │   ├── common/database/            # MongoDB Manager (auto-reconnecting across event loops) & Redis
│   │   ├── common/security/            # Argon2id hasher & Runtime Auth Middleware
│   │   └── common/models/              # Static & Dynamic Model Catalogs
│   ├── contracts/                      # Enterprise Protobuf & Data Transfer Contracts
│   │   ├── contracts/proto/            # Dedicated Proto definitions: common, llm, stt, translation, ocr, tts
│   │   └── contracts/generated/        # Pre-compiled Python gRPC stubs and message types
│   └── sdk/                            # Official Python Client SDK (aip-sdk)
│
├── deploy/                             # Deployment Manifests (Docker Compose, Helm, K8s)
└── tests/                              # Automated Pytest CI/CD test suite (124 tests, 100% pass)
```

---

## 3. Dual Arterial Execution Architecture

AIP incorporates an enterprise-grade **Dual Arterial Execution Model** bridging synchronous low-latency inference with resilient asynchronous batch processing:

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

---

## 4. Communication Architecture: RabbitMQ & Dedicated gRPC

### 4.1 RabbitMQ (AMQP 0-9-1) — Resilient Messaging & Topology

RabbitMQ serves as the asynchronous task coordination fabric across AIP:
- **Quorum Queues (`x-queue-type: quorum`)**: Built on the Raft consensus algorithm, guaranteeing zero message loss across broker restarts or network partitions. Configured with `x-delivery-limit: 4` and `x-max-length: 100000`.
- **Thin Task Envelopes**: Heavy payloads (raw audio chunks, PDF documents, high-resolution images) are persisted to MongoDB Atlas (`job_record.payload`). Only lightweight metadata envelopes (`task_id`, `job_id`, `domain`, `priority`) traverse AMQP, preventing message broker memory bloat.
- **Physical Priority Queues**: Replaced native priority queues with separate physical queues per priority level (`.high`, `.normal`, `.batch`) per domain (e.g. `q.aip.tasks.translation.high`, `q.aip.tasks.translation.normal`, `q.aip.tasks.translation.batch`). This eliminates Head-of-Line blocking where massive batch tasks would starve real-time requests.
- **Fair Dispatching**: Dispatcher workers enforce `prefetch_count = 1`, ensuring tasks are distributed evenly across worker instances based on actual capacity.
- **Broker-Level Delayed Retry (`x-delayed-message`)**: Built using `rabbitmq_delayed_message_exchange-3.13.0`. Retries are scheduled directly in the broker exchange with exponential delay (30s, 60s, 120s, 240s) without blocking the worker thread or event loop with `asyncio.sleep()`.
- **Dead-Letter Queue Governance**: The DLQ (`q.aip.tasks.dlq`) is a Quorum Queue configured with `x-message-ttl: 1209600000` (14 days) and `x-max-length-bytes: 10737418240` (10 GB).

### 4.2 Dedicated gRPC Data-Plane Topology (ISP Compliant)

Following the **Interface Segregation Principle (ISP)**, AIP replaces monolithic generic contracts with 5 purpose-built Protobuf service definitions located in `packages/contracts/contracts/proto/`:

| Service | gRPC Port | HTTP Port | Service Contract | Operations Supported | Modality & Engine |
| :--- | :---: | :---: | :--- | :--- | :--- |
| `vllm-engine` | `50051` | `8001` | `LlmService` | `ChatCompletion`, `StreamChatCompletion`, `GetHealth`, `Cancel` | Text Generation & Embeddings (vLLM / Qwen2.5) |
| `stt-server` | `50052` | `8002` | `SttService` | `TranscribeAudio`, `GetHealth`, `Cancel` | Speech-to-Text (Faster-Whisper) |
| `translation-server` | `50053` | `8003` | `TranslationService` | `Translate`, `GetHealth`, `Cancel` | Bidirectional NMT (CTranslate2 / MarianMT) |
| `ocr-server` | `50054` | `8004` | `OcrService` | `ExtractDocument`, `GetHealth`, `Cancel` | Document OCR & CCCD (EasyOCR / PaddleOCR-VL) |
| `tts-adapter` | `50055` | `8005` | `TtsService` | `SynthesizeSpeech`, `GetHealth`, `Cancel` | Neural Text-to-Speech (viXTTS) |

#### Lifecycle Triad on All Services:
1. **`ExecuteTask`** (e.g. `ChatCompletion`, `Translate`): Strongly-typed input and output messages with binary serialization.
2. **`CancelTask`**: Real `Cancel` RPC. In each data-plane service, `Cancel` looks up the running `asyncio.Task` by `task_id` and calls `.cancel()`. This aborts GPU compute immediately, avoiding wasted token generation or GPU inference time.
3. **`GetHealth`**: Real-time typed status (`SERVING`, `NOT_SERVING`) and active task count reported for health probes and load balancing.

#### Error Taxonomy & Resilience:
- **`InferenceTransientError`**: Caused by network timeouts, `UNAVAILABLE`, or `DEADLINE_EXCEEDED`. Re-routed to the `aip.jobs.delayed` exchange for retry.
- **`InferenceTerminalError`**: Caused by invalid arguments, malformed payloads, or `UNIMPLEMENTED` methods. Immediately acknowledged and dispatched to `q.aip.tasks.dlq` without wasteful retries.

---

## 5. Control Plane Fast-Lane Execution

In addition to asynchronous queue-based batch execution, the Control Plane API Gateway features a **gRPC Fast-Lane**:
- Inbound HTTP REST requests (e.g., `/v1/nlp/translation`) are intercepted.
- If the target service supports gRPC, the request is packaged into a Protobuf message and dispatched directly over a pooled, persistent HTTP/2 gRPC channel.
- Results are received with sub-millisecond overhead and returned directly to the client, with telemetry headers indicating `protocol: grpc_fast_lane`.
- If the gRPC call fails or is unavailable, the gateway falls back transparently to internal HTTP without impacting the end user.

---

## 6. Dispatcher Worker Modular Architecture (DCP Pattern)

The `apps/dispatcher-worker` is structured into 6 decoupled modules:

```text
apps/dispatcher-worker/src/
├── consumer/               # 1. RabbitMQ Queue Listener
│   └── task_consumer.py    # Quorum Queue consumer with prefetch=1 & fair scheduling
├── resolver/               # 2. Dynamic Task Resolver
│   └── task_resolver.py    # Maps domain & alias to dedicated gRPC endpoint (:50051-:50055)
├── client/                 # 3. Dedicated gRPC Client
│   └── inference_client.py # Calls dedicated stubs with strict typed error handling
├── retry/                  # 4. Broker-Level Delayed Retry
│   └── delayed_retry.py    # Publishes to x-delayed-message exchange with jittered exponential backoff
├── publisher/              # 5. Outbound Event Bus
│   └── callback_publisher.py # Emits JobCreated, Progress, Completed, Failed events to aip.events
├── reconciler/             # 6. Self-Healing Reconciler
│   └── stale_reconciler.py # Scans MongoDB for jobs stuck in 'running' > 15m; releases Redis slots
└── main.py                 # Single unified async entrypoint with SIGTERM/SIGINT graceful shutdown
```

---

## 7. Model Catalog: Core Production Models

In accordance with local hardware constraints, the platform standardizes on verified core local models defined in [catalog.py](packages/common/common/models/catalog.py):

| Model Alias | Physical Model | Runtime | Min VRAM | Category | Internal gRPC Target | Internal HTTP URL |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| `chat-general-standard` | `Qwen2.5-1.5B-Instruct` | vLLM | 2 GB | `llm` | `vllm-engine:50051` | `http://vllm-engine:8001/v1` |
| `embed-standard` | `Qwen2.5-1.5B-Instruct` | Transformers | 0 GB (CPU/GPU) | `embedding` | `vllm-engine:50051` | `http://vllm-engine:8001/v1` |
| `translate-vi-standard` | `opus-mt-vi-en` | CTranslate2 | 1 GB | `translation` | `translation-server:50053` | `http://translation-server:8003/v1` |
| `stt-vn-standard` | `faster-whisper-small` | Faster-Whisper | 0 GB (CPU/GPU) | `stt` | `stt-server:50052` | `http://stt-server:8002/v1` |
| `tts-vi-standard` | `viXTTS / Neural` | tts-adapter | 0 GB (CPU/GPU) | `tts` | `tts-adapter:50055` | `http://tts-adapter:8005/v1` |
| `idp-standard` | `EasyOCR / PaddleOCR` | ocr-server | 2 GB | `ocr` | `ocr-server:50054` | `http://ocr-server:8004/v1` |

---

## 8. Testing & Quality Assurance Verification

The codebase is continuously verified through an automated test suite containing **124 automated tests** with **100% pass rate**:

```bash
# Run the full test suite
pytest tests/ -v

# Run gRPC data-plane integration tests
pytest tests/test_grpc_client.py tests/test_grpc_inference_client_errors.py

# Verify dedicated gRPC server lifecycle
python tests/test_vllm_grpc.py
python tests/test_stt_grpc.py
python tests/test_grpc_translation_server.py
python tests/test_tts_grpc.py
python tests/test_ocr_grpc.py
```

---

*AIP Platform Architecture — Designed for Resilient, High-Throughput Enterprise AI Inference.*
