#!/usr/bin/env bash
# Generate Python gRPC and Protobuf code from .proto definitions
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROTO_DIR="${SCRIPT_DIR}/proto"
OUT_DIR="${SCRIPT_DIR}/generated"

mkdir -p "${OUT_DIR}"

echo "Compiling AIP Protobuf definitions from ${PROTO_DIR} to ${OUT_DIR}..."

if command -v uv &> /dev/null; then
    uv run python -m grpc_tools.protoc \
        -I="${PROTO_DIR}" \
        --python_out="${OUT_DIR}" \
        --grpc_python_out="${OUT_DIR}" \
        "${PROTO_DIR}"/*.proto 2>/dev/null || echo "grpc_tools not installed yet. Run: uv pip install grpcio-tools"
else
    python3 -m grpc_tools.protoc \
        -I="${PROTO_DIR}" \
        --python_out="${OUT_DIR}" \
        --grpc_python_out="${OUT_DIR}" \
        "${PROTO_DIR}"/*.proto 2>/dev/null || echo "grpc_tools not installed yet. Run: pip install grpcio-tools"
fi

touch "${OUT_DIR}/__init__.py"
echo "Protobuf generation completed successfully."
