#!/usr/bin/env bash
# Generate Internal Root CA and TLS Certificate for *.cyber.internal and 172.16.20.2
set -euo pipefail

CERT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/certs"
mkdir -p "$CERT_DIR"
cd "$CERT_DIR"

echo "=== 1. Khởi tạo Root CA cho cyber.internal ==="
openssl req -x509 -new -nodes -newkey rsa:2048 -days 3650 \
  -keyout cyber_ca.key -out cyber_ca.crt \
  -subj "/C=VN/ST=Hanoi/O=Cyber Company/OU=Security/CN=Cyber Internal Root CA"

echo "=== 2. Tạo Private Key cho Server ==="
openssl genrsa -out cyber_internal.key 2048

echo "=== 3. Tạo Certificate Signing Request (CSR) ==="
openssl req -new -key cyber_internal.key -out cyber_internal.csr \
  -subj "/C=VN/ST=Hanoi/O=Cyber Company/OU=AI Platform/CN=rag.cyber.internal"

echo "=== 4. Tạo file cấu hình SAN (Subject Alternative Names) ==="
cat << 'EOF' > san.ext
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment
subjectAltName = @alt_names

[alt_names]
DNS.1 = *.cyber.internal
DNS.2 = aip.cyber.internal
DNS.3 = api.cyber.internal
IP.1 = 172.16.20.2
EOF

echo "=== 5. Ký chứng chỉ SSL bằng Root CA ==="
openssl x509 -req -in cyber_internal.csr -CA cyber_ca.crt -CAkey cyber_ca.key \
  -CAcreateserial -out cyber_internal.crt -days 1825 -sha256 -extfile san.ext

rm -f cyber_internal.csr san.ext cyber_ca.srl

echo "✔ Chứng chỉ đã tạo thành công trong $CERT_DIR:"
ls -la "$CERT_DIR"
