FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

COPY packages/common /app/packages/common
COPY data-plane/stt-server /app/data-plane/stt-server

RUN pip install --no-cache-dir -e /app/packages/common -e /app/data-plane/stt-server

EXPOSE 8002

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8002"]
