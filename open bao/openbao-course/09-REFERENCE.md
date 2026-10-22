# Level 9 — Reference & Cheatsheet

> Print this. Bookmark it. Come back to it.

---

## 9.1 Every important `bao` command

### Global flags and environment

```bash
bao [command] [options] [path] [args]
```

| Flag | Purpose | Env var |
|---|---|---|
| `-address` | Server address | `BAO_ADDR` |
| `-token` | Token | `BAO_TOKEN` (legacy: `VAULT_TOKEN`) |
| `-namespace` | Namespace | `BAO_NAMESPACE` |
| `-format` | `table` \| `json` \| `yaml` | `BAO_FORMAT` |
| `-field` | Extract one field | — |
| `-output-curl-string` | Print the equivalent curl | — |
| `-output-policy` | Print the required policy | — |
| `-detailed` | More detail (where supported) | — |
| `-non-interactive` | Never prompt | — |
| `-no-store` | Don't write the token to disk | — |
| `-tls-skip-verify` | ⚠️ dev only | — |
| `-ca-cert` / `-ca-path` / `-client-cert` / `-client-key` | TLS material | `BAO_CACERT` |

> The `BAO_` prefix is preferred, but the CLI **falls back to `VAULT_`** if
> present — for compatibility with existing Vault tooling.

### Status & info

```bash
bao status                       # seal state, version, cluster info
bao status -format=json
bao status -field=sealed         # 2.7.0
bao version
bao version-history
```

### Operator

```bash
bao operator init [-key-shares=N] [-key-threshold=T] [-pgp-keys=...]
bao operator init -status
bao operator unseal <key>
bao operator seal
bao operator step-down
bao operator generate-root [-init] [-format=json]
bao operator rekey -init
bao operator rotate-keys
bao operator key-status
bao operator members
bao operator diagnose
bao operator migrate ...
bao operator validate-config <file>
```

### Raft

```bash
bao operator raft join https://openbao-1:8200
bao operator raft list-peers
bao operator raft remove-peer <node_id>
bao operator raft snapshot save <file>
bao operator raft snapshot inspect <file>
bao operator raft snapshot restore <file>
bao operator raft autopilot state
bao operator raft autopilot get-config
bao operator raft autopilot set-config ...
```

### Secrets engines

```bash
# Built-in types verified on 2.7.1:
#   kv, kv-v2, transit, pki, database, totp, ssh
#   (cubbyhole/ and identity/ are auto-mounted and cannot be enabled)
# Plugin-only (from openbao/openbao-plugins):
#   ldap, aws, gcp, consul, nomad, mongodb
bao secrets enable -path=<path> <type>
bao secrets disable <path>
bao secrets move <old> <new>
bao secrets tune -default-lease-ttl=1h -max-lease-ttl=4h <path>
bao secrets list
bao secrets list -detailed
bao secrets list -format=json
```

### KV

```bash
# Modern syntax: -mount=<mount> <key>
# (the path-like `<mount>/<key>` form is DEPRECATED in 2.7.x)
bao kv put -mount=secret myapp k=v
bao kv get -mount=secret myapp
bao kv get -mount=secret -field=mykey myapp
bao kv get -mount=secret -version=2 myapp
bao kv metadata get -mount=secret myapp
bao kv delete -mount=secret myapp
bao kv undelete -mount=secret myapp
bao kv destroy -mount=secret myapp
bao kv metadata delete -mount=secret myapp
bao kv list -mount=secret
bao kv scan -mount=secret
```

### Auth methods

```bash
# Built-in types verified on 2.7.1:
#   oidc, jwt, approle, userpass, kubernetes, cert
#   (the "token" method is always mounted and cannot be enabled/disabled)
# Plugin-only (from openbao/openbao-plugins):
#   ldap, kerberos, radius, github, aws
bao auth enable -path=<path> <type>
bao auth disable <path>
bao auth list
bao auth accessor list
bao auth tune <path> ...
bao login -method=<type> [args]
# There is NO `bao logout` command in OpenBao 2.7.1. To "log out", delete
# the token file that the default token helper wrote:
rm -f ~/.vault-token          # or $BAO_TOKEN_PATH, if you set it
```

### Policies

```bash
bao policy write <name> -        # from stdin
bao policy read <name>
bao policy list
bao policy delete <name>
# `policy fmt` takes a LOCAL FILE PATH and rewrites it in place.
# (No policy name, no -check flag.)
bao policy fmt ./policies/app-readonly.hcl
```

### Tokens

```bash
bao token create [-policy=...] [-ttl=] [-renewable] [-orphan] [-batch] [-period=] ...
bao token lookup
bao token lookup -accessor <accessor>
bao token renew
bao token renew -increment=2h
bao token revoke <token>
bao token revoke -accessor <accessor>
bao token revoke -orphan <accessor>
bao token revoke -accessor <a> -revoke-lease
bao token capabilities <token> <path>
# (no CLI command — API only)
curl -X POST -H "X-Vault-Token: $BAO_TOKEN" -d '{"path":"<path>"}' \
  "$BAO_ADDR/v1/sys/capabilities-self"
```

### Leases

```bash
bao lease renew -increment=1h <lease-id>
bao lease revoke <lease-id>
bao lease revoke -prefix <path-prefix>
bao lease lookup <lease-id>
```

### Identity

```bash
bao write identity/entity name="alice" metadata=...
bao write identity/entity/id/<id> groups=<group>
bao write identity/entity-alias name=... canonical_id=... mount_accessor=...
bao write identity/group name=<group> policies=<p1>,<p2>
bao read identity/entity/name/alice
bao list identity/entity/name
bao list identity/group/name
```

### Audit

```bash
# 2.7.1: creation via the API is DISABLED by default.
# Use the declarative `audit "<type>" "<path>" { options { ... } }`
# stanza in the server config instead (see §5.5). The command below
# only works with unsafe_allow_api_audit_creation = true.
bao audit enable -path=<name> <type> [options]
bao audit disable <name>
bao audit list
bao audit list -detailed
```

### Plugins

```bash
bao plugin init <sha256> <command>
bao plugin list
bao plugin info <name>
bao plugin register <sha256> <command>
bao plugin reload <name>
bao plugin prune
bao plugin deregister <name>
```

### Namespaces

```bash
bao namespace create <name>
bao namespace list
bao namespace delete <name>
bao namespace seal <name>
bao namespace seal-status <name>
bao namespace patch <name>
```

### Misc

```bash
bao path-help <path>          # discover the API of a path
bao list <path>               # LIST
bao read <path>               # GET
bao write <path> k=v          # PUT/POST
bao delete <path>             # DELETE
bao patch <path> k=v
bao print token
bao unwrap <wrapping-token>
bao monitor [-log-level=info]
bao debug <path>
bao namespace ...
```

---

## 9.2 The API path map

### System

```
GET    /v1/sys/health
GET    /v1/sys/seal-status
POST   /v1/sys/init
GET    /v1/sys/init
GET    /v1/sys/leader
GET    /v1/sys/ha-status
GET    /v1/sys/host-info
GET    /v1/sys/metrics
GET    /v1/sys/monitor
GET    /v1/sys/config/state/sanitized
GET    /v1/sys/config/auditing
POST   /v1/sys/config/cors
GET    /v1/sys/config/ui
```

### Mounts, auth, policies

```
GET    /v1/sys/mounts
POST   /v1/sys/mounts/<type>
DELETE /v1/sys/mounts/<path>
POST   /v1/sys/mounts/<path>/tune
GET    /v1/sys/auth
POST   /v1/sys/auth/<type>
DELETE /v1/sys/auth/<path>
POST   /v1/sys/auth/<path>/tune
GET    /v1/sys/policies/acl
GET    /v1/sys/policies/acl/<name>
POST   /v1/sys/policies/acl/<name>
DELETE /v1/sys/policies/acl/<name>
GET    /v1/sys/policies/egp        (see note in §3.3)
GET    /v1/sys/policies/rgp        (see note in §3.3)
```

### Tokens

```
POST   /v1/auth/token/create
POST   /v1/auth/token/create-orphan
GET    /v1/auth/token/lookup-self
POST   /v1/auth/token/renew-self
POST   /v1/auth/token/revoke-self
LIST   /v1/auth/token/accessors
POST   /v1/auth/token/revoke
POST   /v1/auth/token/revoke-accessor
POST   /v1/auth/token/renew
POST   /v1/auth/token/lookup
GET    /v1/auth/token/accessors
```

### Audit & quotas

```
GET    /v1/sys/audit
POST   /v1/sys/audit/<type>
DELETE /v1/sys/audit/<path>
GET    /v1/sys/quotas/config
POST   /v1/sys/quotas/rate-limit
POST   /v1/sys/quotas/lease-count
```

### Advanced (2.6/2.7)

```
POST   /v1/sys/generate-root-token          # 2.6+ authenticated root gen
POST   /v1/sys/generate-root-token/update
GET    /v1/sys/generate-root-token/attempt  # 2.6+ authenticated status
POST   /v1/sys/generate-recovery-token
GET    /v1/sys/external-keys                 # 2.7
POST   /v1/sys/external-keys/<mount>
LIST   /v1/sys/workflows/manage              # 2.6
GET    /v1/sys/workflows/manage/<path>
POST   /v1/sys/workflows/execute/<path>
POST   /v1/sys/control-group/authorize       # 2.7
GET    /v1/sys/control-group/request         # 2.7
POST   /v1/sys/wrapping/unwrap
GET    /v1/sys/internal/specs/openapi
GET    /v1/sys/internal/ui/resultant-acl
```

### Auth method logins

```
POST   /v1/auth/userpass/login/<username>
POST   /v1/auth/approle/login
POST   /v1/auth/oidc/login
POST   /v1/auth/jwt/login
GET    /v1/auth/oidc/auth_url
GET    /v1/auth/oidc/callback
POST   /v1/auth/kubernetes/login
POST   /v1/auth/cert/login
```

### Secrets engines

```
GET    /v1/secret/data/<path>          # KV v2
POST   /v1/secret/data/<path>
GET    /v1/secret/metadata/<path>
POST   /v1/secret/delete/<path>
POST   /v1/secret/undelete/<path>
POST   /v1/secret/destroy/<path>

GET    /v1/transit/keys/<name>
POST   /v1/transit/keys/<name>
POST   /v1/transit/keys/<name>/rotate
POST   /v1/transit/encrypt/<name>
POST   /v1/transit/decrypt/<name>
POST   /v1/transit/sign/<name>
POST   /v1/transit/verify/<name>
POST   /v1/transit/datakey/plaintext/<name>
POST   /v1/transit/hmac/<algo>
POST   /v1/transit/hash
POST   /v1/transit/random/<bytes>

POST   /v1/pki/root/generate/internal
POST   /v1/pki/root/sign-intermediate
POST   /v1/pki/intermediate/generate/internal
POST   /v1/pki/intermediate/set-signed
POST   /v1/pki/issue/<role>
POST   /v1/pki/revoke
POST   /v1/pki/crl/rotate
GET    /v1/pki/ca
GET    /v1/pki/cert/ca

POST   /v1/database/config/<name>
POST   /v1/database/roles/<name>
GET    /v1/database/creds/<role>
POST   /v1/database/static-roles/<name>
POST   /v1/database/rotate-role/<name>
```

### Headers

| Header | Purpose |
|---|---|
| `X-Vault-Token` | The token |
| `X-Vault-Request: true` | Required for some endpoints (agent/proxy `quit`) |
| `X-Vault-Wrap-TTL` | Request response wrapping |
| `X-Vault-Index` | (2.7) consistency index from a write response |
| `X-Vault-Inconsistent` | (2.7) `fail` \| `forward-active-node` \| `await-state` |
| `X-Vault-Namespace` | Namespace header |
| `X-Vault-Forward` | Internal forwarding |

---

## 9.3 Production-grade HCL configuration (annotated)

```hcl
# ═══════════════════════════════════════════════════════════════
#  OpenBao 2.7.1 — production server configuration
# ═══════════════════════════════════════════════════════════════

ui           = true
cluster_name = "openbao-prod"

api_addr     = "https://openbao-1.corp.internal:8200"
cluster_addr = "https://openbao-1.corp.internal:8201"

# ── Storage ────────────────────────────────────────────────────
storage "raft" {
  path    = "/openbao/data"
  node_id = "openbao-1"

  performance_multiplier = 1
  snapshot_threshold     = 8192
  snapshot_interval      = 120
  trailing_logs          = 10000
}

# ── Listeners ──────────────────────────────────────────────────
listener "tcp" {
  address         = "0.0.0.0:8200"
  cluster_address = "0.0.0.0:8201"

  tls_cert_file = "/openbao/certs/openbao.crt"
  tls_key_file  = "/openbao/certs/openbao.key"
  tls_min_version = "tls12"
  tls_auto_reload  = true            # 2.7.0

  # Unauthenticated legacy endpoints stay OFF
  disable_unauthed_rekey_endpoints = true   # default true

  # Request limits
  max_request_duration   = "60s"
  max_request_size       = 33554432
  max_request_json_memory = 34078720
  max_request_json_strings = 1000
  http_read_timeout      = "30s"
  http_write_timeout     = "0"
  http_idle_timeout      = "5m"

  # 2.7.0 consistency behaviour
  consistency_fallback_behavior        = "forward-active-node"
  consistency_missing_header_forward   = false
  consistency_max_index_wait           = "30s"
}

# ── Memory protection ──────────────────────────────────────────
# ⚠️ There is NO `disable_mlock` option in OpenBao 2.x — it was removed in
#    2.0.0 and the server refuses to start if it is present. Harden swap
#    instead (systemd MemorySwapMax=0, or cgroup v2 memory.swap.max=0;
#    in Docker: memswap_limit: 0 / --memory-swappiness=0).

# ── Lease policy ───────────────────────────────────────────────
default_lease_ttl = "24h"
max_lease_ttl     = "168h"
default_max_request_duration = "90s"

# ── User lockout ───────────────────────────────────────────────
user_lockout "all" {
  lockout_threshold    = 5
  lockout_duration     = "15m"
  lockout_counter_reset = "15m"
}

# ── Telemetry ──────────────────────────────────────────────────
telemetry {
  prometheus_retention_time = "30s"
  disable_hostname   = false
  usage_gauge_period = "1m"
}

# ── Response headers (optional, for debugging) ────────────────
# enable_response_header_hostname = true
# enable_response_header_raft_node_id = true

# ── Plugins (2.5.0+, hardened in 2.7.0) ───────────────────────
plugin_directory = "/openbao/plugins"
plugin_auto_download     = true
plugin_auto_register     = true
plugin_download_behavior = "fail"
plugin_download_max_size = "536870912"   # 512MB default (2.5.5)

# plugin "kms" "pkcs11" {
#   image = "ghcr.io/openbao/openbao-plugin-kms-pkcs11@sha256:<digest>"
# }

# ── Auto-unseal (2.6.0+ plugin model) ──────────────────────────
# seal "pkcs11" {
#   # ...
#   health_check_enabled           = true
#   health_check_timeout           = "1m"
#   health_check_interval          = "10m"
#   health_check_interval_unhealthy = "1m"
# }

# ── Declarative self-initialization (2.4.0+) ───────────────────
# initialize "audit" {
#   request "enable-audit-file" {
#     operation = "update"
#     path      = "sys/audit/file"
#     data = {
#       type    = "file"
#       options = { file_path = "/openbao/logs/audit.log", mode = "0600" }
#     }
#   }
# }

# ── Declarative audit device (2.4.0+) ─────────────────────────
# audit "file" {
#   type    = "file"
#   options = { file_path = "/openbao/logs/audit.log", mode = "0600", log_raw = false }
# }

# ── Keep these OFF ─────────────────────────────────────────────
raw_storage_endpoint  = false
introspection_endpoint = false
unsafe_cross_namespace_identity = false
# unsafe_relative_paths = false
```

---

## 9.4 The full production runbook

### Bootstrapping a new cluster

```bash
# 1. Start
docker compose up -d

# 2. Init (once)
export BAO_ADDR=https://openbao-1:8200
export BAO_CACERT=./certs/ca.crt
bao operator init -key-shares=5 -key-threshold=3 \
  -pgp-keys="alice.asc,bob.asc,carol.asc" \
  -root-token-pgp-key="admin.asc"

# 3. Unseal node 1
bao operator unseal '<k1>'; bao operator unseal '<k2>'; bao operator unseal '<k3>'

# 4. Join the rest
for n in 2 3 4 5; do
  BAO_ADDR=https://openbao-$n:8200 bao operator raft join https://openbao-1:8200
done

# 5. Unseal the rest (each node, each threshold)
for n in 2 3 4 5; do
  for k in 1 2 3; do
    BAO_ADDR=https://openbao-$n:8200 bao operator unseal '<k>'
  done
done

# 6. Audit FIRST
bao audit enable -path=file file file_path=/openbao/logs/audit.log mode=0600
bao audit enable -path=socket socket address="tcp://audit-sink:9023"

# 7. Configure
bao secrets enable -path=secret kv-v2
bao secrets enable -path=db database
bao secrets enable -path=transit transit
bao auth enable -path=oidc oidc
bao auth enable -path=approle approle
bao auth enable -path=github-actions jwt

# 8. Policies, roles, groups (from your IaC repo)

# 9. Revoke the root token
bao token revoke <root-token>

# 10. Snapshot
bao operator raft snapshot save /backup/initial.snap

# 11. Verify
bao status
bao operator raft autopilot state
bao operator raft list-peers
bao secrets list
bao policy list
```

### Daily checks

```bash
bao status
bao operator raft autopilot state
curl -s --cacert certs/ca.crt $BAO_ADDR/v1/sys/metrics | grep -E 'unsealed|active'
df -h /openbao/data /openbao/logs
tail -f /openbao/logs/audit.log | jq -c '{t:.time,op:.request.operation,path:.request.path,err:.error}'
```

### Weekly checks

```bash
# Lease/credential leak check
psql -c "SELECT count(*) FROM pg_roles WHERE rolname LIKE 'v-token-%';"
bao list sys/leases/lookup

# Access review
bao list sys/policies/acl
bao list identity/group/name
bao auth accessor list
```

### Monthly checks

```bash
# Restore drill (in a scratch cluster)
bao operator raft snapshot save /tmp/drill.snap
# ... spin up a scratch cluster, restore, verify ...
```

---

## 9.5 Version migration table (Vault → OpenBao, and 2.x changes)

### Vault 1.14 → OpenBao 2.x

| Vault | OpenBao | Notes |
|---|---|---|
| `vault` CLI | `bao` CLI | Config/env still honour `VAULT_` as a fallback |
| `VAULT_ADDR` | `BAO_ADDR` | `VAULT_` still works as fallback |
| `VAULT_TOKEN` | `BAO_TOKEN` | Same |
| `VAULT_NAMESPACE` | `BAO_NAMESPACE` | Same |
| `VAULT_TOKEN_HELPER` | `BAO_TOKEN_HELPER` | Same |
| `~/.vault-token` | `~/.vault-token` | Override with `BAO_TOKEN_PATH` (2.6.0) |
| `vault status` | `bao status` | Same |
| `vault kv put` | `bao kv put` | Same |
| `vault operator raft snapshot` | `bao operator raft snapshot` | Same |
| `VAULT_LICENSE` | — | Not applicable (MPL-2.0) |
| Enterprise namespaces | `bao namespace` | **Free** |
| Sentinel roles | CEL roles | Not API-compatible |

### OpenBao version changes that break things

| Version | Change | Action |
|---|---|---|
| 2.3.1 | Namespaces GA | — |
| 2.4.0 | Declarative self-init + audit devices; `file` backend legacy upsert dropped | — |
| 2.5.0 | OCI plugin distribution; standby reads; OIDC client credentials | `plugin_auto_download` is a supply-chain decision |
| 2.5.5 | `plugin_download_max_size` (512MB) | Keep it set |
| 2.6.0 | Namespace sealing; KMS plugins; workflows; authenticated root gen; distroless image; `stored_shares` removed; `build_date`→`commit_date`; `sys/health` fields removed; image runs as `openbao` user | Update scripts; fix volume perms |
| 2.6.3 | K8s SA JWT validated on renewal | Patch |
| 2.7.0 | **PQC**; External Keys; control groups; consistency headers; PebbleDB; Postgres read-scaling; **`file` backend removed**; **cloud/PKCS#11 seals removed from binary**; **Kerberos/LDAP/RADIUS removed**; HSM distribution discontinued; `plugin_auto_register` default true; `bao plugin prune` | **Install plugins BEFORE upgrading** |
| 2.7.1 | 5 security fixes (GHSA-3237, q74w, 7m59, 5v22, gf3j) | **Patch immediately** |

---

## 9.6 Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `permission denied` on a KV read | Missing `metadata/` path in the policy | Add `path "<m>/metadata/<k>" { capabilities=["read","list"] }` |
| `permission denied` on `bao kv metadata get` | Missing `list` on the metadata path | Add `list` |
| `permission denied` on `bao secrets list` | Policy too narrow (needs `list` on `sys/mounts`) | Add `sys/mounts` read/list, or don't use `secrets list` |
| OIDC login loops | Redirect URI mismatch (http/https, host, port, trailing slash) | Compare exactly, both sides |
| OIDC: no groups in the token | Keycloak client scope mapper not configured | Add a Group Membership mapper with claim `groups` |
| OIDC: "issuer" error | Discovery URL host ≠ `iss` claim | Make them identical |
| AppRole: "invalid secret id" | Already used (`num_uses=1`) or expired | Mint a new one |
| AppRole: 403 on the secret | Role's token policies don't include the read policy | `bao read auth/approle/role/<name>` |
| AppRole: token can't create children | `token_num_uses` set | Set `token_num_uses=0` |
| Unseal: "unseal key not valid" | Wrong key / wrong node / key already rotated | Check `bao status`, `bao operator key-status` |
| Raft: node won't join | `cluster_addr` unreachable, or TLS mismatch | Check `bao operator raft list-peers`, node logs |
| Raft: no leader | Lost quorum | Restore a voter; check `autopilot state` |
| Audit log not written | Path unwritable, or `log_raw` issues | Check the container's volume perms; `bao audit list -detailed` |
| Cluster stops serving | **All** audit devices failed (fail-closed) | Free disk / fix the sink — this is by design |
| `503 sealed` | Node sealed | Unseal it |
| DB role count growing | Revocation failing | Check `revocation_statements` |
| `vault.core.unsealed=0` | Sealed node | Unseal; check the seal health check |
| Transit decrypt fails after rotation | `min_decryption_version` archived the version | Lower it, or re-encrypt with `transit/rewrap` |
| PKI: "common name not allowed" | `allowed_domains` doesn't include it | Fix the role |
| PKI: chain incomplete | Only the root cert distributed | Distribute the **chain** (`pki/ca`) |
| `bao` can't reach the server | TLS / CA mismatch | `BAO_CACERT`; check `curl --cacert` |

### ⚠️ Scripting gotchas (found the hard way)

These bite every script that talks to OpenBao. All three were found by
*running* the code, not by reading the docs.

#### 1. `bao status` exits non-zero when sealed or uninitialised

```bash
$ bao status >/dev/null; echo $?
2
```

So this idiom **breaks** under `set -euo pipefail`:

```bash
# ❌ The pipeline's exit status is non-zero, so `|| echo true` ALSO fires
#    and you get V="true
true" — which never equals "true".
V=$(bao status -format=json | jq -r .sealed || echo true)
```

```bash
# ✅ Capture the JSON first, then parse it
raw=$(bao status -format=json 2>/dev/null || true)
V=$(printf '%s' "$raw" | jq -r '.sealed' 2>/dev/null || true)
```

The same applies to `bao operator init -status` (exit 2 = not initialised).

#### 2. jq's `//` operator treats `false` as empty

```bash
# ❌ Returns "true" when .sealed is FALSE — i.e. when the server is UNSEALED
jq -r '.sealed // "true"'

# ✅ Correct
jq -r 'if has("sealed") then (.sealed | tostring) else "true" end'
```

`false // "x"` → `"x"`, because `//` means "if the left side is null **or
false**". This one is nasty: a perfectly healthy server gets reported as
"still SEALED".

#### 3. Enabling `kv-v2` briefly makes the mount unavailable

```
* Upgrading from non-versioned to versioned data. This backend will be
  unavailable for a brief period and will resume service shortly.
```

A one-time storage-format upgrade. **Retry** rather than treating it as a
failure:

```bash
for i in 1 2 3 4 5 6; do
  if bao kv put -mount=secret myapp k=v >/dev/null 2>&1; then break; fi
  sleep 2
done
```

#### 4. `bao write -f` is not "print the raw value"

`-f` means "raw format", which still prints a table for multi-field responses.
For a single field, parse the JSON:

```bash
CT=$(bao write -format=json transit/encrypt/app-data \
      plaintext=$(echo -n "sensitive" | base64) | jq -r .data.ciphertext)
```

#### 5. `bao read` fails on raw-PEM endpoints

`/v1/pki_int/ca` and friends return **PEM**, not JSON. `bao read` expects JSON
and will fail with *"json: cannot unmarshal number into Go value of type
api.Secret"*. Use `curl`:

```bash
curl -s --cacert ca.crt "$BAO_ADDR/v1/pki_int/ca" > ca-chain.crt
```

### Diagnostic commands

```bash
bao status
bao sys/config/state/sanitized | jq          # what is actually configured
bao sys/leader
bao sys/ha-status | jq
bao operator raft autopilot state
bao operator members
bao operator key-status
bao operator diagnose
bao sys/internal/ui/resultant-acl             # effective ACL for a token
curl -X POST -H "X-Vault-Token: $BAO_TOKEN" -d '{"path":"<path>"}' \
  "$BAO_ADDR/v1/sys/capabilities-self" 
bao path-help <path>                          # discover an API
bao read sys/internal/specs/openapi > openapi.json
```

---

## 9.7 The one-page mental model

```
┌──────────────────────────────────────────────────────────────────┐
│  CLIENT                                                            │
│    human → Keycloak (OIDC) ──┐                                   │
│    machine → AppRole ────────┤                                    │
│    CI → GitHub OIDC (JWT) ───┼──▶ ┌───────────┐                   │
│                               │    │  TOKEN    │ policy + TTL     │
│                               │    └─────┬─────┘                   │
│                               │          │                         │
│                               ▼          ▼                         │
│                        ┌─────────────────────┐                    │
│                        │  ROUTER + POLICY    │ deny by default   │
│                        │  ENGINE             │                    │
│                        └───┬─────────────┬───┘                    │
│                            │             │                        │
│              ┌─────────────▼──┐   ┌──────▼──────────┐             │
│              │ SECRETS        │   │ AUTH METHODS     │             │
│              │ ENGINE         │   │ (login)          │             │
│              │ kv transit pki │   │ oidc approle jwt │             │
│              │ database totp  │   │ kubernetes cert  │             │
│              └────────┬───────┘   └─────────────────┘             │
│                       │                                          │
│                       ▼                                          │
│                ┌─────────────┐                                    │
│                │  BARRIER 🔒 │  encrypt / decrypt                │
│                └──────┬──────┘                                    │
│                       │                                          │
│                       ▼                                          │
│           ┌───────────────────────┐    ┌──────────────────┐      │
│           │  STORAGE (ciphertext) │    │  AUDIT DEVICES   │      │
│           │  Raft | PostgreSQL   │    │  file/socket/http│──────▶ SIEM
│           └───────────────────────┘    └──────────────────┘      │
│                       │                                          │
│              sealed by: Shamir shares | KMS plugin | transit seal │
└──────────────────────────────────────────────────────────────────┘
```

**Ten truths to remember:**

1. Everything is a **path**; every operation is a **capability** on it.
2. Policies are **deny by default**; grants **union**; `deny` always wins.
3. **Tokens** = identity + policies + TTL. Revoke the token, lose the access.
4. **Accessors** are safe to store; tokens are not.
5. **Leases** make secrets die. Dynamic creds without leases are a smell.
6. The **barrier** means storage holds only ciphertext.
7. The **seal** is the crown jewel. Losing the KMS key = losing everything,
   even backups.
8. **Audit covers everything** except a short list of unauthenticated paths.
9. If **all** audit devices fail, OpenBao stops serving. That's correct.
10. **Namespaces are free** in OpenBao. Use them for real isolation.

---

## 9.8 Where to go next

| Topic | Where |
|---|---|
| Full docs | https://openbao.org/docs/ |
| 2.7 release notes | https://openbao.org/community/release-notes/2-7-0/ |
| Source + changelog | https://github.com/openbao/openbao |
| Plugins | https://github.com/openbao/openbao-plugins |
| Helm chart | https://github.com/openbao/openbao-helm |
| API docs (live) | `bao read sys/internal/specs/openapi` |
| Glossary | https://openbao.org/docs/glossary/ |
| Community | https://github.com/orgs/openbao/discussions |
| Upgrade guides | https://openbao.org/docs/guides/upgrade/ |
| Migration from Vault | https://openbao.org/docs/guides/migration/ |

---

**Course complete.** You now know OpenBao from the barrier up: how it stores
data, how it seals, how it authorizes, how it generates credentials, how it
audits, how it clusters, how it fails, and how it plugs into Keycloak,
FastAPI, LangChain, PostgreSQL, GitHub Actions and Docker Compose.

Go build something. Then break it in a lab and read the audit log.
