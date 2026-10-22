#!/usr/bin/env bash
# =============================================================================
# unseal-lab.sh - unseal the lab server after a restart
# =============================================================================
# WHY YOU NEED THIS:
#   A production-shaped OpenBao server comes back SEALED after every restart.
#   The seal is what makes the data unreadable to anyone who steals the disk.
#   This is not a bug - it is the entire point of the design.
#
#   The only ways to unseal:
#     a) Shamir:  any K of N unseal key shares
#     b) Auto-unseal (Transit/KMS/HSM): the external key service unseals it
#
#   The lab uses (a). Module 04 shows how (b) is configured for production.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/bao-lab.sh"

c_head "Unsealing the lab OpenBao server"

STATUS="$(bao_lab status -format=json 2>/dev/null || true)"
SEALED="$(echo "$STATUS" | jget "d.get('sealed')" 2>/dev/null || echo True)"
THRESHOLD="$(echo "$STATUS" | jget "d.get('threshold')" 2>/dev/null || echo 2)"
SHARES="$(echo "$STATUS" | jget "d.get('total_shares')" 2>/dev/null || echo 3)"

if [[ "$SEALED" == "False" ]]; then
  c_ok "Already unsealed - nothing to do."
  exit 0
fi

c_warn "Server is sealed. Threshold is ${THRESHOLD} of ${SHARES} shares."

# Submit shares until the threshold is met
SUBMITTED=0
for i in $(seq 1 "$SHARES"); do
  [[ $SUBMITTED -ge "$THRESHOLD" ]] && break
  KEY_FILE="${SECRETS_DIR}/unseal-key-${i}"
  [[ -f "$KEY_FILE" ]] || continue
  KEY="$(cat "$KEY_FILE")"
  bao_lab operator unseal "$KEY" >/dev/null
  SUBMITTED=$((SUBMITTED + 1))
  c_ok "Submitted unseal share ${i}"
done

if bao_lab status -format=json | jget "d.get('sealed')" | grep -q False; then
  c_ok "OpenBao is UNSEALED"
else
  c_err "Could not unseal. Not enough shares available?"
  exit 1
fi
