FROM python:3.10-slim

WORKDIR /app

COPY packages/common /app/packages/common
COPY data-plane/moderation-server /app/data-plane/moderation-server

RUN pip install --no-cache-dir -e /app/packages/common -e /app/data-plane/moderation-server

EXPOSE 8006

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8006"]
