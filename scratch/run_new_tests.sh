#!/usr/bin/env bash
cd ~/AI-Projects/llm-apps/ai_platform
export PYTHONPATH=.:packages/common:packages/contracts:tests:benchmarks/rag/src
for f in tests/test_rag_restated_turns.py tests/test_diacritics_restoration.py tests/test_vietnamese_id_recognition.py tests/test_rag_session_ids.py tests/test_rag_observability.py tests/test_rag_faq_admin.py tests/test_rag_answer_pipeline.py tests/test_rag_stability.py; do
  out=$(timeout 90 ./venv/bin/pytest -q -p no:cacheprovider -x "$f" 2>&1); code=$?
  echo "$f :: exit=$code :: $(echo "$out" | tail -1)"
done
