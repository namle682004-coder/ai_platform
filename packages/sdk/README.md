# AI Inference Platform (AIP) Enterprise Python SDK

Official Enterprise Python Client SDK for the AI Inference Platform (AIP).

## Installation

```bash
pip install aip-sdk
```

## Quickstart Usage

```python
from aip_sdk import AIPClient

# Initialize client with your API Key & Enterprise Gateway Base URL
client = AIPClient(
    api_key="aip_live_your_api_key_here",
    base_url="http://localhost:8000"
)

# 1. Chat Completion API
response = client.chat.create(
    model="chat-general-standard",
    messages=[{"role": "user", "content": "Hello, AIP!"}]
)
print(response)

# 2. Text Vector Embedding API
embed_res = client.embeddings.create(
    model="embed-standard",
    input="Hệ thống AI Inference Platform"
)
print(embed_res)

# 3. Async Job Creation API
job_res = client.jobs.create(
    job_type="video_generation",
    alias_name="video-gen-standard"
)
print(job_res)
```

## Requirements

- Python 3.10 or higher
- `httpx >= 0.27.0`
