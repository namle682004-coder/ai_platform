#!/usr/bin/env bash
# Server readiness gate: one command after a deploy, PASS / FAIL. Standard and thresholds:
# .claude/skills/rag-production-quality/infra-standard.md
#
#   deploy/server/server_gate.sh                      # on msp, against the deployed stack
#   AIP_GATE_MODE=local scripts/loadtest_local.sh     # same phases on the local rehearsal stack (stub runtimes)
#
# Phases (each must pass; a later phase still runs so the report is complete):
#   0 preflight   host health (deploy/server/health.sh): memory, disk, earlyoom, model runtimes, caps
#   1 steady      as many users as chat slots: nearly every request answered, p95 / TTFT within bounds
#   2 burst       far more users than slots: refused cleanly (429 / 503), nothing hangs, no 5xx
#   3 ingestion   documents uploaded *during* a chat burst are indexed; chat protections still hold
#   4 postcheck   no container OOM-killed or restarted, no kernel OOM, model runtimes not restarted, host healthy
#
# Environment (defaults for the msp lab host, one chat model with --parallel 2):
#   AIP_GATE_API        RAG API base URL                     (http://127.0.0.1:8010)
#   AIP_GATE_TENANT     tenant used for the test traffic      (gate_<date>)
#   AIP_GATE_DOCS       folder of test documents to upload    (optional; phase 3 skipped without it)
#   AIP_GATE_HEADER     extra header, e.g. "X-AIP-Runtime-Token: …"
#   AIP_GATE_SLOTS      chat slots of the model runtime       (2)
#   AIP_GATE_MAX_P95    steady p95 seconds                    (45)
#   AIP_GATE_MAX_TTFT   steady p95 time to first token, s     (15)
#   AIP_GATE_CONTAINERS containers watched                   (aip-rag-api aip-rag-worker aip-gateway)
#   AIP_GATE_MODE       server | local (local skips host checks that need systemd / journald)
#   AIP_GATE_OUT        report folder                         (/tmp/aip_gate_<timestamp>)
set -uo pipefail
cd "$(dirname "$0")/../.."

API=${AIP_GATE_API:-http://127.0.0.1:8010}
TENANT=${AIP_GATE_TENANT:-gate_$(date +%Y%m%d)}
SLOTS=${AIP_GATE_SLOTS:-2}
MAX_P95=${AIP_GATE_MAX_P95:-45}
MAX_TTFT=${AIP_GATE_MAX_TTFT:-15}
MODE=${AIP_GATE_MODE:-server}
CONTAINERS=${AIP_GATE_CONTAINERS:-aip-rag-api aip-rag-worker aip-gateway}
OUT=${AIP_GATE_OUT:-${TMPDIR:-/tmp}/aip_gate_$(date +%Y%m%d_%H%M%S)}
PY=${PYTHON:-python3}
mkdir -p "$OUT"
HDR=(); [ -n "${AIP_GATE_HEADER:-}" ] && HDR=(--header "$AIP_GATE_HEADER")
CURL_HDR=(-H "X-Tenant-ID: $TENANT" -H "X-User-Role: admin"); [ -n "${AIP_GATE_HEADER:-}" ] && CURL_HDR+=(-H "$AIP_GATE_HEADER")
existing=""; for c in $CONTAINERS; do docker inspect "$c" >/dev/null 2>&1 && existing="$existing $c"; done
declare -A RESULT
start_epoch=$(date +%s)

load() { # load <name> <users> <requests> [extra args…]
  local name=$1 users=$2 requests=$3; shift 3
  echo; echo "### $name: $users users, $requests requests"
  $PY scripts/load_test_rag.py --api "$API" --tenant "$TENANT" --users "$users" --requests "$requests" \
    "${HDR[@]}" --containers $existing --out "$OUT/$name.json" "$@" | tee "$OUT/$name.log"
  return "${PIPESTATUS[0]}"
}

model_restarts() {
  [ "$MODE" = server ] || { echo "-"; return; }
  for u in chat embedding rerank; do systemctl show "aip-model@$u" -p NRestarts --value 2>/dev/null; done | paste -sd,
}

echo "== server gate: api=$API tenant=$TENANT slots=$SLOTS mode=$MODE out=$OUT"
runtime_restarts_before=$(model_restarts)

# 0 preflight
if [ "$MODE" = server ]; then
  bash deploy/server/health.sh | tee "$OUT/preflight.log"; code=${PIPESTATUS[0]}
  RESULT[0_preflight]=$([ "$code" -le 1 ] && echo PASS || echo "FAIL (health.sh exit $code)")
else
  curl -fsS -m 5 "$API/health" >/dev/null && RESULT[0_preflight]=PASS || RESULT[0_preflight]="FAIL (API not healthy)"
fi

# 1 steady: users = chat slots
load steady "$SLOTS" $((SLOTS * 6)) --stream --min-success 0.95 --max-p95 "$MAX_P95" --max-ttft-p95 "$MAX_TTFT"
RESULT[1_steady]=$([ $? = 0 ] && echo PASS || echo FAIL)

cooldown() { # rate limits count per minute: each phase starts with a fresh window
  echo "  (cooldown ${AIP_GATE_COOLDOWN:-65}s for the rate-limit window)"; sleep "${AIP_GATE_COOLDOWN:-65}"
}

cooldown
# 2 burst: 8x the slots
load burst $((SLOTS * 8)) $((SLOTS * 24)) --max-latency 90
RESULT[2_burst]=$([ $? = 0 ] && echo PASS || echo FAIL)

# 3 ingestion under chat load
if [ -n "${AIP_GATE_DOCS:-}" ] && [ -d "${AIP_GATE_DOCS}" ]; then
  cooldown
  echo; echo "### ingestion during a chat burst"
  ids=()
  while IFS= read -r -d '' f; do
    r=$(curl -s -m 120 "${CURL_HDR[@]}" -F "file=@$f" "$API/v1/knowledge/documents/upload?wait_for_completion=false")
    id=$(echo "$r" | $PY -c 'import json,sys; print(json.load(sys.stdin).get("doc_id",""))' 2>/dev/null)
    echo "  uploaded $(basename "$f") -> ${id:-ERROR $r}"; [ -n "$id" ] && ids+=("$id")
  done < <(find "$AIP_GATE_DOCS" -maxdepth 1 -type f \( -name '*.pdf' -o -name '*.docx' -o -name '*.xlsx' \) -print0)
  load ingest_burst $((SLOTS * 4)) $((SLOTS * 12)) --max-latency 90; chat_ok=$?
  pending=${#ids[@]}; failed=0; deadline=$(( $(date +%s) + ${AIP_GATE_INGEST_TIMEOUT:-900} ))
  while [ "$pending" -gt 0 ] && [ "$(date +%s)" -lt "$deadline" ]; do
    pending=0; failed=0
    for id in "${ids[@]}"; do
      st=$(curl -s -m 10 "${CURL_HDR[@]}" "$API/v1/knowledge/documents/$id" | $PY -c 'import json,sys; print(json.load(sys.stdin).get("status",""))' 2>/dev/null)
      case "$st" in INDEXED) ;; FAILED) failed=$((failed + 1));; *) pending=$((pending + 1));; esac
    done
    [ "$pending" -gt 0 ] && sleep 10
  done
  echo "  documents: ${#ids[@]} uploaded, $failed failed, $pending still pending"
  RESULT[3_ingestion]=$([ "$chat_ok" = 0 ] && [ "$failed" = 0 ] && [ "$pending" = 0 ] && [ "${#ids[@]}" -gt 0 ] \
    && echo PASS || echo "FAIL (chat=$chat_ok failed=$failed pending=$pending)")
  for id in "${ids[@]}"; do curl -s -m 30 -X DELETE "${CURL_HDR[@]}" "$API/v1/knowledge/documents/$id" >/dev/null; done
else
  RESULT[3_ingestion]="SKIPPED (set AIP_GATE_DOCS)"
fi

# 4 postcheck
problems=""
for c in $existing; do
  st=$(docker inspect -f '{{.State.OOMKilled}} {{.State.Running}}' "$c" 2>/dev/null)
  [ "$st" = "false true" ] || problems="$problems $c:$st"
done
if [ "$MODE" = server ]; then
  oom=$(journalctl -k --since "@$start_epoch" 2>/dev/null | grep -ci -E "out of memory|oom-kill")
  [ "${oom:-0}" -gt 0 ] && problems="$problems kernel-oom:$oom"
  after=$(model_restarts); [ "$after" = "$runtime_restarts_before" ] || problems="$problems model-restarts:$runtime_restarts_before->$after"
  bash deploy/server/health.sh > "$OUT/postcheck.log"; [ $? -le 1 ] || problems="$problems health-critical"
fi
RESULT[4_postcheck]=$([ -z "$problems" ] && echo PASS || echo "FAIL ($problems )")

echo; echo "== SERVER GATE ($(date '+%F %T'))"
verdict=0
for k in $(printf '%s\n' "${!RESULT[@]}" | sort); do
  echo "  $k: ${RESULT[$k]}"; case "${RESULT[$k]}" in FAIL*) verdict=1;; esac
done
echo "  reports: $OUT"
echo "== $([ $verdict = 0 ] && echo PASS || echo FAIL)"
exit $verdict
