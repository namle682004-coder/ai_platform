FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl gcc g++ && rm -rf /var/lib/apt/lists/*

COPY packages/common /app/packages/common
COPY packages/contracts /app/packages/contracts
COPY apps/data-plane/vllm-engine /app/apps/data-plane/vllm-engine

RUN pip install --no-cache-dir torch transformers accelerate
RUN pip install --no-cache-dir -e /app/packages/common -e /app/apps/data-plane/vllm-engine

WORKDIR /app/apps/data-plane/vllm-engine
ENV PYTHONPATH=/app/apps/data-plane/vllm-engine:/app/packages/common:/app/packages/contracts

EXPOSE 8001

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
