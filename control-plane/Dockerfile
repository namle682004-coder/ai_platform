FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY packages/common /app/packages/common
COPY packages/contracts /app/packages/contracts
COPY control-plane /app/control-plane

RUN pip install --no-cache-dir \
    -e /app/packages/common \
    -e /app/packages/contracts \
    -e /app/control-plane

WORKDIR /app/control-plane
ENV PYTHONPATH=/app/control-plane:/app/packages/common:/app/packages/contracts

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
