FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY packages/common /app/packages/common
COPY packages/contracts /app/packages/contracts
COPY apps/image-worker /app/apps/image-worker

RUN pip install --no-cache-dir     -e /app/packages/common     -e /app/packages/contracts     -e /app/apps/image-worker

WORKDIR /app/apps/image-worker
ENV PYTHONPATH=/app/apps/image-worker:/app/packages/common:/app/packages/contracts

CMD ["python", "worker.py"]
