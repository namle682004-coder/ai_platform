#!/usr/bin/env bash
# Memory caps on the containers of the model host. A container that reaches its cap is OOM-killed and
# restarted by Docker; without a cap it takes memory from the model runtimes and from the host itself.
#
#   deploy/server/apply_container_limits.sh [--dry-run]
#
# `docker update` keeps the cap across restarts of the same container. The AIP app containers also
# get theirs from docker-compose.server.yml (mem_limit), so redeploys keep them; the infra stack
# (~/aip-infra) is not in this repo: re-run this script after recreating one of its containers.
#
# Budget on the 8 GB host (caps, not typical use): runtimes 2G + 1G + 1G (systemd MemoryMax),
# containers below ~4.5G, OS + page cache the rest. earlyoom is the last line if all peak at once.
set -euo pipefail

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

declare -A LIMITS=(
  [aip-qdrant]=1g
  [aip-rabbitmq]=512m
  [aip-minio]=512m
  [aip-redis]=256m
  [aip-gateway]=512m
  [aip-rag-api]=1g
  [aip-rag-worker]=768m
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
