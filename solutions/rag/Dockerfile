FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (Tesseract OCRs scanned PDF pages during ingestion; no OCR server needed)
RUN apt-get update && apt-get install -y --no-install-recommends     curl tesseract-ocr     && rm -rf /var/lib/apt/lists/*

# Vietnamese OCR models: tessdata_best (LSTM) language + script models; the distribution's "fast" models misread
# Vietnamese diacritics (measured on dg233, see benchmarks/rag/configs/data_gate.yaml).
ENV TESSDATA_PREFIX=/usr/share/tessdata_best
RUN mkdir -p $TESSDATA_PREFIX/script \
    && for m in vie osd; do curl -fsSL -o $TESSDATA_PREFIX/$m.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/$m.traineddata; done \
    && curl -fsSL -o $TESSDATA_PREFIX/script/Vietnamese.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/script/Vietnamese.traineddata

COPY packages/contracts /app/packages/contracts
COPY packages/common /app/packages/common
COPY solutions/rag /app/solutions/rag

RUN pip install --no-cache-dir \
    aio-pika \
    fastapi \
    uvicorn \
    httpx \
    pypdf \
    pymupdf \
    flashrank \
    pydantic \
    pydantic-settings \
    python-docx \
    openpyxl \
    minio \
    motor \
    pymongo \
    grpcio \
    protobuf \
    python-multipart \
    prometheus-client \
    redis \
    pytesseract \
    pillow

ENV PYTHONPATH="/app:/app/solutions/rag:/app/packages/common:/app/packages/contracts"

EXPOSE 8010

# Same image runs both roles: the worker (default) and the REST API
# (`python -m solutions.rag.main --mode api --port 8010`).
CMD ["python", "solutions/rag/worker.py"]
