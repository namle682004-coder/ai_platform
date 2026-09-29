#!/usr/bin/env bash
set -e

echo "🚀 [1/2] Checking syntax & linter with Ruff (0.5s)..."
.venv/bin/ruff check apps/ packages/ tests/ scripts/

echo "🧪 [2/2] Running fast regression test suite (3s)..."
TEST_MODE=true VLLM_TEST_MODE=true PYTHONPATH='.:packages/common:packages/contracts:packages/sdk:apps/control-plane:apps/control-plane/src' \
  .venv/bin/pytest tests/test_gateway.py tests/test_dcp_enhancements.py -q --disable-warnings

echo "✅ All local fast checks PASSED! Safe to commit and push."
