FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY packages/common /app/packages/common
COPY packages/contracts /app/packages/contracts
COPY data-plane/translation-server /app/data-plane/translation-server

RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu torch
RUN pip install --no-cache-dir -e /app/packages/common -e /app/packages/contracts -e /app/data-plane/translation-server

WORKDIR /app/data-plane/translation-server
ENV PYTHONPATH=/app/data-plane/translation-server:/app/packages/common:/app/packages/contracts

EXPOSE 8003

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8003"]
