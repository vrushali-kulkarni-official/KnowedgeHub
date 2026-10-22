#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  Step 1 — get an OIDC token.
#
#  In GitHub Actions, the token comes from the runner's
#  ACTIONS_ID_TOKEN_REQUEST_URL (available only when the job has
#  `permissions: id-token: write`).
#
#  In the lab, it comes from the stand-in IdP, which mints a token
#  with the same claims GitHub puts in one.
#
#  Output: the token, on stdout and in $GITHUB_OUTPUT (or $STEP_OUT).
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

AUDIENCE="${BAO_AUDIENCE:-openbao}"
REPOSITORY="${GITHUB_REPOSITORY:-your-org/your-repo}"
REF="${GITHUB_REF:-refs/heads/main}"
WORKFLOW="${GITHUB_WORKFLOW:-deploy.yml}"
ENVIRONMENT="${GITHUB_ENVIRONMENT:-production}"
ACTOR="${GITHUB_ACTOR:-octocat}"
IDP_URL="${IDP_TOKEN_URL:-http://127.0.0.1:8099/token}"

# ── Real GitHub path ────────────────────────────────────────────
if [ -n "${ACTIONS_ID_TOKEN_REQUEST_URL:-}" ]; then
  echo "[ci] requesting OIDC token from GitHub (audience=$AUDIENCE)" >&2
  OIDC_TOKEN=$(curl -sS -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_URL" \
    "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=$AUDIENCE" | jq -r .value)
else
  # ── Lab path: the stand-in IdP ────────────────────────────────
  echo "[ci] requesting OIDC token from the lab IdP (audience=$AUDIENCE)" >&2
  OIDC_TOKEN=$(curl -sS -G "$IDP_URL" \
    --data-urlencode "audience=$AUDIENCE" \
    --data-urlencode "repository=$REPOSITORY" \
    --data-urlencode "ref=$REF" \
    --data-urlencode "workflow=$WORKFLOW" \
    --data-urlencode "environment=$ENVIRONMENT" \
    --data-urlencode "actor=$ACTOR" | jq -r .value)
fi

if [ -z "$OIDC_TOKEN" ] || [ "$OIDC_TOKEN" = "null" ]; then
  echo "::error::could not obtain an OIDC token (is 'id-token: write' set?)" >&2
  exit 1
fi

echo "[ci] OIDC token acquired (${#OIDC_TOKEN} chars)" >&2

# Never let it hit a log
echo "::add-mask::$OIDC_TOKEN" >&2

if [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "oidc_token=$OIDC_TOKEN" >> "$GITHUB_OUTPUT"
fi
if [ -n "${STEP_OUT:-}" ]; then
  echo "$OIDC_TOKEN" > "$STEP_OUT"
fi

printf '%s' "$OIDC_TOKEN"
