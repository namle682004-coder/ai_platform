.PHONY: setup dev-env dev-env-down dev-gateway test export context lint clean

UV ?= $(shell which uv 2>/dev/null || echo /home/namle/.local/bin/uv)

setup:
	@echo "Setting up environment and locking dependencies using uv..."
	$(UV) venv || true
	$(UV) pip install -e packages/common -e packages/sdk-py -e services/gateway -e services/translation-server -e services/stt-server -e services/moderation-server pytest httpx ruff python-multipart

dev-env:
	@echo "Starting local infrastructure (MongoDB, Redis, RabbitMQ, MinIO)..."
	docker compose -f deploy/docker-compose/docker-compose.yml up -d mongodb redis rabbitmq minio

dev-env-down:
	@echo "Stopping local infrastructure..."
	docker compose -f deploy/docker-compose/docker-compose.yml down

dev-gateway:
	@echo "Starting Gateway Microservice with uv..."
	cd services/gateway && PYTHONPATH=../../services:../../packages $(UV) run uvicorn main:app --reload --host 0.0.0.0 --port 8000

test:
	@echo "Running Pytest with uv..."
	PYTHONPATH=services:packages:packages/sdk-py $(UV) run pytest

export:
	@echo "Exporting OpenAPI JSON, Postman Collection, and Redoc HTML..."
	PYTHONPATH=services:packages:packages/sdk-py $(UV) run python scripts/export_api_assets.py

context:
	@echo "Exporting Repomix Codebase Context for AI Agents..."
	PYTHONPATH=services:packages:packages/sdk-py $(UV) run python scripts/export_repo_context.py

lint:
	@echo "Running ruff check with uv..."
	$(UV) run ruff check .

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	rm -rf .venv
