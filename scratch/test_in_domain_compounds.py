import re
import json

with open('/home/namle/AI-Projects/llm-apps/ai_platform/benchmarks/rag/datasets/enterprise/frozen_test/enterprise_golden_v2.jsonl') as f:
    cases = [json.loads(line) for line in f]

# Load documents text
with open('/home/namle/AI-Projects/llm-apps/ai_platform/benchmarks/rag/datasets/enterprise/frozen_test/enterprise_golden_v2.jsonl') as f:
    pass

from solutions.rag.infrastructure.adapters.qdrant_adapter import QdrantVectorStoreAdapter
from solutions.rag.scratch.test_compounds import extract_compound_entities

EOF
