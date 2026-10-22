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
for i in $(seq 1 30); do
  if bao_lab status >/dev/null 2>&1; then
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
  c_warn "Already initialized - skipping init."
  c_warn "If the server is sealed, run: ./scripts/unseal-lab.sh"
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

# Save each share separately, so a single leaked file is not a full compromise
i=1
for key in $(echo "$INIT_JSON" | jget "d['unseal_keys_b64']"); do
  save_secret "unseal-key-${i}" "$key"
  i=$((i + 1))
done

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

if bao_lab status -format=json | jget "d.get('sealed')" | grep -q False; then
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
