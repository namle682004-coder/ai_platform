FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl && rm -rf /var/lib/apt/lists/*

COPY packages/common /app/packages/common
COPY packages/contracts /app/packages/contracts
COPY platform/runtimes/stt-server /app/platform/runtimes/stt-server

RUN pip install --no-cache-dir \
    -e /app/packages/common \
    -e /app/packages/contracts \
    -e /app/platform/runtimes/stt-server

WORKDIR /app/platform/runtimes/stt-server
ENV PYTHONPATH=/app/platform/runtimes/stt-server:/app/packages/common:/app/packages/contracts

EXPOSE 8002

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8002"]
