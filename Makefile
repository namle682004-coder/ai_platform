.PHONY: setup dev-env dev-env-down dev-env-full \
        docker-up up docker-down down docker-pull pull docker-build build docker-ps ps docker-clean \
        docker-ai docker-vllm docker-translation docker-monitoring \
        docker-logs docker-logs-ui docker-logs-dispatcher docker-logs-callback \
        dev-gateway dev-vllm dev-translation dev-stt dev-ocr dev-moderation dev-tts \
		prepare-translation-model \
        dev-dispatcher dev-callback worker-image \
        dev-ui ui frontend-dev frontend-build \
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
	                  -e control-plane \
	                  -e workers/orchestration/dispatcher-worker \
	                  -e workers/orchestration/callback-worker \
	                  -e workers/gpu-workloads/image-worker \
	                  -e data-plane/vllm-engine \
	                  -e data-plane/translation-server \
	                  -e data-plane/stt-server \
	                  -e data-plane/moderation-server \
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
	cd control-plane && \
	PYTHONPATH=../packages/common:../packages/contracts:../packages/sdk:src:. \
	../$(UVICORN) src.main:app --reload --host 0.0.0.0 --port 8000

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
	cd data-plane/vllm-engine && \
	PYTHONPATH=../../packages/common:../../packages/contracts:. \
	../../$(UVICORN) app:app --reload --host 0.0.0.0 --port 8001

dev-translation:
	@echo "▶ Starting Translation Microservice (Helsinki-NLP) on http://localhost:8003 ..."
	cd data-plane/translation-server && \
	PYTHONPATH=../../packages/common:../../packages/contracts:. \
	../../$(UVICORN) app:app --reload --host 0.0.0.0 --port 8003

dev-stt:
	@echo "▶ Starting Speech-to-Text Microservice (PhoWhisper) on http://localhost:8002 ..."
	cd data-plane/stt-server && \
	PYTHONPATH=../../packages/common:../../packages/contracts:. \
	../../$(UVICORN) app:app --reload --host 0.0.0.0 --port 8002

dev-ocr:
	@echo "▶ Starting OCR Microservice (PaddleOCR) on http://localhost:8004 ..."
	cd data-plane/ocr-server && \
	PYTHONPATH=../../packages/common:../../packages/contracts:. \
	../../$(UVICORN) app:app --reload --host 0.0.0.0 --port 8004

dev-moderation:
	@echo "▶ Starting Moderation Microservice on http://localhost:8006 ..."
	cd data-plane/moderation-server && \
	PYTHONPATH=../../packages/common:../../packages/contracts:. \
	../../$(UVICORN) app:app --reload --host 0.0.0.0 --port 8006

dev-tts:
	@echo "▶ Starting TTS Adapter Microservice on http://localhost:8007 ..."
	cd data-plane/tts-adapter && \
	PYTHONPATH=../../packages/common:../../packages/contracts:. \
	../../$(UVICORN) app:app --reload --host 0.0.0.0 --port 8007

# ─── Tầng 3: Workers (Orchestration & GPU-Workloads) ──────────────
dev-dispatcher:
	@echo "▶ Starting AIP Dedicated Dispatcher Worker (Domain Tasks & Stale Reconciler)..."
	PYTHONPATH=.:packages/common:packages/contracts:control-plane:control-plane/src:workers/orchestration/dispatcher-worker \
	$(PYTHON) workers/orchestration/dispatcher-worker/dispatcher/main.py

dev-callback:
	@echo "▶ Starting AIP Dedicated Callback Worker (HMAC Webhooks)..."
	PYTHONPATH=.:packages/common:packages/contracts:control-plane:control-plane/src:workers/orchestration/callback-worker \
	$(PYTHON) workers/orchestration/callback-worker/worker/main.py

worker-image:
	@echo "▶ Starting Image Generation Worker (FLUX.1/SDXL) — queue: q.aip.tasks.image ..."
	PYTHONPATH=.:packages/common:packages/contracts:control-plane:control-plane/src:workers/gpu-workloads/image-worker \
	$(PYTHON) workers/gpu-workloads/image-worker/worker.py

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
	PYTHONPATH=.:packages/common:packages/contracts:packages/sdk:control-plane:control-plane/src:workers/orchestration/dispatcher-worker:workers/orchestration/callback-worker:workers/gpu-workloads/image-worker:data-plane/translation-server:data-plane/vllm-engine \
	$(PYTEST) -v

lint:
	@echo "▶ Running Ruff linter on all code..."
	$(RUFF) check control-plane/ data-plane/ workers/ packages/ tests/

fmt:
	@echo "▶ Auto-fixing Ruff lint issues..."
	$(RUFF) check --fix control-plane/ data-plane/ workers/ packages/ tests/

# ─── Utilities ────────────────────────────────────────────────────
export:
	@echo "▶ Exporting OpenAPI JSON, Postman Collection, and Redoc HTML..."
	PYTHONPATH=.:packages/common:packages/contracts:packages/sdk:control-plane:control-plane/src \
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
	@echo "║           Everwin AI Platform — Clean Architecture Stack            ║"
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
