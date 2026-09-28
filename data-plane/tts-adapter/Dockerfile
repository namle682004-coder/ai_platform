FROM python:3.10-slim

WORKDIR /app

COPY packages/common /app/packages/common
COPY data-plane/tts-adapter /app/data-plane/tts-adapter

RUN pip install --no-cache-dir -e /app/packages/common -e /app/data-plane/tts-adapter

EXPOSE 8007

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8007"]
