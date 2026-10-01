FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY packages/common /app/packages/common
COPY packages/contracts /app/packages/contracts
COPY apps/callback-worker /app/apps/callback-worker

RUN pip install --no-cache-dir \
    -e /app/packages/common \
    -e /app/packages/contracts \
    -e /app/apps/callback-worker

WORKDIR /app/apps/callback-worker
ENV PYTHONPATH=/app/apps/callback-worker:/app/packages/common:/app/packages/contracts

CMD ["python", "worker/main.py"]
