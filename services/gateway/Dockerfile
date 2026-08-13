FROM python:3.10-slim

WORKDIR /app

COPY packages/common /app/packages/common
COPY services/gateway /app/services/gateway

RUN pip install --no-cache-dir -e /app/packages/common -e /app/services/gateway

EXPOSE 8000

CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
