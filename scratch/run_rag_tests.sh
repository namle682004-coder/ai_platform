#!/usr/bin/env bash
cd ~/AI-Projects/llm-apps/ai_platform
export PYTHONPATH=.:packages/common:packages/contracts:packages/sdk:platform/gateway:platform/gateway/src
for f in tests/test_rag_*.py tests/test_answer_verification.py tests/test_numeric_and_units.py \
         tests/test_hard_gatekeeper_and_cutoff.py tests/test_context_combine.py tests/test_multi_hop_iterative_rag.py \
         tests/test_pre_retrieval_optimization.py tests/test_tenant_id_consistency.py \
         tests/test_clean_architecture_ports.py tests/test_architecture_srs2.py; do
  out=$(timeout 150 ./venv/bin/pytest -q -p no:cacheprovider "$f" 2>&1)
  code=$?
  echo "$f :: exit=$code :: $(echo "$out" | tail -1)"
  if [ $code -ne 0 ]; then echo "$out" | grep -E "^(FAILED|ERROR)" | head -10; fi
done
