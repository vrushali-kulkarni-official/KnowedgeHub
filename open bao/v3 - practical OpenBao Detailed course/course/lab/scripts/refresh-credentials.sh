#!/usr/bin/env bash
# =============================================================================
# refresh-credentials.sh - mint a fresh AppRole secret_id
#
# WHY THIS EXISTS
#   The ai-harness-service role deliberately has secret_id_ttl=1h. That is the
#   point of AppRole: the credential a workload uses to fetch a token is
#   short-lived and rotated by whoever delivers it. But it means the copy you
#   saved when you ran setup-platform.sh goes stale.
#
#   When it does, the application fails like this:
#
#     Error writing data to auth/approle/login: Error making API request.
#     URL: PUT http://127.0.0.1:8200/v1/auth/approle/login
#     Code: 403. Errors:
#     * permission denied
#
#   or, if the secret_id has expired outright:
#
#     Code: 400. Errors:
#     * invalid role or secret ID
#
#   Both mean "get a new secret_id", not "your policies are wrong".
#
# WHAT IT DOES
#   Generates one new secret_id for the AI harness role and rewrites
#   lab/secrets/ai-harness-secret-id (mode 600). The role_id does not change:
#   role_id identifies the ROLE and is stable for the life of the role.
#
#   It touches nothing else - no secrets are rewritten, no policies change.
#   The old secret_id stays valid until its own TTL expires.
#
# USAGE
#   ./scripts/refresh-credentials.sh
#
#   Then point your app at the new value:
#     export BAO_SECRET_ID=$(cat lab/secrets/ai-harness-secret-id)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/bao-lab.sh"

use_lab_token

ROLE="${1:-ai-harness-service}"

c_head "Refreshing the secret_id for AppRole '${ROLE}'"

if ! bao_lab read -format=json "auth/approle/role/${ROLE}" >/dev/null 2>&1; then
  c_err "No such AppRole: ${ROLE}"
  c_err "Run ./scripts/setup-platform.sh first."
  exit 1
fi

# `-force` makes this safe to re-run: it issues a NEW secret_id rather than
# failing because one is already outstanding.
SID="$(bao_lab write -force -format=json "auth/approle/role/${ROLE}/secret-id" 2>/dev/null \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['secret_id'])")"

if [[ -z "${SID}" || "${SID}" == "null" ]]; then
  c_err "The server did not return a secret_id."
  exit 1
fi

save_secret "ai-harness-secret-id" "${SID}"
c_ok "New secret_id saved to lab/secrets/ai-harness-secret-id (chmod 600)"

# Prove it works, rather than telling the learner to trust us.
RID="$(bao_lab read -format=json "auth/approle/role/${ROLE}/role-id" 2>/dev/null \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['role_id'])")"

if bao_lab write -format=json auth/approle/login role_id="${RID}" secret_id="${SID}" >/dev/null 2>&1; then
  c_ok "Verified: the new secret_id logs in successfully."
else
  c_err "The new secret_id did NOT authenticate. Something else is wrong."
  exit 1
fi

cat <<'EOF'

  Point your application at it:
      export BAO_SECRET_ID=$(cat lab/secrets/ai-harness-secret-id)

  Reminder: this credential is designed to expire. In production, whatever
  delivers the secret_id to the workload mints a fresh one on a schedule and
  hands it over out of band.

EOF
