#!/usr/bin/env bash
# Read-only report of what fills the disk of the model host, with what could be freed. Deletes nothing.
#   deploy/onprem/host/scripts/disk_report.sh            (on the server)   |   ssh msp 'bash -s' < deploy/onprem/host/scripts/disk_report.sh
set -uo pipefail

echo "== physical disks and volumes (is there unallocated space for the root volume?)"
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT 2>/dev/null
command -v vgs >/dev/null && vgs 2>/dev/null | sed 's/^/  /' || echo "  (vgs needs root: 'sudo vgs' shows VFree = space the root volume can grow into)"
echo
echo "== root filesystem"; df -h / | sed 's/^/  /'
echo
echo "== home directories"; du -sh "$HOME"/* "$HOME"/.cache 2>/dev/null | sort -rh | head -15 | sed 's/^/  /'
echo
echo "== models"; du -sh "$HOME"/models/*/* 2>/dev/null | sort -rh | head -15 | sed 's/^/  /'
echo
echo "== docker"; docker system df 2>/dev/null | sed 's/^/  /'
echo
echo "== model files in use by running runtimes"
ps -eo args | grep -o -- '-m [^ ]*' | awk '{print "  " $2}' | sort -u
echo
echo "== could be freed (review before deleting anything)"
echo "  docker image prune -f && docker builder prune -f      # unused images, build cache"
echo "  model files above that no running runtime uses (e.g. ONNX / PyTorch copies of a GGUF model)"
echo "  ~/vllm-env if no service uses it (check: ps -eo args | grep vllm-env)"
echo "  sudo lvextend -r -l +100%FREE /dev/ubuntu-vg/ubuntu-lv  # only if 'sudo vgs' shows VFree > 0"
