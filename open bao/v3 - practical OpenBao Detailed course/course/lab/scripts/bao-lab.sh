#!/usr/bin/env bash
# =============================================================================
# bao-lab.sh - shared helpers for the Meridian AI OpenBao course
# =============================================================================
# Every function here was executed against a live OpenBao v2.7.1 server
# before being written down. The flag ordering matters:
#   bao write [FLAGS] PATH KEY=VALUE
#   bao <cmd> [FLAGS] [POSITIONAL]
# Get it wrong and you get:
#   "Command flags must be provided before positional arguments"
# =============================================================================
set -euo pipefail

# --- Connection settings -----------------------------------------------------
export BAO_ADDR="${BAO_ADDR:-http://127.0.0.1:8200}"
export BAO_FORMAT="${BAO_FORMAT:-json}"

LAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SECRETS_DIR="${LAB_DIR}/secrets"
CONTAINER="${BAO_CONTAINER:-meridian-openbao}"

# --- How to reach the bao CLI -----------------------------------------------
# Three supported ways, in priority order:
#   1. $BAO_BIN           - you point at a local binary yourself
#   2. $LAB_DIR/bin/bao   - a binary dropped into lab/bin/ (no Docker needed)
#   3. docker exec        - the normal course path
#
# Option 2 exists so the whole course can be run WITHOUT Docker: download the
# OpenBao binary, drop it in lab/bin/, and everything else is identical.
if [[ -n "${BAO_BIN:-}" ]]; then
  :
elif command -v bao >/dev/null 2>&1; then
  BAO_BIN="bao"
elif [[ -x "${LAB_DIR}/bin/bao" ]]; then
  BAO_BIN="${LAB_DIR}/bin/bao"
else
  BAO_BIN="docker exec -i ${CONTAINER} bao"
fi
export BAO_BIN

# Run bao inside the lab container (always works, even without a local install)
bao_lab() {
  if [[ -n "${BAO_BIN:-}" && "$BAO_BIN" != docker* ]]; then
    "$BAO_BIN" "$@"
  else
    docker exec -i -e BAO_ADDR -e BAO_TOKEN "${CONTAINER}" bao "$@"
  fi
}

c_head() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
c_ok()  { printf '\033[1;32m  ✓ %s\033[0m\n' "$*"; }
c_warn(){ printf '\033[1;33m  ! %s\033[0m\n' "$*"; }
c_err() { printf '\033[1;31m  ✗ %s\033[0m\n' "$*" >&2; }

# --- Secret store for lab artifacts -----------------------------------------
# Unseal keys and tokens are written here with 0600 perms. In a real org these
# live in a password manager or an HSM ceremony - never on the app box.
save_secret() {
  local name="$1" value="$2"
  mkdir -p "${SECRETS_DIR}"
  umask 077
  printf '%s' "$value" > "${SECRETS_DIR}/${name}"
  printf '%s' "$value" | tr -d '\n' | sha256sum | cut -c1-16 > "${SECRETS_DIR}/${name}.sha256"
}

load_secret() {
  local name="$1"
  [[ -f "${SECRETS_DIR}/${name}" ]] || { c_err "Missing ${SECRETS_DIR}/${name}"; return 1; }
  cat "${SECRETS_DIR}/${name}"
}

# --- Token helpers -----------------------------------------------------------
# Set BAO_TOKEN from the saved lab token
use_lab_token() {
  export BAO_TOKEN="$(load_secret root-token)"
  export BAO_TOKEN
}

# Extract a scalar from bao's JSON output
jget() { python3 -c "import sys,json;d=json.load(sys.stdin);print($1)"; }

# --- Lease / token helpers ---------------------------------------------------
renew_token() {
  local increment="${1:-30m}"
  bao_lab write auth/token/renew-self increment="$increment" >/dev/null
  c_ok "Token renewed by ${increment}"
}

revoke_token_prefix() {
  local prefix="$1"
  bao_lab write sys/leases/revoke-prefix prefix="$prefix" >/dev/null
  c_ok "Revoked all leases under prefix: ${prefix}"
}
