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
    python-multipart

ENV PYTHONPATH="/app:/app/solutions/rag:/app/packages/common:/app/packages/contracts"

CMD ["python", "solutions/rag/worker.py"]
