#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
#  bootstrap.sh — idempotent initial configuration for Lab 01
#
#  Run AFTER:  docker compose up -d
#              ./gen-certs.sh
#              bao operator init + unseal
#
#  Usage:  BAO_ADDR=... BAO_CACERT=... ./bootstrap.sh
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

export BAO_ADDR="${BAO_ADDR:-https://127.0.0.1:8200}"
export BAO_CACERT="${BAO_CACERT:-./certs/ca.crt}"

command -v bao >/dev/null || { echo "bao CLI not found"; exit 1; }
command -v jq  >/dev/null || { echo "jq not found"; exit 1; }

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

say "Audit device (before anything else is stored)"
# NOTE: in OpenBao 2.7.1 audit devices cannot be created via the API.
# The device is declared in config/openbao.hcl:
#     audit "file" "file" {
#       description = "Local audit log (declarative)."
#       options { file_path = "/openbao/logs/audit.log" mode = "0600" log_raw = "false" }
#     }
bao audit list -detailed

say "Secret engines"
bao secrets enable -path=secret kv-v2   2>/dev/null || echo "  secret/ already enabled"
bao secrets enable -path=transit transit 2>/dev/null || echo "  transit/ already enabled"
bao secrets enable -path=db database     2>/dev/null || echo "  db/ already enabled"

say "Auth methods"
bao auth enable -path=userpass userpass 2>/dev/null || echo "  userpass/ already enabled"
bao auth enable -path=approle approle    2>/dev/null || echo "  approle/ already enabled"

say "Policies"
bao policy write app-readonly - >/dev/null <<'EOF'
path "secret/data/myapp" {
  capabilities = ["read"]
}
path "secret/metadata/myapp" {
  capabilities = ["read", "list"]
}
EOF
echo "  app-readonly"

bao policy write app-writer - >/dev/null <<'EOF'
path "secret/data/myapp" {
  capabilities = ["create", "read", "update", "patch"]
}
path "secret/metadata/myapp" {
  capabilities = ["read", "list", "delete"]
}
EOF
echo "  app-writer"

say "Demo secret"
bao kv put secret/myapp \
  db_host=postgres \
  db_port=5432 \
  db_user=app \
  db_password='S3cr3t-Change-Me' \
  llm_api_key='sk-demo-not-a-real-key'

say "AppRole for the app"
bao write auth/approle/role/myapp \
  secret_id_ttl=10m \
  secret_id_num_uses=1 \
  token_num_uses=0 \
  token_ttl=20m \
  token_max_ttl=1h \
  policies=app-readonly 2>/dev/null || echo "  (role exists)"

ROLE_ID=$(bao read -field=role_id auth/approle/role/myapp)
SECRET_ID=$(bao write -f -field=secret_id auth/approle/role/myapp/secret-id)

cat <<EOF

──────────────────────────────────────────────────────────────
  ROLE_ID     = $ROLE_ID
  SECRET_ID   = $SECRET_ID

  ⚠️  Treat the secret_id like a password: it is single-use
      (secret_id_num_uses=1) and expires in 10 minutes.
      Never commit it. Inject it at deploy time.
──────────────────────────────────────────────────────────────
EOF

say "Done"
