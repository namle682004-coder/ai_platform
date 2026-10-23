# Embedding & Reranking Server

Serves the two retrieval aliases registered in MongoDB (`aliases` collection):

| Alias | Model | Endpoint |
|---|---|---|
| `embed-standard` | `BAAI/bge-m3` (1024-dim dense, optional sparse) | `POST /v1/embeddings` |
| `rerank-standard` | `BAAI/bge-reranker-v2-m3` (scores in [0, 1]) | `POST /v1/rerank` |

Both aliases point at `http://172.16.20.2:8012/v1`, so one process serves both.
Only one uvicorn worker is used: each worker would load its own copy of the weights onto the GPU.

## Run on the GPU host (msp)

```bash
mkdir -p ~/aip && cp -r embedding-server ~/aip/ && cd ~/aip/embedding-server
python3 -m venv .venv && .venv/bin/pip install "FlagEmbedding>=1.3.0" "fastapi>=0.115.0" "uvicorn[standard]>=0.32.0" "pydantic-settings>=2.0.0"

cat > .env <<'EOF'
AIP_EMBEDDING_EMBEDDING_MODEL_PATH=/home/lenam/models/bge-m3
AIP_EMBEDDING_RERANKER_MODEL_PATH=/home/lenam/models/bge-reranker
# Same value as AIP_RUNTIME_TOKEN on the gateway and the RAG service
AIP_RUNTIME_TOKEN=<shared-secret>
EOF

.venv/bin/uvicorn app:app --host 0.0.0.0 --port 8012 --workers 1
# or as a service: see aip-embedding.service
```

## Smoke test

```bash
curl -s localhost:8012/health/ready
curl -s localhost:8012/v1/embeddings -H "X-AIP-Runtime-Token: $TOKEN" \
  -H 'Content-Type: application/json' -d '{"model":"embed-standard","input":["hóa đơn điện tử"]}' | head -c 200
curl -s localhost:8012/v1/rerank -H "X-AIP-Runtime-Token: $TOKEN" -H 'Content-Type: application/json' \
  -d '{"model":"rerank-standard","query":"thủ tục hoàn thuế","documents":["Hồ sơ hoàn thuế gồm...","Lịch nghỉ Tết"]}'
```

## Configuration (`AIP_EMBEDDING_` prefix)

| Variable | Default |
|---|---|
| `EMBEDDING_MODEL_PATH` | `/home/lenam/models/bge-m3` |
| `RERANKER_MODEL_PATH` | `/home/lenam/models/bge-reranker` |
| `USE_FP16` | `true` |
| `EMBEDDING_BATCH_SIZE` / `RERANKER_BATCH_SIZE` | `16` |
| `RUNTIME_TOKEN` (or the shared `AIP_RUNTIME_TOKEN`, no prefix) | unset (then a `Bearer` header is required) |
| `PORT` | `8012` |
