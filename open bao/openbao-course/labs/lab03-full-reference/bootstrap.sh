#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  bootstrap.sh — full-stack initial configuration (Lab 03)
#
#  Prerequisites:
#    docker compose up -d
#    ./gen-certs.sh
#    bao operator init + unseal
#
#  Environment:
#    BAO_ADDR, BAO_CACERT       — where OpenBao is
#    KEYCLOAK_CLIENT_SECRET     — from keycloak/realm.json
#    PG_ADMIN_PASSWORD          — the openbao_admin password used by
#                                 postgres/init/01-openbao-admin.sql
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

export BAO_ADDR="${BAO_ADDR:-https://127.0.0.1:8200}"
export BAO_CACERT="${BAO_CACERT:-./certs/ca.crt}"

: "${KEYCLOAK_CLIENT_SECRET:?set KEYCLOAK_CLIENT_SECRET}"
: "${PG_ADMIN_PASSWORD:?set PG_ADMIN_PASSWORD}"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

say "1/8 — Audit device (before anything else)"
# NOTE: in OpenBao 2.7.1 audit devices cannot be created via the API.
# The audit device is declared in config/openbao.hcl:
#     audit "file" "file" {
#       description = "Local audit log (declarative)."
#       options { file_path = "/openbao/logs/audit.log" mode = "0600" log_raw = "false" }
#     }
# Verify it is live:
bao audit list -detailed

say "2/8 — Secret engines"
bao secrets enable -path=secret kv-v2   2>/dev/null || echo "   secret/ ok"
bao secrets enable -path=transit transit 2>/dev/null || echo "   transit/ ok"
bao secrets enable -path=db database     2>/dev/null || echo "   db/ ok"

say "3/8 — Auth methods"
bao auth enable -path=oidc oidc          2>/dev/null || echo "   oidc/ ok"
bao auth enable -path=approle approle    2>/dev/null || echo "   approle/ ok"
bao auth enable -path=github-actions jwt 2>/dev/null || echo "   github-actions/ ok"

say "4/8 — OIDC (Keycloak)"
# NOTE (verified on 2.7.1):
#   * the config path is auth/<mount>/config  (NOT auth/oidc/oidc)
#   * oidc_discovery_url is the BASE url     (no .well-known suffix)
#   * the client keys are oidc_client_id / oidc_client_secret
bao write auth/oidc/config \
  oidc_discovery_url="http://keycloak:8080/realms/enterprise" \
  oidc_client_id="openbao" \
  oidc_client_secret="$KEYCLOAK_CLIENT_SECRET" \
  default_role="human"

bao write auth/oidc/role/human - <<EOF
{
  "user_claim": "preferred_username",
  "oidc_scopes": "openid profile email groups",
  "role_type": "oidc",
  "allowed_redirect_uris": "http://localhost:8250/oidc/callback,https://127.0.0.1:8200/ui/vault/auth/oidc/oidc/callback",
  "groups_claim": "groups",
  "token_ttl": "1h",
  "token_max_ttl": "8h"
}
EOF
echo "   auth/oidc/config + auth/oidc/role/human"

say "5/8 — Policies"
bao policy write app-readonly - >/dev/null <<'EOF'
path "secret/data/myapp" {
  capabilities = ["read"]
}
path "secret/metadata/myapp" {
  capabilities = ["read", "list"]
}
path "database/creds/app" {
  capabilities = ["read"]
}
path "transit/encrypt/myapp" {
  capabilities = ["update"]
}
path "transit/decrypt/myapp" {
  capabilities = ["update"]
}
EOF
echo "   app-readonly"

bao policy write human-default - >/dev/null <<'EOF'
path "auth/token/lookup-self" {
  capabilities = ["read"]
}
path "auth/token/renew-self" {
  capabilities = ["update"]
}
path "sys/audit" {
  capabilities = ["read", "list"]
}
EOF
echo "   human-default"

say "6/8 — Identity groups"
bao write identity/group name=openbao-sre policies=human-default 2>/dev/null || true
bao write identity/group name=openbao-platform policies=human-default 2>/dev/null || true
echo "   openbao-sre, openbao-platform"

say "7/8 — PostgreSQL dynamic credentials"
bao write db/config/postgres \
  plugin_name=postgresql-database-plugin \
  connection_url="postgresql://{{username}}:{{password}}@postgres:5432/appdb?sslmode=disable" \
  username="openbao_admin" \
  password="$PG_ADMIN_PASSWORD" \
  verify_connection=true \
  allowed_roles="app"

bao write db/roles/app \
  db_name=postgres \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT CONNECT ON DATABASE appdb TO \"{{name}}\"; GRANT USAGE ON SCHEMA public TO \"{{name}}\";" \
  revocation_statements="DROP ROLE IF EXISTS \"{{name}}\";" \
  default_ttl="1h" \
  max_ttl="4h" \
  username_template="v-token-{{identity.entity.id}}-{{random 6}}-{{timestamp}}"
echo "   db/config/postgres + db/roles/app"

say "8/8 — App secret + AppRole"
bao kv put secret/myapp \
  db_host=postgres \
  db_port=5432 \
  db_name=appdb \
  redis_host=redis \
  redis_port=6379 \
  llm_api_key='sk-demo-not-a-real-key'

bao write auth/approle/role/myapp \
  secret_id_ttl=10m \
  secret_id_num_uses=1 \
  token_num_uses=0 \
  token_ttl=20m \
  token_max_ttl=1h \
  policies=app-readonly 2>/dev/null || true

ROLE_ID=$(bao read -field=role_id auth/approle/role/myapp)
SECRET_ID=$(bao write -f -field=secret_id auth/approle/role/myapp/secret-id)

cat <<EOF

──────────────────────────────────────────────────────────────
  APPROLE_ROLE_ID   = $ROLE_ID
  APPROLE_SECRET_ID = $SECRET_ID

  ⚠️  The secret_id is single-use and expires in 10 minutes.
      Put it in .env (git-ignored) for the lab; in CI, inject it.

  For the bao-agent sidecar, update config/agent.hcl with these
  values, then:  docker compose up -d bao-agent app
──────────────────────────────────────────────────────────────
EOF
