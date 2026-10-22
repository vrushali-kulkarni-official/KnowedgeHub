#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  simulate-ci.sh — run the CI flow locally, exactly as GitHub would.
#
#  This executes the SAME step scripts that the real GitHub Action
#  uses, so if it works here it works in GitHub. The only difference
#  is where the OIDC token comes from:
#
#    GitHub  → ACTIONS_ID_TOKEN_REQUEST_URL (signed by GitHub)
#    Lab     → the stand-in IdP on :8099 (same claims, local key)
#
#  Run:  ./simulate-ci.sh
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

cd "$(dirname "$0")"

export BAO_ADDR="${BAO_ADDR:-http://127.0.0.1:8200}"
export BAO_AUDIENCE="${BAO_AUDIENCE:-openbao}"
export BAO_ROLE="${BAO_ROLE:-github}"
export SECRET_OUT="${SECRET_OUT:-./app-config.json}"
export AUDIT_LOG="${AUDIT_LOG:-./logs/audit.log}"
export STEP_OUT=""

banner() { printf '\n\033[1;35m▸ %s\033[0m\n' "$*"; }

mkdir -p .tmp logs

banner "Step 1/4 — Get an OIDC token"
OIDC_TOKEN=$(./ci/steps/01-get-oidc-token.sh)
echo "$OIDC_TOKEN" > .tmp/oidc_token

banner "Step 2/4 — Exchange it for an OpenBao token"
BAO_TOKEN=$(./ci/steps/02-login.sh "$OIDC_TOKEN")
echo "$BAO_TOKEN" > .tmp/bao_token

banner "Step 3/4 — Read the secret"
./ci/steps/03-fetch-secrets.sh "$BAO_TOKEN"

banner "Step 4/4 — Check the audit trail"
sleep 1
./ci/steps/04-audit-check.sh

# ─────────────────────────────────────────────────────────────────
#  Negative test: prove the bounds actually bind.
#  A token minted for a DIFFERENT repo / branch must be rejected.
# ─────────────────────────────────────────────────────────────────
banner "Negative test — a token from the wrong repo must be refused"
set +e
BAD=$(curl -sS -G "http://127.0.0.1:8099/token" \
        --data-urlencode "audience=openbao" \
        --data-urlencode "repository=someone-else/their-repo" \
        --data-urlencode "ref=refs/heads/attacker-branch" \
        --data-urlencode "workflow=deploy.yml" | jq -r .value)
ERR=$(curl -sS -H "Content-Type: application/json" \
        -d "{\"role\":\"github\",\"jwt\":\"$BAD\"}" \
        "$BAO_ADDR/v1/auth/github-actions/login")
if echo "$ERR" | jq -e '.errors' >/dev/null 2>&1; then
  echo "  ✅ correctly refused:"
  echo "     $(echo "$ERR" | jq -r '.errors | join(", ")')"
else
  echo "  ❌ ACCEPTED A TOKEN IT SHOULD HAVE REJECTED — fix your bound_claims!"
fi
set -e

cat <<'EOF'

──────────────────────────────────────────────────────────────
  What just happened:

    1. A short-lived OIDC token was minted (5 min lifetime).
    2. OpenBao verified its signature against the JWKS.
    3. OpenBao checked bound_audiences + bound_claims
       (repo + ref + workflow) before issuing anything.
    4. A 15-minute OpenBao token was issued with the ci-deploy policy.
    5. The secret was read and written to app-config.json — never printed.
    6. The audit log recorded the read, with the claim-derived identity.

  No long-lived secret exists anywhere in this flow.

──────────────────────────────────────────────────────────────
EOF
