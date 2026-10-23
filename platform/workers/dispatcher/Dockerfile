FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY packages/common /app/packages/common
COPY packages/contracts /app/packages/contracts
COPY platform/workers/dispatcher /app/platform/workers/dispatcher

RUN pip install --no-cache-dir \
    -e /app/packages/common \
    -e /app/packages/contracts \
    -e /app/platform/workers/dispatcher

WORKDIR /app/platform/workers/dispatcher
ENV PYTHONPATH=/app/platform/workers/dispatcher:/app/platform/workers/dispatcher/src:/app/packages/common:/app/packages/contracts

CMD ["python", "-m", "src.main"]
