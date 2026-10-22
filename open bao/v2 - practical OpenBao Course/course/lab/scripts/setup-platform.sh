#!/usr/bin/env bash
# =============================================================================
# setup-platform.sh - provision Meridian AI's secret structure
# =============================================================================
# Idempotent. Safe to re-run. Assumes Module 01 (init + unseal) is done.
#
# Creates:
#   - KV v2 mount at ai/platform with production tuning
#   - The Gemini API key + Postgres + Redis credentials
#   - Transit mount for application-level encryption
#   - AppRole for the AI harness with a least-privilege policy
#   - AppRole for the secret rotation bot
#   - Custom metadata for ownership/rotation tracking
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/bao-lab.sh"

use_lab_token

# -----------------------------------------------------------------------------
# 1. Secret engine: KV v2 for platform configuration
# -----------------------------------------------------------------------------
c_head "1/6  KV v2 engine at ai/platform"
if bao_lab secrets list -format=json | python3 -c "import sys,json;print('ai/platform/' in json.load(sys.stdin))" | grep -q True; then
  c_warn "ai/platform/ already mounted - skipping"
else
  # NOTE: "kv-v2" explicitly. Plain "kv" gives you KV v1 (verified).
  bao_lab secrets enable -path=ai/platform kv-v2 >/dev/null
  c_ok "Mounted ai/platform/ (kv-v2)"
fi

# KV v2 specific settings live at <mount>/config, NOT sys/mounts/<path>/tune
bao_lab write ai/platform/config \
  cas_required=true \
  max_versions=10 \
  delete_version_after=168h \
  >/dev/null
c_ok "KV v2 config: cas_required=true, max_versions=10, delete_version_after=168h"

# Generic engine tuning (leases, listing visibility) - note flags come FIRST
bao_lab secrets tune -default-lease-ttl=1h -max-lease-ttl=24h ai/platform >/dev/null
c_ok "Engine tuning: default-lease-ttl=1h, max-lease-ttl=24h"

# -----------------------------------------------------------------------------
# 2. Transit engine for application-level encryption
# -----------------------------------------------------------------------------
c_head "2/6  Transit engine at ai/transit"
if bao_lab secrets list -format=json | python3 -c "import sys,json;print('ai/transit/' in json.load(sys.stdin))" | grep -q True; then
  c_warn "ai/transit/ already mounted - skipping"
else
  bao_lab secrets enable -path=ai/transit transit >/dev/null
  c_ok "Mounted ai/transit/"
fi

bao_lab write ai/transit/keys/llm-payload-key \
  type=chacha20-poly1305 \
  min_decryption_version=1 \
  >/dev/null
c_ok "Created Transit key: llm-payload-key (chacha20-poly1305)"

# -----------------------------------------------------------------------------
# 3. The actual secrets
# -----------------------------------------------------------------------------
c_head "3/6  Storing Meridian AI secrets"
# CAS is required, so we must pass the current version.
# Helper: read current version (0 if the path does not exist yet)
cur_version() {
  # NOTE: flags must come BEFORE the positional path, or you get
  # "Too many arguments (expected 1, got 2)".
  bao_lab kv metadata get -format=json "$1" 2>/dev/null \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('data',{}).get('current_version',0))" 2>/dev/null \
    || echo 0
}

put_secret() {
  local path="$1"; shift
  local cas; cas="$(cur_version "$path")"
  # With cas_required=true, EVERY write must declare the expected current
  # version - including the very first one, which uses -cas=0.
  bao_lab kv put -cas="$cas" "$path" "$@" >/dev/null
  c_ok "Wrote ${path} (version $(cur_version "$path"))"
}

put_secret ai/platform/llm/gemini \
  api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" \
  model="gemini-2.0-flash" \
  project_id="meridian-ai-prod" \
  endpoint="https://generativelanguage.googleapis.com/v1beta"

put_secret ai/platform/db/postgres \
  username="meridian_app" \
  password="Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK" \
  host="postgres" \
  port="5432" \
  dbname="meridian_ai" \
  sslmode="require"

put_secret ai/platform/cache/redis \
  host="redis" \
  port="6379" \
  password="Yb3mQ8vT1xW6rK4pL9zD2nF7gH5jA0sC4eU" \
  db="0"

put_secret ai/platform/oidc/keycloak \
  issuer="http://keycloak:8080/realms/meridian-ai" \
  client_id="ai-harness" \
  client_secret="meridian-ai-harness-client-secret-rotate-me" \
  admin_password="admin"

# -----------------------------------------------------------------------------
# 4. Custom metadata - ownership and rotation policy
# -----------------------------------------------------------------------------
c_head "4/6  Tagging secrets with ownership metadata"
for p in ai/platform/llm/gemini ai/platform/db/postgres ai/platform/cache/redis ai/platform/oidc/keycloak; do
  case "$p" in
    *gemini)    owner="ai-platform"; rot="90d"; sev="critical"; tk="SEC-1042" ;;
    *postgres)  owner="data-platform"; rot="30d"; sev="critical"; tk="SEC-1043" ;;
    *redis)     owner="data-platform"; rot="90d"; sev="high"; tk="SEC-1044" ;;
    *keycloak)  owner="identity"; rot="30d"; sev="critical"; tk="SEC-1045" ;;
  esac
  bao_lab kv metadata put \
    -custom-metadata="owner=${owner}" \
    -custom-metadata="rotation=${rot}" \
    -custom-metadata="severity=${sev}" \
    -custom-metadata="ticket=${tk}" \
    "$p" >/dev/null
  c_ok "Tagged ${p} (owner=${owner}, rotation=${rot})"
done

# -----------------------------------------------------------------------------
# 5. Policies
# -----------------------------------------------------------------------------
c_head "5/6  Applying least-privilege policies"
POLICY_DIR="${LAB_DIR}/policies"
for f in "${POLICY_DIR}"/*.hcl; do
  name="$(basename "$f" .hcl)"
  bao_lab policy write "$name" - < "$f" >/dev/null
  c_ok "Policy applied: ${name}"
done

# -----------------------------------------------------------------------------
# 6. AppRoles (machine authentication)
# -----------------------------------------------------------------------------
c_head "6/6  Creating AppRole machine identities"
if ! bao_lab auth list -format=json | python3 -c "import sys,json;print('approle/' in json.load(sys.stdin))" | grep -q True; then
  bao_lab auth enable approle >/dev/null
  c_ok "Enabled approle auth method"
fi

# The AI harness: read-only, short-lived tokens
bao_lab write auth/approle/role/ai-harness-service \
  token_policies="ai-harness-service" \
  token_ttl=15m \
  token_max_ttl=1h \
  secret_id_ttl=1h \
  secret_id_num_uses=0 \
  >/dev/null
c_ok "AppRole ai-harness-service (ttl 15m, max 1h)"

# The rotation bot: the only writer
bao_lab write auth/approle/role/secret-rotation-bot \
  token_policies="secret-rotation-bot" \
  token_ttl=30m \
  token_max_ttl=4h \
  secret_id_ttl=24h \
  >/dev/null
c_ok "AppRole secret-rotation-bot (ttl 30m, max 4h)"

# Generate the secret_id for the harness and save it for the app container
SID="$(bao_lab write -force -format=json auth/approle/role/ai-harness-service/secret-id 2>/dev/null \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['secret_id'])")"
RID="$(bao_lab read -field=role_id auth/approle/role/ai-harness-service/role-id)"
save_secret "ai-harness-role-id" "$RID"
save_secret "ai-harness-secret-id" "$SID"
c_ok "Harness credentials saved to lab/secrets/ (role_id + secret_id)"

cat <<'EOF'

──────────────────────────────────────────────────────────────────────────────
 PLATFORM PROVISIONED

  Mounts      : ai/platform (kv-v2), ai/transit (transit)
  Secrets     : llm/gemini, db/postgres, cache/redis, oidc/keycloak
  Policies    : ai-harness-service, data-pipeline-service,
                secret-rotation-bot, platform-operator, platform-admin
  AppRoles    : ai-harness-service, secret-rotation-bot

  To run the app container:
    export BAO_ROLE_ID=$(cat lab/secrets/ai-harness-role-id)
    export BAO_SECRET_ID=$(cat lab/secrets/ai-harness-secret-id)
    docker compose up -d ai-harness

──────────────────────────────────────────────────────────────────────────────
EOF
