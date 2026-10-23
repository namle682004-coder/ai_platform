FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY packages/common /app/packages/common
COPY packages/contracts /app/packages/contracts
COPY platform/workers/callback /app/platform/workers/callback

RUN pip install --no-cache-dir \
    -e /app/packages/common \
    -e /app/packages/contracts \
    -e /app/platform/workers/callback

WORKDIR /app/platform/workers/callback
ENV PYTHONPATH=/app/platform/workers/callback:/app/packages/common:/app/packages/contracts

CMD ["python", "worker/main.py"]
