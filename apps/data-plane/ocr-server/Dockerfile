FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

COPY packages/common /app/packages/common
COPY data-plane/ocr-server /app/data-plane/ocr-server

RUN pip install --no-cache-dir -e /app/packages/common -e /app/data-plane/ocr-server

EXPOSE 8004

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8004"]
