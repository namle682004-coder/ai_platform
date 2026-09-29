FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

COPY packages/common /app/packages/common
COPY apps/data-plane/stt-server /app/apps/data-plane/stt-server

RUN pip install --no-cache-dir -e /app/packages/common -e /app/apps/data-plane/stt-server

WORKDIR /app/apps/data-plane/stt-server
ENV PYTHONPATH=/app/apps/data-plane/stt-server:/app/packages/common

EXPOSE 8002

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8002"]
