#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  Step 3 — read the secret with the OpenBao token.
#
#  The secret is written to a FILE, never echoed. Printing it would
#  put it in the CI log, where it stays forever.
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

BAO_ADDR="${BAO_ADDR:-http://127.0.0.1:8200}"
BAO_TOKEN="${1:?usage: 03-fetch-secrets.sh <bao-token>}"
OUT="${SECRET_OUT:-./app-config.json}"
MOUNT="${SECRET_MOUNT:-secret}"
KEY="${SECRET_KEY:-myapp}"

curl -sS \
  -H "X-Vault-Token: $BAO_TOKEN" \
  "$BAO_ADDR/v1/$MOUNT/data/$KEY" > "$OUT"

if jq -e '.errors' "$OUT" >/dev/null 2>&1; then
  echo "::error::$(jq -r '.errors | join(", ")' "$OUT")" >&2
  exit 1
fi

echo "[ci] secret written to $OUT (values NOT printed)" >&2
echo "[ci] keys present: $(jq -r '.data.data | keys | join(", ")' "$OUT")" >&2
