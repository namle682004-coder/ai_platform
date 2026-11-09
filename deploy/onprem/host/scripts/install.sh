#!/usr/bin/env bash
# One-time hardening of the model host (msp / 172.16.20.2) after the 2026-11-05 incident: the host ran
# out of memory under chat load, stopped answering SSH and ping, and needed a manual reset.
#
# Run ON THE SERVER, from a checkout of this repo (needs sudo):
#   sudo deploy/onprem/host/scripts/install.sh            # apply
#   sudo deploy/onprem/host/scripts/install.sh --dry-run  # only print what would be done
#
# What it sets up (each step is idempotent):
#   1. Model runtimes as systemd services (aip-model@chat|embedding|rerank) with a memory cap each,
#      restart on failure and start on boot; the hand-started llama-servers are stopped first.
#   2. earlyoom: under memory pressure it kills the largest runtime *before* the kernel starts thrashing,
#      so the host never freezes; sshd / dockerd / systemd are never chosen.
#   3. Memory caps on the Docker containers (infra + AIP app), so no container can starve the host.
#   4. A small swap file as a buffer (only when the disk has room), vm.swappiness low.
#   5. Disk hygiene: journald and model logs capped, so logs cannot fill the root filesystem.
set -euo pipefail

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1
HERE="$(cd "$(dirname "$0")" && pwd)"
RUN_USER="${AIP_RUN_USER:-lenam}"

run() { echo "+ $*"; [ "$DRY" = 1 ] || "$@"; }
write() {  # write <path> <content>
  echo "+ write $1"; [ "$DRY" = 1 ] && { printf '%s\n' "$2" | sed 's/^/    /'; return; }
  printf '%s\n' "$2" > "$1"
}

[ "$DRY" = 1 ] || [ "$(id -u)" = 0 ] || { echo "Run with sudo (or --dry-run)."; exit 1; }

echo "== 1. Model runtimes as systemd services"
run mkdir -p /etc/aip/models /var/log/aip
run chown "$RUN_USER" /var/log/aip
run install -m 0644 "$HERE/../systemd/aip-model@.service" /etc/systemd/system/aip-model@.service
for name in chat embedding rerank; do
  env_file="/etc/aip/models/$name.env"
  if [ -f "$env_file" ]; then
    echo "  keep existing $env_file (compare with $HERE/../models/$name.env)"
  else
    run install -m 0644 "$HERE/../models/$name.env" "$env_file"
  fi
  src="$env_file"; [ -f "$src" ] || src="$HERE/../models/$name.env"
  high=$(grep -E '^MEMORY_HIGH=' "$src" | cut -d= -f2); max=$(grep -E '^MEMORY_MAX=' "$src" | cut -d= -f2)
  run mkdir -p "/etc/systemd/system/aip-model@$name.service.d"
  write "/etc/systemd/system/aip-model@$name.service.d/memory.conf" "[Service]
MemoryHigh=${high:-3G}
MemoryMax=${max:-5G}"
done
# Stop runtimes started by hand (nohup) on the same ports before the services take them over.
for port in 8011 8012 8013; do
  pids=$(ss -ltnpH "sport = :$port" 2>/dev/null | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u || true)
  for pid in $pids; do
    if ! systemctl status "$pid" 2>/dev/null | grep -q 'aip-model@'; then run kill "$pid"; fi
  done
done
run systemctl daemon-reload
for name in chat embedding rerank; do run systemctl enable --now "aip-model@$name"; done

echo "== 2. earlyoom (kill the biggest runtime before the host thrashes)"
if ! command -v earlyoom >/dev/null 2>&1; then run apt-get install -y earlyoom; fi
write /etc/default/earlyoom 'EARLYOOM_ARGS="-m 6,3 -s 100,100 -r 300 --prefer (^|/)llama-server$ --avoid (^|/)(sshd|systemd|dockerd|containerd|journald)$"'
run systemctl enable --now earlyoom
run systemctl restart earlyoom

echo "== 3. Memory caps on containers (survive restarts; re-run after recreating a container)"
if [ "$DRY" = 1 ]; then "$HERE/apply_container_limits.sh" --dry-run; else "$HERE/apply_container_limits.sh"; fi

echo "== 4. Swap buffer (2 GB, only with room on /)"
if swapon --show | grep -q .; then
  echo "  swap already on"
else
  free_gb=$(df -BG --output=avail / | tail -1 | tr -dc 0-9)
  if [ "${free_gb:-0}" -ge 8 ]; then
    run fallocate -l 2G /swapfile && run chmod 600 /swapfile && run mkswap /swapfile && run swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || { [ "$DRY" = 1 ] || echo '/swapfile none swap sw 0 0' >> /etc/fstab; }
  else
    echo "  SKIP: only ${free_gb:-?} GB free on / (need 8). Free disk first (deploy/onprem/host/scripts/disk_report.sh)."
  fi
fi
write /etc/sysctl.d/90-aip.conf "vm.swappiness=10
vm.min_free_kbytes=131072"
run sysctl --system >/dev/null

echo "== 5. Logs cannot fill the disk"
run mkdir -p /etc/systemd/journald.conf.d
write /etc/systemd/journald.conf.d/aip.conf "[Journal]
SystemMaxUse=200M"
run systemctl restart systemd-journald
write /etc/logrotate.d/aip "/var/log/aip/*.log {
  daily
  rotate 5
  maxsize 50M
  compress
  missingok
  notifempty
  copytruncate
}"
write /etc/docker/daemon.json.aip-hint "Container logs: add to /etc/docker/daemon.json then restart docker:
{\"log-driver\": \"json-file\", \"log-opts\": {\"max-size\": \"20m\", \"max-file\": \"3\"}}"

echo
echo "Done. Check: systemctl status 'aip-model@*' earlyoom; deploy/onprem/host/scripts/health.sh"
