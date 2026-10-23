FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY packages/common /app/packages/common
COPY packages/contracts /app/packages/contracts
COPY platform/workers/media/image-worker /app/platform/workers/media/image-worker

RUN pip install --no-cache-dir     -e /app/packages/common     -e /app/packages/contracts     -e /app/platform/workers/media/image-worker

WORKDIR /app/platform/workers/media/image-worker
ENV PYTHONPATH=/app/platform/workers/media/image-worker:/app/packages/common:/app/packages/contracts

CMD ["python", "worker.py"]
