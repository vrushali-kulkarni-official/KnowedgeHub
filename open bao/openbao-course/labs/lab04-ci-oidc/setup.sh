#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  setup.sh — one-time configuration for Lab 04
#
#    1. Init + unseal OpenBao
#    2. Enable the KV engine and the CI policy
#    3. Enable the `jwt` auth method for GitHub Actions
#    4. Create the role (bound to repo + ref + workflow)
#    5. Store the app's secrets
#
#  Run:  ./setup.sh
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

export BAO_ADDR="${BAO_ADDR:-http://127.0.0.1:8200}"
JWKS_URL="${JWKS_URL:-http://127.0.0.1:8099/jwks.json}"
REPO="${REPO:-your-org/your-repo}"
REF="${REF:-refs/heads/main}"
WORKFLOW="${WORKFLOW:-deploy.yml}"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

command -v bao >/dev/null || { echo "bao CLI not found — see labs/README.md"; exit 1; }
command -v jq  >/dev/null || { echo "jq not found"; exit 1; }

# ⚠️ `bao status` EXITS NON-ZERO (2) when the server is sealed or
#    uninitialised. Under `set -euo pipefail` a naive
#      V=$(bao status -format=json | jq -r .sealed)
#    therefore FAILS, and `|| echo true` appends a second line, giving
#    V="true\ntrue" — which never equals "true".
#    Always capture the JSON first, then parse it.
#
# ⚠️ ALSO: jq's `//` operator treats `false` as "empty", so
#      jq -r '.sealed // "true"'      →  "true"   (WRONG when unsealed!)
#    Use an explicit if/else instead.
seal_state() {
  local raw s
  raw=$(bao status -format=json 2>/dev/null || true)
  s=$(printf '%s' "$raw" \
        | jq -r 'if has("sealed") then (.sealed | tostring) else "true" end' 2>/dev/null || true)
  [ -z "$s" ] && s=true
  printf '%s' "$s"
}

# ─────────────────────────────────────────────────────────────────
say "1/5  Initialise + unseal"
if ! bao operator init -status >/dev/null 2>&1; then   # exit 2 = not initialised
  echo "    Initialising (5 shares / 3 threshold)..."
  bao operator init -key-shares=5 -key-threshold=3 -format=json > init.json
  python3 - <<'PY'
import json
d = json.load(open("init.json"))
open("unseal-keys.txt", "w").write("\n".join(d["unseal_keys_b64"]) + "\n")
open(".root-token", "w").write(d["root_token"])
print("    saved 5 unseal keys -> unseal-keys.txt   (treat like a password)")
print("    saved the root token -> .root-token        (git-ignored)")
PY
else
  echo "    Already initialised."
fi

# Use the saved root token (or whatever BAO_TOKEN is already set to)
if [ -z "${BAO_TOKEN:-}" ] && [ -f .root-token ]; then
  BAO_TOKEN=$(cat .root-token)
  export BAO_TOKEN
fi

if [ -z "${BAO_TOKEN:-}" ]; then
  echo
  echo "    This cluster is already initialised but no root token is available."
  echo "    Set one and re-run:"
  echo "      export BAO_TOKEN='<root token>'"
  echo "    ...or wipe the data and start fresh:"
  echo "      docker compose down -v && rm -rf data && ./setup.sh"
  exit 1
fi

# Unseal if we still have 3 keys on file
if [ -f unseal-keys.txt ]; then
  SEALED=$(seal_state)
  if [ "$SEALED" = "true" ]; then
    echo "    Unsealing with 3 of 5 keys..."
    head -3 unseal-keys.txt | while read -r key; do
      [ -n "$key" ] && bao operator unseal "$key" >/dev/null 2>&1 || true
    done
  fi
fi

if [ "$(seal_state)" = "true" ]; then
  echo
  echo "    OpenBao is still SEALED."
  echo "    Unseal it with 3 keys, then re-run this script:"
  echo "      bao operator unseal '<key1>' && bao operator unseal '<key2>' && bao operator unseal '<key3>'"
  exit 1
fi
echo "    unsealed ✓"

# ─────────────────────────────────────────────────────────────────
say "2/5  Secrets engine + the app's secrets"
bao secrets enable -path=secret kv-v2 2>/dev/null || echo "    secret/ already enabled"

# Enabling kv-v2 on a fresh mount performs a one-time storage-format
# upgrade, during which the mount is briefly unavailable. Retry.
for i in 1 2 3 4 5 6; do
  if bao kv put -mount=secret myapp \
        db_host=postgres \
        db_port=5432 \
        llm_api_key='sk-lab-not-a-real-key' \
        deploy_token='dep-lab-not-a-real-token' >/dev/null 2>&1; then
    echo "    wrote secret/myapp"
    break
  fi
  echo "    (mount busy — upgrading storage format, retry $i/6)"
  sleep 2
done

# ─────────────────────────────────────────────────────────────────
say "3/5  The CI policy (least privilege — no list, no wildcards)"
bao policy write ci-deploy - <<'EOF'
# CI may read the app's config...
path "secret/data/myapp" {
  capabilities = ["read"]
}
path "secret/metadata/myapp" {
  capabilities = ["read", "list"]
}

# ...and update the deploy config it owns.
path "secret/data/myapp/deploy" {
  capabilities = ["create", "read", "update", "patch"]
}
path "secret/metadata/myapp/deploy" {
  capabilities = ["read", "list"]
}
EOF
echo "    ci-deploy"

# ─────────────────────────────────────────────────────────────────
say "4/5  The GitHub Actions auth method"
bao auth enable -path=github-actions jwt 2>/dev/null || echo "    github-actions/ already enabled"

# The jwks_url is a LITERAL url (it keeps /.well-known/jwks).
# In production against real GitHub you would use:
#   oidc_discovery_url = "https://token.actions.githubusercontent.com"
bao write auth/github-actions/config - <<EOF
{
  "jwks_url": "$JWKS_URL",
  "bound_issuer": "https://token.actions.githubusercontent.com",
  "default_role": "github"
}
EOF
echo "    auth/github-actions/config"

bao write auth/github-actions/role/github - <<EOF
{
  "role_type": "jwt",
  "user_claim": "actor",
  "bound_audiences": ["openbao"],
  "bound_claims": {
    "repository": "$REPO",
    "ref": "$REF",
    "workflow": "$WORKFLOW"
  },
  "claim_mappings": {
    "actor": "actor",
    "repository": "repository",
    "ref": "ref",
    "workflow": "workflow",
    "environment": "environment",
    "run_id": "run_id"
  },
  "token_policies": ["ci-deploy"],
  "token_ttl": "15m",
  "token_max_ttl": "30m"
}
EOF
echo "    auth/github-actions/role/github (bound to $REPO @ $REF / $WORKFLOW)"

# ─────────────────────────────────────────────────────────────────
say "5/5  Verify"
bao status
echo
echo "  auth mount status: $(bao read -format=json auth/github-actions/config | python3 -c 'import json,sys;print(json.load(sys.stdin)["data"].get("status"))')"
echo
cat <<EOF

──────────────────────────────────────────────────────────────
  READY. Now run:   ./simulate-ci.sh
  It runs the exact steps the GitHub Action runs, then shows
  you the audit log entry proving who read what.
──────────────────────────────────────────────────────────────
EOF
