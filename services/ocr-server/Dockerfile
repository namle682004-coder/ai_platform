FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

COPY packages/common /app/packages/common
COPY services/ocr-server /app/services/ocr-server

RUN pip install --no-cache-dir -e /app/packages/common -e /app/services/ocr-server

EXPOSE 8005

CMD ["uvicorn", "ocr_server.main:app", "--host", "0.0.0.0", "--port", "8005"]
