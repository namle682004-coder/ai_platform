#!/usr/bin/env bash

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$DIR/.venv/bin"
PID_DIR="/tmp/aip_services"
mkdir -p "$PID_DIR"

# Native development uses the repository model registry; Docker mounts it at /models.
export AIP_MODEL_REGISTRY_PATH="${AIP_MODEL_REGISTRY_PATH:-$DIR/models}"
export LD_LIBRARY_PATH="/home/namle/AI-Projects/llm-apps/qdrant-deploy/venv/lib/python3.10/site-packages/nvidia/cublas/lib:$DIR/.venv/lib/python3.10/site-packages/nvidia/cublas/lib:$LD_LIBRARY_PATH"

SERVICES=(
  "8001:vllm-engine:data-plane/vllm-engine:app:app"
  "8002:stt-server:data-plane/stt-server:app:app"
  "8003:translation-server:data-plane/translation-server:app:app"
  "8004:ocr-server:data-plane/ocr-server:app:app"
  "8006:moderation-server:data-plane/moderation-server:app:app"
  "8007:tts-adapter:data-plane/tts-adapter:app:app"
)

is_port_listening() {
  local port=$1
  ss -tulpn 2>/dev/null | grep -q ":$port "
}

start_all() {
  echo "════════════════════════════════════════════════════════════════"
  echo "🚀 Khởi động tất cả AI Data-Plane Microservices (Native WSL2)..."
  echo "════════════════════════════════════════════════════════════════"

  for item in "${SERVICES[@]}"; do
    IFS=":" read -r port name sdir app_cmd <<< "$item"
    if is_port_listening "$port"; then
      echo "  [ALREADY RUNNING] Port $port: $name"
    else
      echo -n "  [STARTING] Port $port: $name ... "
      cd "$DIR/$sdir"
      PYTHONPATH="$DIR/packages/common:$DIR/packages/contracts:." \
      nohup "$VENV/uvicorn" $app_cmd --host 0.0.0.0 --port "$port" > "/tmp/${name}.log" 2>&1 &
      local pid=$!
      echo "$pid" > "$PID_DIR/${name}.pid"
      sleep 1.5
      if is_port_listening "$port"; then
        echo "SUCCESS (PID: $pid)"
      else
        echo "STARTED (PID: $pid - log: /tmp/${name}.log)"
      fi
    fi
  done
  echo ""
  status_all
}

stop_all() {
  echo "════════════════════════════════════════════════════════════════"
  echo "🛑 Dừng tất cả AI Data-Plane Microservices & Giải phóng VRAM/RAM"
  echo "════════════════════════════════════════════════════════════════"

  for item in "${SERVICES[@]}"; do
    IFS=":" read -r port name sdir app_cmd <<< "$item"
    echo -n "  [STOPPING] Port $port: $name ... "
    # Try kill by pid file
    if [ -f "$PID_DIR/${name}.pid" ]; then
      local pid=$(cat "$PID_DIR/${name}.pid")
      kill "$pid" 2>/dev/null || true
      rm -f "$PID_DIR/${name}.pid"
    fi
    # Kill by port if still listening
    fuser -k "${port}/tcp" 2>/dev/null || true
    echo "DONE"
  done
  echo "✅ Đã giải phóng toàn bộ tài nguyên GPU/RAM."
}

status_all() {
  echo "════════════════════════════════════════════════════════════════"
  echo "📊 TRẠNG THÁI CÁC CỔNG AI PLATFORM"
  echo "════════════════════════════════════════════════════════════════"

  # Gateway (Docker / Local)
  if is_port_listening 8000; then
    echo "  🟢 [ACTIVE]   Port 8000: Gateway Control-Plane (OpenAI Export)"
  else
    echo "  🔴 [INACTIVE] Port 8000: Gateway Control-Plane"
  fi

  for item in "${SERVICES[@]}"; do
    IFS=":" read -r port name sdir app_cmd <<< "$item"
    if is_port_listening "$port"; then
      echo "  🟢 [ACTIVE]   Port $port: $name"
    else
      echo "  🔴 [INACTIVE] Port $port: $name"
    fi
  done
  echo "════════════════════════════════════════════════════════════════"
}

case "$1" in
  start)
    start_all
    ;;
  stop)
    stop_all
    ;;
  status)
    status_all
    ;;
  restart)
    stop_all
    sleep 2
    start_all
    ;;
  *)
    echo "Sử dụng: $0 {start|stop|status|restart}"
    exit 1
    ;;
esac
