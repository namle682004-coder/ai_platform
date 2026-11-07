#!/usr/bin/env bash
# Rehearsal of the server gate on this machine: isolated stack (fresh infra, stub model runtimes with the
# model host's slots and latencies, same memory caps), then deploy/server/server_gate.sh in local mode.
#
#   scripts/loadtest_local.sh [docs_folder]     # KEEP=1 leaves the stack running afterwards
set -uo pipefail
cd "$(dirname "$0")/.."
export AIP_RAG_IMAGE=${AIP_RAG_IMAGE:-aip-rag:ocr-test}
COMPOSE=(docker compose -f deploy/docker-compose/docker-compose.loadtest.yml -p aip-loadtest)

"${COMPOSE[@]}" up -d || exit 2
echo "waiting for the RAG API…"
for _ in $(seq 1 60); do curl -fsS -m 3 http://127.0.0.1:18010/health >/dev/null 2>&1 && break; sleep 3; done
curl -fsS -m 3 http://127.0.0.1:18010/health >/dev/null || { "${COMPOSE[@]}" logs --tail 40 rag-api; exit 2; }

AIP_GATE_MODE=local AIP_GATE_API=http://127.0.0.1:18010 AIP_GATE_TENANT=loadtest \
AIP_GATE_CONTAINERS="aip-loadtest-rag-api aip-loadtest-rag-worker" AIP_GATE_DOCS=${1:-} \
AIP_GATE_SLOTS=${STUB_CHAT_SLOTS:-2} PYTHON=${PYTHON:-./venv/bin/python} \
  bash deploy/server/server_gate.sh
verdict=$?

[ "${KEEP:-0}" = 1 ] || "${COMPOSE[@]}" down -v >/dev/null 2>&1
exit $verdict
