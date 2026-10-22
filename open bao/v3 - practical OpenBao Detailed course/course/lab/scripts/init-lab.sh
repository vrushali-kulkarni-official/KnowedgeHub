#!/usr/bin/env bash
# =============================================================================
# init-lab.sh - one-time OpenBao initialization for the course lab
# =============================================================================
# Run this ONCE after `docker compose up -d openbao`.
#
# What it does:
#   1. Waits for the server to answer
#   2. Runs `bao operator init` (3 shares, threshold 2)
#   3. Unseals with 2 of the 3 shares
#   4. Saves the root token + unseal keys to lab/secrets/ (chmod 600)
#
# WHY 3 SHARES / THRESHOLD 2:
#   Shamir's Secret Sharing splits the root key into N shares, any K of which
#   reconstruct it. 2-of-3 means:
#     - You can lose 1 share and still unseal.
#     - No single person can unseal alone (no single point of failure).
#   For production, use 5-of-7 or 7-of-11 across different people/sites.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/bao-lab.sh"

c_head "Meridian AI OpenBao Lab - Initialization"

# --- 1. Wait for the server --------------------------------------------------
c_head "1/4  Waiting for OpenBao to accept requests"

# Diagnose the two most likely failures BEFORE the timeout, so the learner
# gets an actionable message instead of "did not come up in 30s".
if ! command -v docker >/dev/null 2>&1 && [[ ! -x "${LAB_DIR}/bin/bao" ]] && ! command -v bao >/dev/null 2>&1; then
  c_err "Neither Docker nor a local bao binary was found."
  c_err ""
  c_err "  Fix it one of two ways:"
  c_err "    A) Install Docker and run:  docker compose up -d openbao"
  c_err "    B) Skip Docker entirely: download the OpenBao 2.7.1 binary and put it"
  c_err "       at lab/bin/bao, then run:  lab/bin/bao server -config=lab/config"
  exit 1
fi

if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "${BAO_CONTAINER:-meridian-openbao}" \
   && [[ ! -x "${LAB_DIR}/bin/bao" ]] && ! command -v bao >/dev/null 2>&1; then
  c_err "The OpenBao container '${BAO_CONTAINER:-meridian-openbao}' is not running."
  c_err "  Start it first:  docker compose up -d openbao"
  c_err "  (then:  docker compose logs -f openbao  to watch it start)"
  exit 1
fi

for i in $(seq 1 30); do
  # NOTE: `bao status` exits 2 on an UNINITIALIZED server - that is a normal
  # state, not a failure. So do NOT test the exit code. Test for the JSON
  # payload instead: if the server answers at all, it is up.
  # NOTE: two traps here.
  #  1. `bao status` exits 2 on an UNINITIALIZED server - a normal state, not
  #     a failure. So never test its exit code.
  #  2. `set -o pipefail` would make that exit 2 poison the whole pipeline,
  #     so the match would be ignored. Capture first, then match.
  _status_json="$(bao_lab status -format=json 2>/dev/null || true)"
  if [[ "$_status_json" == *'"initialized"'* ]]; then
    c_ok "Server is responding at ${BAO_ADDR}"
    break
  fi
  [[ $i -eq 30 ]] && { c_err "Server did not come up in 30s"; exit 1; }
  sleep 2
done

# --- 2. Check if already initialized -----------------------------------------
c_head "2/4  Checking initialization state"
STATUS="$(bao_lab status -format=json 2>/dev/null || true)"
INITIALIZED="$(echo "$STATUS" | jget "d.get('initialized')" 2>/dev/null || echo False)"

if [[ "$INITIALIZED" == "True" ]]; then
  if [[ -f "${SECRETS_DIR}/root-token" ]]; then
    c_warn "Already initialized - skipping init."
    c_warn "If the server is sealed, run: ./scripts/unseal-lab.sh"
  else
    c_err "This server is ALREADY INITIALIZED, but lab/secrets/root-token is missing."
    c_err ""
    c_err "  The root token and the unseal keys are printed ONCE, at init, and"
    c_err "  are not recoverable from the server. You have three options:"
    c_err ""
    c_err "    A) You still have the unseal keys -> mint a new root token:"
    c_err "         ./scripts/break-glass.sh"
    c_err "    B) You have the original init.json -> recover the keys from it:"
    c_err "         ls lab/secrets/init.json"
    c_err "    C) You have NEITHER -> the store must be rebuilt. This destroys"
    c_err "       all data in it:"
    c_err "         docker compose down -v && docker compose up -d openbao"
    c_err "         ./scripts/init-lab.sh"
  fi
  exit 0
fi

# --- 3. Initialize -----------------------------------------------------------
# 3 shares, threshold 2. -format=json gives us machine-readable keys.
# NOTE: -recovery-shares / -recovery-threshold DO NOT WORK in Shamir mode.
# Recovery keys are an auto-unseal (KMS/Transit) feature only. In Shamir mode
# the unseal keys ARE your recovery mechanism.
c_head "3/4  Initializing (3 shares, threshold 2)"
INIT_JSON="$(bao_lab operator init -key-shares=3 -key-threshold=2 -format=json)"

echo "$INIT_JSON" > "${SECRETS_DIR}/init.json"
chmod 600 "${SECRETS_DIR}/init.json"

# Save each share separately, so a single leaked file is not a full compromise.
# NOTE: print one key per line. Printing the list directly gives Python's repr
# (['key1', 'key2']) and the quotes/brackets end up inside the key, which
# then fails to unseal with "'key' must be a valid hex or base64 string".
i=1
while IFS= read -r key; do
  [ -n "$key" ] || continue
  save_secret "unseal-key-${i}" "$key"
  i=$((i + 1))
done < <(printf '%s' "$INIT_JSON" | python3 -c "
import sys, json
for k in json.load(sys.stdin)['unseal_keys_b64']:
    print(k)
")

ROOT_TOKEN="$(echo "$INIT_JSON" | jget "d['root_token']")"
save_secret "root-token" "$ROOT_TOKEN"

c_ok "Generated 3 unseal key shares (threshold 2)"
c_ok "Root token saved to lab/secrets/root-token (chmod 600)"
c_ok "Initial keys saved to lab/secrets/init.json"
c_warn ""
c_warn "  Store the unseal keys in your password manager NOW."
c_warn "  init.json contains everything - treat it as a critical secret."

# --- 4. Unseal ---------------------------------------------------------------
c_head "4/4  Unsealing (2 of 3 shares)"
K1="$(load_secret unseal-key-1)"
K2="$(load_secret unseal-key-2)"

bao_lab operator unseal "$K1" >/dev/null
c_ok "Unseal share 1 submitted"
bao_lab operator unseal "$K2" >/dev/null
c_ok "Unseal share 2 submitted"

if [[ "$(bao_lab status -format=json 2>/dev/null | jget "d.get('sealed')" || true)" == "False" ]]; then
  c_ok "OpenBao is UNSEALED and ready"
else
  c_err "Still sealed - something went wrong"; exit 1
fi

cat <<'EOF'

──────────────────────────────────────────────────────────────────────────────
 NEXT STEPS

  1. Authenticate:
       source lab/scripts/bao-lab.sh
       use_lab_token

  2. Open the GUI:
       http://127.0.0.1:8200/ui
     (log in with the root token from lab/secrets/root-token)

  3. Continue the course:
       Module 01 → modules/01-foundations/README.md
──────────────────────────────────────────────────────────────────────────────
EOF
