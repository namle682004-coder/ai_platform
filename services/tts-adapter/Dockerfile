FROM python:3.10-slim

WORKDIR /app

COPY packages/common /app/packages/common
COPY services/tts-adapter /app/services/tts-adapter

RUN pip install --no-cache-dir -e /app/packages/common -e /app/services/tts-adapter

EXPOSE 8002

CMD ["uvicorn", "tts_adapter.main:app", "--host", "0.0.0.0", "--port", "8002"]
