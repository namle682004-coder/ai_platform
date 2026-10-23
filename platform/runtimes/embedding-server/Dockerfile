FROM pytorch/pytorch:2.4.1-cuda12.1-cudnn9-runtime

WORKDIR /app/platform/runtimes/embedding-server

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY platform/runtimes/embedding-server /app/platform/runtimes/embedding-server
RUN pip install --no-cache-dir "FlagEmbedding>=1.3.0" "fastapi>=0.115.0" "uvicorn[standard]>=0.32.0" "pydantic-settings>=2.0.0"

# Mount the weights directory at /models (e.g. -v /home/lenam/models:/models:ro)
ENV AIP_EMBEDDING_EMBEDDING_MODEL_PATH=/models/bge-m3 \
    AIP_EMBEDDING_RERANKER_MODEL_PATH=/models/bge-reranker

EXPOSE 8012
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s CMD curl -fs http://localhost:8012/health/ready || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8012", "--workers", "1"]
