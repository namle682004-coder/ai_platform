#!/usr/bin/env bash
# Deploy the application stack (gateway + RAG API + RAG worker) to the internal server.
#
#   scripts/deploy_server.sh [git-ref]      # default: HEAD
#
# Ships exactly one committed revision (git archive) over SSH, so the server needs no GitHub
# access and what runs there always matches a commit. The server keeps its secrets in
# $REMOTE_ENV_FILE (template: deploy/docker-compose/server.env.example).
set -euo pipefail

SSH_HOST="${AIP_SSH_HOST:-msp}"
REMOTE_ROOT="${AIP_REMOTE_ROOT:-~/aip}"
REMOTE_ENV_FILE="${AIP_REMOTE_ENV_FILE:-$REMOTE_ROOT/aip.env}"
REF="${1:-HEAD}"
MIN_FREE_DISK_GB="${AIP_MIN_FREE_DISK_GB:-6}"   # image builds need room; below this the deploy stops
MIN_FREE_MEM_MB="${AIP_MIN_FREE_MEM_MB:-1500}"  # building on a host under memory pressure can freeze it

cd "$(git rev-parse --show-toplevel)"
SHA="$(git rev-parse --short "$REF")"
if [ "$REF" = "HEAD" ] && [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "⚠ Uncommitted changes are NOT deployed; shipping commit $SHA only."
fi

echo "▶ Checking the server before deploying ..."
# Building images on a full disk / an out-of-memory host is what preceded the 2026-11-05 freeze:
# make room first, and refuse to deploy rather than push the host over.
ssh "$SSH_HOST" "set -e
  avail_gb() { df -BG --output=avail / | tail -1 | tr -dc 0-9; }
  if [ \"\$(avail_gb)\" -lt $MIN_FREE_DISK_GB ]; then
    echo \"  only \$(avail_gb) GB free on /: removing unused images and build cache\"
    docker image prune -f >/dev/null; docker builder prune -f --filter until=24h >/dev/null
  fi
  if [ \"\$(avail_gb)\" -lt $MIN_FREE_DISK_GB ]; then
    echo \"✘ \$(avail_gb) GB free on / (need $MIN_FREE_DISK_GB). Free disk first: deploy/server/disk_report.sh\"; exit 1
  fi
  avail_mb=\$(awk '/MemAvailable/ {print int(\$2/1024)}' /proc/meminfo)
  if [ \"\$avail_mb\" -lt $MIN_FREE_MEM_MB ]; then
    echo \"✘ only \${avail_mb} MB of memory available (need $MIN_FREE_MEM_MB): the host is under pressure, not building now\"; exit 1
  fi
  echo \"  disk \$(avail_gb) GB free, memory \${avail_mb} MB available\""

echo "▶ Shipping $SHA to $SSH_HOST:$REMOTE_ROOT/app ..."
ssh "$SSH_HOST" "test -f $REMOTE_ENV_FILE || { echo 'Missing $REMOTE_ENV_FILE (see deploy/docker-compose/server.env.example)'; exit 1; }
  rm -rf $REMOTE_ROOT/app.next && mkdir -p $REMOTE_ROOT/app.next"
git archive --format=tar "$REF" | ssh "$SSH_HOST" "tar -x -C $REMOTE_ROOT/app.next && echo $SHA > $REMOTE_ROOT/app.next/DEPLOYED_REVISION"
if [ -d deploy/server/certs ]; then
  echo "▶ Syncing TLS certificates to $SSH_HOST ..."
  scp -r deploy/server/certs "$SSH_HOST:$REMOTE_ROOT/app.next/deploy/server/"
fi

echo "▶ Building images and restarting the stack ..."
ssh "$SSH_HOST" "set -e
  rm -rf $REMOTE_ROOT/app.prev
  if [ -d $REMOTE_ROOT/app ]; then mv $REMOTE_ROOT/app $REMOTE_ROOT/app.prev; fi
  mv $REMOTE_ROOT/app.next $REMOTE_ROOT/app
  cd $REMOTE_ROOT/app
  docker rm -f aip-nginx 2>/dev/null || true
  export AIP_ENV_FILE=$REMOTE_ENV_FILE AIP_VERSION=$SHA
  docker compose -f deploy/docker-compose/docker-compose.server.yml up -d --build --remove-orphans
  # Disk on the server is small: keep only the images of the revision now running.
  docker images --format '{{.Repository}}:{{.Tag}}' | grep -E '^aip/(gateway|rag):' | grep -v \":$SHA\\\$\" | xargs -r docker rmi >/dev/null || true
  docker image prune -f >/dev/null
  # The build cache grows with every deploy (41 -> 45 GB of a 48 GB disk in two days): keep one day of it.
  docker builder prune -f --filter until=24h >/dev/null
  # Containers of the infra stack keep their memory caps across this deploy; re-apply in case one was recreated.
  deploy/server/apply_container_limits.sh >/dev/null || true
  df -h / | tail -1
  docker compose -f deploy/docker-compose/docker-compose.server.yml ps"

echo "✔ Deployed $SHA. Gateway: http://172.16.20.2:8000 | HTTPS: https://rag.cyber.internal"
