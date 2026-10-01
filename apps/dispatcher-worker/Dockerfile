FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY packages/common /app/packages/common
COPY packages/contracts /app/packages/contracts
COPY apps/dispatcher-worker /app/apps/dispatcher-worker

RUN pip install --no-cache-dir \
    -e /app/packages/common \
    -e /app/packages/contracts \
    -e /app/apps/dispatcher-worker

WORKDIR /app/apps/dispatcher-worker
ENV PYTHONPATH=/app/apps/dispatcher-worker:/app/apps/dispatcher-worker/src:/app/packages/common:/app/packages/contracts

CMD ["python", "-m", "src.main"]
