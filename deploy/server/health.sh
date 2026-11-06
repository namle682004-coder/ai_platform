#!/usr/bin/env bash
# Read-only health check of the model host: memory, disk, load, GPU, model runtimes, containers.
# Exit code: 0 healthy, 1 warning, 2 critical – usable from cron, CI or before an evaluation run.
#
#   deploy/server/health.sh                 # on the server
#   ssh msp 'bash -s' < deploy/server/health.sh   # from a workstation
set -uo pipefail

WARN_MEM_MB="${AIP_WARN_MEM_MB:-1500}"; CRIT_MEM_MB="${AIP_CRIT_MEM_MB:-600}"
WARN_DISK_PCT="${AIP_WARN_DISK_PCT:-85}"; CRIT_DISK_PCT="${AIP_CRIT_DISK_PCT:-95}"
status=0
flag() { # flag <level 1|2> <message>
  [ "$1" -gt "$status" ] && status=$1
  [ "$1" = 2 ] && echo "  ✘ CRITICAL: $2" || echo "  ! WARNING: $2"
}

cpus=$(nproc)
avail_mb=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
total_mb=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
disk_pct=$(df --output=pcent / | tail -1 | tr -dc 0-9)
disk_avail=$(df -h --output=avail / | tail -1 | tr -d ' ')
load1=$(cut -d' ' -f1 /proc/loadavg)

echo "== $(hostname) $(date '+%F %T')"
echo "memory: ${avail_mb} MB available of ${total_mb} MB | disk /: ${disk_pct}% used, ${disk_avail} free | load: $load1 (${cpus} CPUs)"
[ "$avail_mb" -lt "$CRIT_MEM_MB" ] && flag 2 "memory available ${avail_mb} MB < ${CRIT_MEM_MB} MB" \
  || { [ "$avail_mb" -lt "$WARN_MEM_MB" ] && flag 1 "memory available ${avail_mb} MB < ${WARN_MEM_MB} MB"; }
[ "$disk_pct" -ge "$CRIT_DISK_PCT" ] && flag 2 "disk / ${disk_pct}% used" \
  || { [ "$disk_pct" -ge "$WARN_DISK_PCT" ] && flag 1 "disk / ${disk_pct}% used"; }
awk -v l="$load1" -v c="$cpus" 'BEGIN { exit !(l > 4 * c) }' && flag 2 "load $load1 > 4 x $cpus CPUs (host thrashing?)"
swapon --show | grep -q . || echo "  (no swap configured)"
systemctl is-active --quiet earlyoom 2>/dev/null || flag 1 "earlyoom is not running (deploy/server/install.sh)"

echo "-- GPU"
nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv,noheader 2>/dev/null || flag 1 "nvidia-smi unavailable"

echo "-- model runtimes"
for spec in chat:8011 embedding:8012 rerank:8013; do
  name=${spec%%:*}; port=${spec##*:}
  code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/health")
  unit=$(systemctl is-active "aip-model@$name" 2>/dev/null || true)
  rss=$(ps -o rss= -p "$(ss -ltnpH "sport = :$port" 2>/dev/null | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)" 2>/dev/null | awk '{print int($1/1024)}')
  echo "  $name :$port health=$code service=${unit:-none} rss=${rss:-?}MB"
  [ "$code" = 200 ] || flag 2 "$name runtime on :$port not healthy (HTTP $code)"
  [ "$unit" = active ] || flag 1 "$name runtime is not the systemd service aip-model@$name (no memory cap / no restart)"
done

echo "-- containers (memory use / cap)"
docker stats --no-stream --format '  {{.Name}}: {{.MemUsage}} ({{.MemPerc}})' 2>/dev/null | grep aip- || echo "  docker unavailable"
for c in $(docker ps --format '{{.Names}}' 2>/dev/null | grep '^aip-'); do
  [ "$(docker inspect -f '{{.HostConfig.Memory}}' "$c")" = 0 ] && flag 1 "container $c has no memory cap (deploy/server/apply_container_limits.sh)"
done

echo "-- RAG overload state"
curl -s -m 5 http://127.0.0.1:8010/health 2>/dev/null | head -c 600; echo

case $status in 0) echo "== HEALTHY";; 1) echo "== WARNING";; *) echo "== CRITICAL";; esac
exit $status
