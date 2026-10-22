#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  gen-certs.sh — create a local CA + server certificate
#
#  Usage:  ./gen-certs.sh [output-dir]
#  Default output dir: ./certs
#
#  Produces:
#    ca.crt        — CA certificate (trust anchor)
#    ca.key        — CA private key (keep offline!)
#    openbao.crt   — server certificate (chain: leaf only, see note)
#    openbao.key   — server private key
#
#  NOTE: for the intermediate-CA model described in the course,
#  replace this script with the OpenBao PKI flow (Level 4, §4.3).
#  This script is the "good enough for a lab" version.
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

OUT="${1:-./certs}"
mkdir -p "$OUT"
cd "$OUT"

echo "==> Generating CA"
openssl genrsa -out ca.key 4096
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 \
  -subj "/CN=openbao-lab-ca" -out ca.crt

echo "==> Generating server key + CSR"
openssl genrsa -out openbao.key 4096
openssl req -new -key openbao.key -subj "/CN=openbao" -out openbao.csr

cat > san.cnf <<'EOF'
[req]
distinguished_name = req_distinguished_name
req_extensions     = v3_req
[req_distinguished_name]
[v3_req]
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names
[alt_names]
DNS.1 = openbao
DNS.2 = localhost
DNS.3 = openbao.local
IP.1  = 127.0.0.1
EOF

echo "==> Signing server certificate"
openssl x509 -req -in openbao.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out openbao.crt -days 825 -sha256 -extfile san.cnf -extensions v3_req

chmod 600 ca.key openbao.key
chmod 644 ca.crt openbao.crt
rm -f openbao.csr san.cnf

echo
echo "Done. Certificates in $OUT"
echo "  Trust anchor for clients: $OUT/ca.crt"
echo "  CA private key            : $OUT/ca.key  (keep offline!)"
