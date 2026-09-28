# AIP OpenAI-Compatible Model Serving Engine (Data Plane - Tầng 2)

High-throughput, memory-efficient LLM & Embedding serving engine built with FastAPI and Transformers, compliant with **SRS Section 2.2, 5.2, & 6.1**.

## Overview

`vllm-engine` provides the official inference execution layer for all text, reasoning, classification, summarization, and embedding models hosted on the platform:

- `chat-general-standard` (Qwen3-8B / Qwen2.5-Instruct)
- `chat-general-high-quality` (Qwen3-14B)
- `summarize-high-quality` (Qwen3-14B)
- `classify-dynamic-standard` (Qwen3-8B)
- `ner-re-standard` (Qwen3-8B)
- `embed-standard` (Qwen3-Embedding-8B)

## Port & Protocol

- **Default Port**: `8001`
- **Protocol**: OpenAI-compatible HTTP REST & Server-Sent Events (SSE) streaming
  - `POST /v1/chat/completions`
  - `POST /v1/completions`
  - `POST /v1/embeddings`
  - `GET /v1/models`
  - `GET /health`

## Local Development vs. Production Cluster

- **Production (Multi-GPU / K8s)**: Runs the OpenAI-compatible FastAPI service and loads the configured Transformers model into the available accelerator.
- **Local Dev (RTX 3050 4GB VRAM / CPU)**: Runs `uvicorn app:app --port 8001` with the configured compact model and the same API contract.
