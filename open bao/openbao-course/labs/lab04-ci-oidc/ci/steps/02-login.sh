#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  Step 2 — exchange the OIDC token for an OpenBao token.
#
#  The `audience` sent to the IdP MUST match OpenBao's
#  `bound_audiences`, or the login is rejected.
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

BAO_ADDR="${BAO_ADDR:-http://127.0.0.1:8200}"
BAO_ROLE="${BAO_ROLE:-github}"
OIDC_TOKEN="${1:?usage: 02-login.sh <oidc-token>}"

LOGIN=$(curl -sS \
  -H "X-Vault-Request: true" \
  -H "Content-Type: application/json" \
  -d "{\"role\":\"$BAO_ROLE\",\"jwt\":\"$OIDC_TOKEN\"}" \
  "$BAO_ADDR/v1/auth/github-actions/login")

# Surface a useful error instead of a jq stack trace
if echo "$LOGIN" | jq -e '.errors' >/dev/null 2>&1; then
  echo "::error::OpenBao login failed: $(echo "$LOGIN" | jq -r '.errors | join(", ")')" >&2
  exit 1
fi

BAO_TOKEN=$(echo "$LOGIN" | jq -r .auth.client_token)
[ -n "$BAO_TOKEN" ] && [ "$BAO_TOKEN" != "null" ] || {
  echo "::error::no token in the login response" >&2; exit 1; }

echo "[ci] OpenBao token acquired" >&2
echo "[ci]   ttl:      $(echo "$LOGIN" | jq -r .auth.lease_duration)s" >&2
echo "[ci]   policies: $(echo "$LOGIN" | jq -r '.auth.policies | join(", ")')" >&2
echo "[ci]   accessor: $(echo "$LOGIN" | jq -r .auth.accessor)" >&2

echo "::add-mask::$BAO_TOKEN" >&2

if [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "token=$BAO_TOKEN" >> "$GITHUB_OUTPUT"
fi
if [ -n "${STEP_OUT:-}" ]; then
  echo "$BAO_TOKEN" > "$STEP_OUT"
fi

printf '%s' "$BAO_TOKEN"
