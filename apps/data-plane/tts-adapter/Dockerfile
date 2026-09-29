FROM python:3.10-slim

WORKDIR /app

COPY packages/common /app/packages/common
COPY apps/data-plane/tts-adapter /app/apps/data-plane/tts-adapter

RUN pip install --no-cache-dir -e /app/packages/common -e /app/apps/data-plane/tts-adapter

WORKDIR /app/apps/data-plane/tts-adapter
ENV PYTHONPATH=/app/apps/data-plane/tts-adapter:/app/packages/common

EXPOSE 8007

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8007"]
