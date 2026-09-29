FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY packages/common /app/packages/common
COPY packages/contracts /app/packages/contracts
COPY apps/data-plane/tts-adapter /app/apps/data-plane/tts-adapter

RUN pip install --no-cache-dir \
    -e /app/packages/common \
    -e /app/packages/contracts \
    -e /app/apps/data-plane/tts-adapter

WORKDIR /app/apps/data-plane/tts-adapter
ENV PYTHONPATH=/app/apps/data-plane/tts-adapter:/app/packages/common:/app/packages/contracts

EXPOSE 8007

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8007"]
