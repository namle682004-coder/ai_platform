FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY packages/common /app/packages/common
COPY packages/contracts /app/packages/contracts
COPY workers/gpu-workloads/image-worker /app/workers/gpu-workloads/image-worker

RUN pip install --no-cache-dir     -e /app/packages/common     -e /app/packages/contracts     -e /app/workers/gpu-workloads/image-worker

WORKDIR /app/workers/gpu-workloads/image-worker
ENV PYTHONPATH=/app/workers/gpu-workloads/image-worker:/app/packages/common:/app/packages/contracts

CMD ["python", "worker.py"]
