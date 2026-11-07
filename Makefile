.PHONY: setup dev-env dev-env-down dev-env-full \
        docker-up up docker-down down docker-pull pull docker-build build docker-ps ps docker-clean \
        docker-ai docker-vllm docker-translation docker-monitoring \
        docker-logs docker-logs-ui docker-logs-dispatcher docker-logs-callback \
        dev-gateway dev-rag dev-rag-worker deploy-server dev-vllm dev-translation dev-stt dev-ocr dev-moderation dev-tts \
		prepare-translation-model \
        dev-dispatcher dev-callback worker-image \
        dev-ui ui frontend-dev frontend-build \
        rag-eval-import rag-eval-checklist rag-eval-calibrate rag-eval rag-gate rag-eval-test rag-connectors-e2e \
        test lint fmt export clean help

COMPOSE_FILE ?= deploy/docker-compose/docker-compose.yml
DOCKER_COMPOSE ?= docker compose -f $(COMPOSE_FILE)
PYTHON ?= ./venv/bin/python
UVICORN ?= ./venv/bin/uvicorn
PYTEST ?= ./venv/bin/pytest
RUFF ?= ./venv/bin/ruff
UV ?= $(shell which uv 2>/dev/null || echo /home/namle/.local/bin/uv)

# ─── Setup ────────────────────────────────────────────────────────
setup:
	@echo "▶ Setting up virtualenv and installing all monorepo packages..."
	$(UV) venv || true
	$(UV) pip install -e packages/common \
	                  -e packages/contracts \
	                  -e packages/sdk \
	                  -e platform/gateway \
	                  -e platform/workers/dispatcher \
	                  -e platform/workers/callback \
	                  -e platform/workers/media/image-worker \
	                  -e platform/runtimes/vllm-engine \
	                  -e platform/runtimes/translation-server \
	                  -e platform/runtimes/stt-server \
	                  -e platform/runtimes/moderation-server \
	                  pytest httpx ruff python-multipart

# ─── Infrastructure (Dev) ─────────────────────────────────────────
dev-env:
	@echo "▶ Starting core infrastructure (MongoDB, Redis, RabbitMQ, MinIO)..."
	$(DOCKER_COMPOSE) up -d mongodb redis rabbitmq minio

dev-env-full:
	@echo "▶ Starting full infrastructure stack (including Prometheus, Grafana, Alertmanager)..."
	$(DOCKER_COMPOSE) --profile monitoring up -d
dev-env-down:
	@echo "▶ Stopping all infrastructure containers..."
	$(DOCKER_COMPOSE) down

# ─── Docker Core Stack (BẮT BUỘC & NÊN CHẠY - 8 SERVICES CỐT LÕI) ──
# Gồm: MongoDB, Redis, RabbitMQ, MinIO, Control-Plane, Frontend, Dispatcher, Callback
docker-up:
	@echo "▶ Starting 8 Core Essential Services (Mongo, Redis, RabbitMQ, MinIO, Gateway, Frontend, Workers)..."
	$(DOCKER_COMPOSE) up -d

up: docker-up

docker-pull:
	@echo "▶ Pulling official images for Core Infrastructure (MongoDB, Redis, RabbitMQ, MinIO)..."
	$(DOCKER_COMPOSE) pull mongodb redis rabbitmq minio

pull: docker-pull

docker-build:
	@echo "▶ Building lightweight Core Application services (Control-Plane, Frontend, Workers)..."
	$(DOCKER_COMPOSE) build control-plane frontend dispatcher-worker callback-worker

build: docker-build

docker-ps:
	@echo "▶ Status of running Core AIP containers:"
	$(DOCKER_COMPOSE) ps

ps: docker-ps

docker-down:
	@echo "▶ Stopping all AIP Docker containers..."
	$(DOCKER_COMPOSE) down

down: docker-down

docker-clean:
	@echo "▶ Cleaning dead containers, old volumes, and build cache..."
	docker container prune -f
	docker builder prune -f

# ─── On-Demand Docker AI & Monitoring (CHỈ BẬT KHI CẦN, KHÔNG TỰ ĐỘNG BẬT) ───
docker-translation:
	@echo "▶ Starting Translation Server in Docker on-demand..."
	$(DOCKER_COMPOSE) --profile ai-specialized up -d translation-server

docker-vllm:
	@echo "▶ Starting vLLM Serving Engine in Docker on-demand..."
	$(DOCKER_COMPOSE) --profile ai-llm up -d vllm-engine

docker-ai:
	@echo "▶ Starting all Specialized AI microservices in Docker..."
	$(DOCKER_COMPOSE) --profile ai-specialized up -d

docker-monitoring:
	@echo "▶ Starting Monitoring stack (Prometheus, Alertmanager, Grafana)..."
	$(DOCKER_COMPOSE) --profile monitoring up -d

docker-logs:
	@echo "▶ Streaming Control-Plane Docker logs (Ctrl+C to exit)..."
	docker logs -f aip-control-plane

docker-logs-ui:
	@echo "▶ Streaming Frontend UI Docker logs (Ctrl+C to exit)..."
	docker logs -f aip-frontend

docker-logs-dispatcher:
	@echo "▶ Streaming Dispatcher-Worker Docker logs (Ctrl+C to exit)..."
	docker logs -f aip-dispatcher-worker

docker-logs-callback:
	@echo "▶ Streaming Callback-Worker Docker logs (Ctrl+C to exit)..."
	docker logs -f aip-callback-worker

docker-logs-translation:
	@echo "▶ Streaming Translation-Server Docker logs (Ctrl+C to exit)..."
	docker logs -f aip-translation-server

docker-logs-vllm:
	@echo "▶ Streaming vLLM-Engine Docker logs (Ctrl+C to exit)..."
	docker logs -f aip-vllm-engine

docker-logs-stt:
	@echo "▶ Streaming STT-Server Docker logs (Ctrl+C to exit)..."
	docker logs -f aip-stt-server

# ─── Tầng 1: Control Plane (Native Dev) ───────────────────────────
dev-gateway:
	@echo "▶ Starting Control-Plane API on http://localhost:8000 ..."
	cd platform/gateway && \
	PYTHONPATH=../../packages/common:../../packages/contracts:../../packages/sdk:src:. \
	../../$(UVICORN) src.main:app --reload --host 0.0.0.0 --port 8000

# Enterprise RAG API; the gateway forwards /v1/rag and /v1/knowledge here (RAG_SERVICE_URL).
dev-rag:
	@echo "▶ Starting Enterprise RAG API on http://localhost:8010 ..."
	PYTHONPATH=.:packages/common:packages/contracts \
	RAG_TRUST_IDENTITY_HEADERS=$${RAG_TRUST_IDENTITY_HEADERS:-true} \
	RAG_ENFORCE_SHARED_KB_WRITE_ACL=$${RAG_ENFORCE_SHARED_KB_WRITE_ACL:-false} \
	$(PYTHON) -m solutions.rag.main --mode api --host 0.0.0.0 --port 8010

dev-rag-worker:
	@echo "▶ Starting RAG ingestion worker ..."
	PYTHONPATH=.:packages/common:packages/contracts $(PYTHON) -m solutions.rag.main --mode worker

# Ship the committed revision (default HEAD) to the internal server msp: gateway + RAG API + worker
deploy-server:
	@bash scripts/deploy_server.sh $(REF)

# ─── Quản lý toàn bộ AI Data Plane (Start / Stop / Status 1 Click) ───
start-all:
	@bash scripts/manage_services.sh start

stop-all:
	@bash scripts/manage_services.sh stop

status-all:
	@bash scripts/manage_services.sh status

restart-all:
	@bash scripts/manage_services.sh restart

# ─── Tầng 2: Data Plane (Native Dev - Zero Docker Overhead, Dùng chung GPU) ─
prepare-translation-model:
	@echo "▶ Converting the Hugging Face translation model to CTranslate2 format..."
	$(PYTHON) scripts/prepare_translation_model.py --output models/translation/opus-mt-vi-en

dev-vllm:
	@echo "▶ Starting vLLM Serving Engine on http://localhost:8001 ..."
	cd platform/runtimes/vllm-engine && \
	PYTHONPATH=../../../packages/common:../../../packages/contracts:. \
	../../../$(UVICORN) app:app --reload --host 0.0.0.0 --port 8001

dev-translation:
	@echo "▶ Starting Translation Microservice (Helsinki-NLP) on http://localhost:8003 ..."
	cd platform/runtimes/translation-server && \
	PYTHONPATH=../../../packages/common:../../../packages/contracts:. \
	../../../$(UVICORN) app:app --reload --host 0.0.0.0 --port 8003

dev-stt:
	@echo "▶ Starting Speech-to-Text Microservice (PhoWhisper) on http://localhost:8002 ..."
	cd platform/runtimes/stt-server && \
	PYTHONPATH=../../../packages/common:../../../packages/contracts:. \
	../../../$(UVICORN) app:app --reload --host 0.0.0.0 --port 8002

dev-ocr:
	@echo "▶ Starting OCR Microservice (PaddleOCR) on http://localhost:8004 ..."
	cd platform/runtimes/ocr-server && \
	PYTHONPATH=../../../packages/common:../../../packages/contracts:. \
	../../../$(UVICORN) app:app --reload --host 0.0.0.0 --port 8004

dev-moderation:
	@echo "▶ Starting Moderation Microservice on http://localhost:8006 ..."
	cd platform/runtimes/moderation-server && \
	PYTHONPATH=../../../packages/common:../../../packages/contracts:. \
	../../../$(UVICORN) app:app --reload --host 0.0.0.0 --port 8006

dev-tts:
	@echo "▶ Starting TTS Adapter Microservice on http://localhost:8007 ..."
	cd platform/runtimes/tts-adapter && \
	PYTHONPATH=../../../packages/common:../../../packages/contracts:. \
	../../../$(UVICORN) app:app --reload --host 0.0.0.0 --port 8007

# ─── Tầng 3: Workers (Orchestration & GPU-Workloads) ──────────────
dev-dispatcher:
	@echo "▶ Starting AIP Dedicated Dispatcher Worker (Domain Tasks & Stale Reconciler)..."
	PYTHONPATH=.:packages/common:packages/contracts:platform/gateway:platform/gateway/src:platform/workers/dispatcher:platform/workers/dispatcher/src \
	$(PYTHON) platform/workers/dispatcher/src/main.py

dev-callback:
	@echo "▶ Starting AIP Dedicated Callback Worker (HMAC Webhooks)..."
	PYTHONPATH=.:packages/common:packages/contracts:platform/gateway:platform/gateway/src:platform/workers/callback \
	$(PYTHON) platform/workers/callback/worker/main.py

worker-image:
	@echo "▶ Starting Image Generation Worker (FLUX.1/SDXL) — queue: q.aip.tasks.image ..."
	PYTHONPATH=.:packages/common:packages/contracts:platform/gateway:platform/gateway/src:platform/workers/media/image-worker \
	$(PYTHON) platform/workers/media/image-worker/worker.py

# ─── Tầng 6: Frontend / UI ────────────────────────────────────────
frontend-dev:
	@echo "▶ Starting Staff Portal UI (Vite Dev Server) on http://localhost:5173 ..."
	@echo "   Staff Console  → http://localhost:5173/staff/dashboard"
	@echo "   Auth Page      → http://localhost:5173/auth/login.html"
	@echo "   Status Page    → http://localhost:5173/status.html"
	cd frontend && export PATH="/home/namle/.local/bin:$$PATH" && npm run dev

ui: frontend-dev
dev-ui: frontend-dev

frontend-build:
	@echo "▶ Building Frontend for Production (dist/)..."
	cd frontend && export PATH="/home/namle/.local/bin:$$PATH" && npm run build

# ─── Tests & Lint ─────────────────────────────────────────────────
test:
	@echo "▶ Running full Pytest test suite..."
	PYTHONPATH=.:packages/common:packages/contracts:packages/sdk:platform/gateway:platform/gateway/src:platform/workers/dispatcher:platform/workers/callback:platform/workers/media/image-worker:platform/runtimes/translation-server:platform/runtimes/vllm-engine \
	$(PYTEST) -v

lint:
	@echo "▶ Running Ruff linter on all code..."
	$(RUFF) check platform/ solutions/ packages/ tests/

fmt:
	@echo "▶ Auto-fixing Ruff lint issues..."
	$(RUFF) check --fix platform/ solutions/ packages/ tests/

# ─── RAG evaluation & go-live gate (benchmarks/rag) ───────────────
# make rag-eval RAG_EVAL_TENANT=<project> RAG_EVAL_HEADERS='--header "X-AIP-Runtime-Token: …"' [RAG_EVAL_BASELINE=benchmarks/rag/runs/<prev>]
RAG_EVAL_XLSX ?= Bo_test_Chatbot_KhungAI_v2_KetQua.xlsx
RAG_EVAL_DATASET_CONFIG ?= benchmarks/rag/configs/datasets/khung_ai.yaml
RAG_EVAL_DATASET ?= benchmarks/rag/datasets/acceptance/khung_ai_v2.jsonl
RAG_EVAL_CALIBRATION ?= benchmarks/rag/runs/calibration_khung_ai_checklist.json
RAG_EVAL_GRADES_FROM ?= $(basename $(RAG_EVAL_DATASET)).calibration.jsonl
RAG_EVAL_GATE ?= benchmarks/rag/configs/gate.yaml
RAG_EVAL_API ?= http://localhost:8010
RAG_EVAL_TENANT ?=
RAG_EVAL_HEADERS ?=
RAG_EVAL_BASELINE ?=
RAG_EVAL_RUN ?=
RAG_BENCH = cd benchmarks/rag/src && PYTHONPATH=../../..:../../../packages/common $(abspath $(PYTHON)) -m rag_benchmark.cli

rag-eval-import:
	@echo "▶ Workbook -> golden JSONL + judge calibration examples..."
	$(RAG_BENCH) import-xlsx $(abspath $(RAG_EVAL_XLSX)) --config $(abspath $(RAG_EVAL_DATASET_CONFIG)) --out $(abspath $(RAG_EVAL_DATASET))

rag-eval-checklist:
	@echo "▶ Drafting core points per case (review the .checklist.xlsx, then import it with --import-xlsx)..."
	$(RAG_BENCH) checklist --dataset $(abspath $(RAG_EVAL_DATASET))

rag-eval-calibrate:
	@echo "▶ Measuring grader agreement with human grades..."
	$(RAG_BENCH) calibrate --dataset $(abspath $(RAG_EVAL_DATASET)) \
		--examples $(abspath $(basename $(RAG_EVAL_DATASET)).calibration.jsonl) --out $(abspath $(RAG_EVAL_CALIBRATION))

rag-eval:
	@test -n "$(RAG_EVAL_TENANT)" || (echo "RAG_EVAL_TENANT is required" && exit 2)
	@echo "▶ Running acceptance suite + go-live gate (exit 1 = NO-GO)..."
	$(RAG_BENCH) suite --dataset $(abspath $(RAG_EVAL_DATASET)) --api $(RAG_EVAL_API) --tenant $(RAG_EVAL_TENANT) \
		$(RAG_EVAL_HEADERS) --gate $(abspath $(RAG_EVAL_GATE)) --calibration $(abspath $(RAG_EVAL_CALIBRATION)) \
		--out-dir $(abspath benchmarks/rag/runs) $(if $(RAG_EVAL_BASELINE),--baseline $(abspath $(RAG_EVAL_BASELINE))) \
		$(foreach g,$(RAG_EVAL_GRADES_FROM),--grades-from $(abspath $(g)))

rag-gate:
	@test -n "$(RAG_EVAL_RUN)" || (echo "RAG_EVAL_RUN=<run dir> is required" && exit 2)
	$(RAG_BENCH) gate --run $(abspath $(RAG_EVAL_RUN)) --gate $(abspath $(RAG_EVAL_GATE)) \
		--calibration $(abspath $(RAG_EVAL_CALIBRATION)) $(if $(RAG_EVAL_BASELINE),--baseline $(abspath $(RAG_EVAL_BASELINE)))

# Step-1 data-quality gate: AIP parser+chunker vs independent extraction (no LLM). Exit 1 = do not start step 2.
# make rag-data-gate RAG_DATA_DOCS=/path/to/docs [RAG_DATA_CHECKS=benchmarks/rag/datasets/acceptance/<set>.index_checks.json]
RAG_DATA_DOCS ?=
RAG_DATA_CHECKS ?=
rag-data-gate:
	@test -n "$(RAG_DATA_DOCS)" || (echo "RAG_DATA_DOCS=<folder of source documents> is required" && exit 2)
	cd benchmarks/rag/src && PYTHONPATH=../../..:../../../packages/common:../../../packages/contracts \
		$(abspath $(PYTHON)) -m rag_benchmark.data_audit --docs "$(RAG_DATA_DOCS)" \
		$(if $(RAG_DATA_CHECKS),--checks $(abspath $(RAG_DATA_CHECKS))) --gate $(abspath benchmarks/rag/configs/data_gate.yaml)

# Connector rehearsal: isolated stack + fake customer source (JSON API + intranet), real API/worker/Mongo/Qdrant.
# make rag-connectors-e2e [AIP_RAG_IMAGE=aip-rag:ocr-test]   (exit 1 = a check failed; the stack is removed either way)
RAG_E2E_COMPOSE = -f deploy/docker-compose/docker-compose.loadtest.yml \
	-f deploy/docker-compose/docker-compose.connectors-e2e.yml -p aip-loadtest
rag-connectors-e2e:
	docker compose $(RAG_E2E_COMPOSE) up -d --wait
	docker exec -i aip-loadtest-rag-api python - < scripts/e2e_connectors.py; rc=$$?; \
		docker compose $(RAG_E2E_COMPOSE) down -v; exit $$rc

rag-eval-test:
	@echo "▶ Offline tests of tracing, verification and the evaluation harness..."
	$(PYTEST) -q tests/test_rag_tracing.py tests/test_rag_acceptance_suite.py tests/test_numeric_and_units.py \
		tests/test_answer_verification.py tests/test_rag_answer_pipeline.py

# ─── Utilities ────────────────────────────────────────────────────
export:
	@echo "▶ Exporting OpenAPI JSON, Postman Collection, and Redoc HTML..."
	PYTHONPATH=.:packages/common:packages/contracts:packages/sdk:platform/gateway:platform/gateway/src \
	$(PYTHON) scripts/export_api_assets.py


clean:
	@echo "▶ Cleaning build artifacts and caches..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .venv

# ─── Help ─────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "╔═════════════════════════════════════════════════════════════════════╗"
	@echo "║           AIP Platform — Clean Architecture Stack            ║"
	@echo "╠═════════════════════════════════════════════════════════════════════╣"
	@echo "║ DOCKER CORE (8 SERVICES BẮT BUỘC & NÊN CHẠY)                         ║"
	@echo "║  make up (docker-up)     Start 8 Core Services (DB, Queue, Gateway)  ║"
	@echo "║  make pull (docker-pull) Pull images for Core Infra (Mongo, Redis..) ║"
	@echo "║  make build              Build lightweight Gateway, Frontend, Worker ║"
	@echo "║  make ps (docker-ps)     View status of running core containers      ║"
	@echo "║  make down (docker-down) Stop all containers                         ║"
	@echo "║  make docker-clean       Prune dead containers & build cache         ║"
	@echo "╠═════════════════════════════════════════════════════════════════════╣"
	@echo "║ ON-DEMAND DOCKER (CHỈ BẬT KHI CẦN)                                   ║"
	@echo "║  make docker-vllm        Start vLLM in Docker container              ║"
	@echo "║  make docker-translation Start Translation in Docker                 ║"
	@echo "║  make docker-ai          Start all AI microservices in Docker        ║"
	@echo "║  make docker-monitoring  Start Prometheus, Grafana, Alertmanager     ║"
	@echo "╠═════════════════════════════════════════════════════════════════════╣"
	@echo "║ NATIVE DEV (ZERO DOCKER OVERHEAD, DÙNG CHUNG GPU & HF CACHE)         ║"
	@echo "║  make start-all          Start all AI microservices (1-Click)        ║"
	@echo "║  make stop-all           Stop all AI microservices & free GPU VRAM   ║"
	@echo "║  make status-all         Check status of all Platform ports          ║"
	@echo "║  make dev-gateway        Control-Plane API Gateway → :8000           ║"
	@echo "║  make dev-vllm           vLLM Foundation Engine    → :8001           ║"
	@echo "║  make dev-translation    Translation Microservice  → :8003           ║"
	@echo "║  make dev-stt            Speech-to-Text (Whisper)  → :8002           ║"
	@echo "║  make dev-ocr            OCR Microservice          → :8004           ║"
	@echo "║  make dev-moderation     Moderation Microservice   → :8006           ║"
	@echo "║  make dev-tts            TTS Microservice          → :8007           ║"
	@echo "║  make dev-dispatcher     Task Dispatcher Worker                      ║"
	@echo "║  make dev-callback       Webhook Callback Worker                     ║"
	@echo "║  make worker-image       Image Generation Worker (FLUX/SDXL)         ║"
	@echo "╠═════════════════════════════════════════════════════════════════════╣"
	@echo "║ FRONTEND & TESTING                                                  ║"
	@echo "║  make ui                 Staff & Admin Portal      → :5173           ║"
	@echo "║  make test               Run full Pytest test suite                  ║"
	@echo "║  make lint / make fmt    Run / auto-fix Ruff linter                  ║"
	@echo "╚═════════════════════════════════════════════════════════════════════╝"
	@echo ""
