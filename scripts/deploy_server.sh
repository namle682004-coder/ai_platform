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

cd "$(git rev-parse --show-toplevel)"
SHA="$(git rev-parse --short "$REF")"
if [ "$REF" = "HEAD" ] && [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "⚠ Uncommitted changes are NOT deployed; shipping commit $SHA only."
fi

echo "▶ Shipping $SHA to $SSH_HOST:$REMOTE_ROOT/app ..."
ssh "$SSH_HOST" "test -f $REMOTE_ENV_FILE || { echo 'Missing $REMOTE_ENV_FILE (see deploy/docker-compose/server.env.example)'; exit 1; }
  rm -rf $REMOTE_ROOT/app.next && mkdir -p $REMOTE_ROOT/app.next"
git archive --format=tar "$REF" | ssh "$SSH_HOST" "tar -x -C $REMOTE_ROOT/app.next && echo $SHA > $REMOTE_ROOT/app.next/DEPLOYED_REVISION"

echo "▶ Building images and restarting the stack ..."
ssh "$SSH_HOST" "set -e
  rm -rf $REMOTE_ROOT/app.prev
  if [ -d $REMOTE_ROOT/app ]; then mv $REMOTE_ROOT/app $REMOTE_ROOT/app.prev; fi
  mv $REMOTE_ROOT/app.next $REMOTE_ROOT/app
  cd $REMOTE_ROOT/app
  export AIP_ENV_FILE=$REMOTE_ENV_FILE AIP_VERSION=$SHA
  docker compose -f deploy/docker-compose/docker-compose.server.yml up -d --build --remove-orphans
  # Disk on the server is small: keep only the images of the revision now running.
  docker images --format '{{.Repository}}:{{.Tag}}' | grep -E '^aip/(gateway|rag):' | grep -v \":$SHA\\\$\" | xargs -r docker rmi >/dev/null || true
  docker image prune -f >/dev/null
  docker compose -f deploy/docker-compose/docker-compose.server.yml ps"

echo "✔ Deployed $SHA. Gateway: http://172.16.20.2:8000"
