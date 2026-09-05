FROM python:3.10-slim

WORKDIR /app

COPY packages/common /app/packages/common
COPY services/translation-server /app/services/translation-server

RUN pip install --no-cache-dir -e /app/packages/common -e /app/services/translation-server

EXPOSE 8003

CMD ["uvicorn", "translation_server.main:app", "--host", "0.0.0.0", "--port", "8003"]
