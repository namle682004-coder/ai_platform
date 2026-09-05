FROM python:3.10-slim

WORKDIR /app

COPY packages/common /app/packages/common
COPY services/moderation-server /app/services/moderation-server

RUN pip install --no-cache-dir -e /app/packages/common -e /app/services/moderation-server

EXPOSE 8004

CMD ["uvicorn", "moderation_server.main:app", "--host", "0.0.0.0", "--port", "8004"]
