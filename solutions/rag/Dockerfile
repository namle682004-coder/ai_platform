FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends     curl     && rm -rf /var/lib/apt/lists/*

COPY packages/contracts /app/packages/contracts
COPY packages/common /app/packages/common
COPY solutions/rag /app/solutions/rag

RUN pip install --no-cache-dir \
    aio-pika \
    fastapi \
    uvicorn \
    httpx \
    pypdf \
    pymupdf \
    flashrank \
    pydantic \
    pydantic-settings \
    python-docx \
    openpyxl \
    minio \
    motor \
    pymongo \
    grpcio \
    protobuf \
    python-multipart \
    prometheus-client \
    redis

ENV PYTHONPATH="/app:/app/solutions/rag:/app/packages/common:/app/packages/contracts"

EXPOSE 8010

# Same image runs both roles: the worker (default) and the REST API
# (`python -m solutions.rag.main --mode api --port 8010`).
CMD ["python", "solutions/rag/worker.py"]
