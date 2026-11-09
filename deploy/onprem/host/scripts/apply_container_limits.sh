#!/usr/bin/env bash
# Memory caps on the containers of the model host. A container that reaches its cap is OOM-killed and
# restarted by Docker; without a cap it takes memory from the model runtimes and from the host itself.
#
#   deploy/onprem/host/scripts/apply_container_limits.sh [--dry-run]
#
# `docker update` keeps the cap across restarts of the same container. The AIP app containers also
# get theirs from docker-compose.server.yml (mem_limit), so redeploys keep them; the infra stack
# (~/aip-infra) is not in this repo: re-run this script after recreating one of its containers.
#
# Budget on the 32 GB host (caps, not typical use):
# - Host model runtimes: chat 5G + embedding 2.5G + rerank 2.5G = ~10G (systemd MemoryMax)
# - App & Infra containers: ~12G
# - OS + page cache + buffers: ~10G
# earlyoom remains the last defense line if unexpected spikes occur.
set -euo pipefail

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

declare -A LIMITS=(
  [aip-qdrant]=2g
  [aip-rabbitmq]=1g
  [aip-minio]=1g
  [aip-redis]=512m
  [aip-gateway]=1g
  [aip-litellm]=1g
  [aip-rag-api]=2g
  [aip-rag-worker]=1536m
  [aip-nginx]=128m
)

for name in "${!LIMITS[@]}"; do
  limit="${LIMITS[$name]}"
  if ! docker inspect "$name" >/dev/null 2>&1; then
    echo "  skip $name (no such container)"
    continue
  fi
  echo "+ docker update --memory $limit --memory-swap $limit $name"
  [ "$DRY" = 1 ] || docker update --memory "$limit" --memory-swap "$limit" "$name" >/dev/null
done
