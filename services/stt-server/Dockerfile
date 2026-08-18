FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

COPY packages/common /app/packages/common
COPY services/stt-server /app/services/stt-server

RUN pip install --no-cache-dir -e /app/packages/common -e /app/services/stt-server

EXPOSE 8001

CMD ["uvicorn", "stt_server.main:app", "--host", "0.0.0.0", "--port", "8001"]
