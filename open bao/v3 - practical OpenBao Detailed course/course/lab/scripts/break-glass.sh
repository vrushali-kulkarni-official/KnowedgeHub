#!/usr/bin/env bash
# =============================================================================
# break-glass.sh - mint a new root token without rotating the root key
# =============================================================================
# Use this when the root token is compromised, suspected leaked, or has
# simply been lost. It uses your unseal-key quorum to authorize a NEW root
# token. It does NOT rotate the root key, so your existing unseal shares
# stay valid.
#
# Usage:
#   export BAO_ADDR=http://127.0.0.1:8200
#   export BAO_TOKEN=$(cat lab/secrets/root-token)   # a sudo-capable token
#   export UNSEAL_KEY_1="<share 1>"
#   export UNSEAL_KEY_2="<share 2>"
#   ./lab/scripts/break-glass.sh
#
# Then revoke the old token:
#   bao token revoke <old-root-token>
# =============================================================================
set -euo pipefail

UNSEAL_KEY_1="${UNSEAL_KEY_1:?set UNSEAL_KEY_1}"
UNSEAL_KEY_2="${UNSEAL_KEY_2:?set UNSEAL_KEY_2}"

# 1. One-time password. The CLI prints ONLY the bare 26-char string.
OTP=$(bao operator generate-root -generate-otp | tail -1)
echo "[1/5] OTP captured (${#OTP} chars)"

# 2. Start the attempt. The nonce comes back here and is required from now on.
INIT_OUT=$(bao operator generate-root -init -otp="$OTP")
NONCE=$(printf '%s\n' "$INIT_OUT" | awk '/^Nonce/{print $2}')
if [ -z "$NONCE" ]; then
  echo "could not read the nonce; aborting" >&2
  exit 1
fi
echo "[2/5] attempt started, nonce=$NONCE"

# 3. Submit each share. The nonce MUST be passed on every call.
bao operator generate-root -nonce="$NONCE" -otp="$OTP" "$UNSEAL_KEY_1" >/dev/null
echo "[3/5] share 1 of 2 accepted"

OUT=$(bao operator generate-root -nonce="$NONCE" -otp="$OTP" "$UNSEAL_KEY_2")
echo "[4/5] share 2 of 2 accepted"

# 4. The output field is "Encoded Token" (two words), field number 3.
ENC=$(printf '%s\n' "$OUT" | awk '/^Encoded Token/{print $3}')
if [ -z "$ENC" ]; then
  echo "could not read the encoded token; aborting" >&2
  exit 1
fi

# 5. Decode with the SAME OTP.
NEW_TOKEN=$(bao operator generate-root -decode="$ENC" -otp="$OTP" | tr -d '\r' | tail -1)
echo "[5/5] new root token minted"

echo
echo "NEW ROOT TOKEN: ${NEW_TOKEN}"
