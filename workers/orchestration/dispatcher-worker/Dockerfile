FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY packages/common /app/packages/common
COPY packages/contracts /app/packages/contracts
COPY control-plane /app/control-plane
COPY workers/orchestration/dispatcher-worker /app/workers/orchestration/dispatcher-worker

RUN pip install --no-cache-dir \
    -e /app/packages/common \
    -e /app/packages/contracts \
    -e /app/control-plane \
    -e /app/workers/orchestration/dispatcher-worker

WORKDIR /app/workers/orchestration/dispatcher-worker
ENV PYTHONPATH=/app/workers/orchestration/dispatcher-worker:/app/control-plane:/app/packages/common:/app/packages/contracts

CMD ["python", "dispatcher/main.py"]
