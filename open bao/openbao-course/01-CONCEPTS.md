# Level 1 — The Core Concepts

> **Goal:** you can now read any OpenBao documentation, any policy, and any
> config file and understand *why* it says what it says. This level is the
> foundation everything else is built on.

---

## 1.1 The server, the barrier, the storage backend

### The chain of custody for a secret

```
  plaintext secret
        │  you call POST /v1/secret/data/myapp  {"db_password":"s3cr3t"}
        ▼
  ┌──────────────────────┐
  │  ROUTER              │  resolves path → mount → plugin
  └──────────┬───────────┘
             ▼
  ┌──────────────────────┐
  │  SECRETS ENGINE      │  kv-v2 plugin
  └──────────┬───────────┘
             ▼
  ┌──────────────────────┐
  │  BARRIER  🔒         │  encrypt(plaintext) → ciphertext
  └──────────┬───────────┘
             ▼
  ┌──────────────────────┐
  │  STORAGE BACKEND     │  Raft or PostgreSQL — ciphertext only
  └──────────────────────┘
```

**Everything crosses the barrier.** The barrier is a single in-memory key
(the *encryption key*) that OpenBao holds only while unsealed. On disk, at rest,
in backups, in snapshots, in the Postgres database — **only ciphertext**.

### The three keys (get this right, it's a common confusion)

| Key                            | Where it lives                                          | What it protects   |
| ------------------------------ | ------------------------------------------------------- | ------------------ |
| **Encryption key** ("keyring") | In memory, unsealed. Encrypted at rest.                 | All your data      |
| **Root key** (barrier key)     | Encrypted by the unseal key, stored next to the data    | The encryption key |
| **Unseal key**                 | Split into N shares, given to humans (or held by a KMS) | The root key       |

So to read a secret:
`unseal share(s) → root key → encryption key → plaintext`

Which is why **unseal is the crown jewels** and why auto-unseal moves that crown
jewel into a KMS/HSM (Level 5) or a second OpenBao cluster (Level 6).

### Storage backends — you have exactly two real choices

| Backend                         | HA?                         | When to use                                                                |
| ------------------------------- | --------------------------- | -------------------------------------------------------------------------- |
| **`raft`** (integrated storage) | ✅ Yes                       | Default choice. Self-contained, no external DB, snapshot/restore built in. |
| **`postgresql`**                | ✅ Yes (`ha_enabled = true`) | You already run Postgres and want one backup/monitoring story.             |
| `pebbledb`                      | ❌ No                        | Non-HA durable, good perf, new in 2.7.0. Fine for single node.             |
| `in-memory`                     | ❌                           | `-dev` mode only.                                                          |
| ~~`file`~~                      | —                           | **REMOVED in 2.7.0.**                                                      |

> ⚠️ **2.7.0 removed the `file` storage backend.** If you see a tutorial using
> `storage "file" { path = "..." }`, that tutorial is pre-2.7 and is wrong.
> Use `storage "raft"`.

Raft config:

```hcl
storage "raft" {
  path    = "/openbao/data"
  node_id = "openbao-node-1"
}
cluster_addr = "https://10.0.0.1:8201"   # REQUIRED with raft
```

PostgreSQL config (2.7 flavour):

```hcl
storage "postgresql" {
  connection_url = "postgres://bao:bao@postgres:5432/openbao?sslmode=verify-full"
  ha_enabled     = "true"
  cluster_addr   = "https://10.0.0.1:8201"   # needed for 2.7 read-scaling
}
```

> **PostgreSQL + HA caveat (2.7.0):** read scalability on Postgres requires
> **physical replication** (streaming replication / Patroni), **not** logical
> replication. And it requires `ha_enabled = true` plus a reachable
> `cluster_addr` from standbys to the primary.

---

## 1.2 Seal / Unseal — the lifecycle

```
   [Uninitialized]  --bao operator init-->  [Initialized, SEALED]
                                                      |
                              unseal keys (Shamir)    |  or auto-unseal (KMS/transit)
                             or recovery keys         v
                                                      [Initialized, UNSEALED]
                                                      |
                             seal / restart / storage error
                                                      v
                                                  [SEALED again]
```

### The four states you'll see

```bash
bao status
```

```
Sealed          true
Storage Type    raft
Initialized     true
```

| State                  | Meaning                             | Can you log in?               |
| ---------------------- | ----------------------------------- | ----------------------------- |
| Uninitialized          | Never `bao operator init`'d         | No — only `/sys/init` works   |
| Initialized + Sealed   | Keys exist but master key is locked | **No**                        |
| Initialized + Unsealed | Fully operational                   | Yes                           |
| Unsealed + Standby     | Node is alive, leader is elsewhere  | Yes (reads; writes forwarded) |

### Shamir seal (the default)

`bao operator init` splits the unseal key into N shares with a threshold T.
**T of N** shares reconstruct it.

```bash
bao operator init -key-shares=5 -key-threshold=3
```

* 5 shares, any 3 unseal.
* Each share is a long base64 string.
* **Partial unsealing is per-node, not per-cluster.** Each node needs T shares
  entered on *that node*. (This trips up everyone once.)
* Shares are NOT stored in OpenBao. If you lose them, you're done (unless you
  have recovery keys).

### Recovery keys (the emergency escape hatch)

With **auto-unseal**, `init` produces *recovery keys* instead of unseal keys.
They are **not** unseal keys — they cannot decrypt the root key. They only
*authorize* quorum operations (generating a new root token, rotating keys).

```bash
bao operator init -recovery-shares=5 -recovery-threshold=3
```

> 🚨 **The critical production warning from the docs, verbatim in spirit:**
> *"If the seal mechanism or its keys are permanently deleted, then the OpenBao
> cluster cannot be recovered, even from backups."* Auto-unseal creates a hard
> lifecycle dependency. Mitigate with IAM/SCP-style controls on the KMS key, and
> **rehearse the recovery-key path**.

### Unsealing, step by step

```bash
bao status                      # -> Sealed: true
bao operator unseal <share-1>   # "Key 1 of 3 unsealed"
bao operator unseal <share-2>   # "Key 2 of 3 unsealed"
bao operator unseal <share-3>   # "Unseal complete"
bao status                      # -> Sealed: false
```

The state is **server-side**, so you can enter shares from different machines.

### Sealing on purpose (incident response)

```bash
bao operator seal     # throws away the root key in memory
```

Useful if you suspect an active compromise: the cluster is instantly useless to
the attacker until the threshold is met again. Requires root/sudo.

### Generating a new root token when you're locked out

```bash
# Requires a quorum of recovery keys (auto-unseal) or unseal keys (Shamir)
bao operator generate-root -init
bao operator generate-root -format=json
```

> ✅ Since 2.6.0, `bao operator generate-root` uses the **authenticated**
> `/sys/generate-root-token` endpoints. The old **unauthenticated**
> `/sys/generate-root/attempt` endpoints are deprecated and disabled by default
> (2.7.1 also fixed a bug where they returned a response even when audit logging
> failed — `GHSA-q74w-hv5x-6hxf`). Never teach people the old endpoint.

### Seal migration

You can move from Shamir → auto-unseal or KMS A → KMS B, but it **requires
downtime** and both seal mechanisms must be available during the migration.
Full procedure: Level 5. Always take a snapshot first.

---

## 1.3 Policies — the authorization model

### Everything is a path, everything is a capability

OpenBao's model is a filesystem with verbs. A **policy** is a set of rules
mapping paths → allowed capabilities.

```hcl
# app-readonly.hcl
path "secret/data/myapp" {
  capabilities = ["read"]
}
```

**Deny by default.** An empty policy grants *nothing*. A token with only
`app-readonly` cannot read `sys/health`, cannot list mounts, cannot write.

### The nine capabilities

| Capability | Means                                          | HTTP verb                           |
| ---------- | ---------------------------------------------- | ----------------------------------- |
| `create`   | Create a new object at this path               | `POST`/`PUT`                        |
| `read`     | Read the value                                 | `GET`                               |
| `update`   | Overwrite an existing value                    | `POST`/`PUT`                        |
| `patch`    | Partially modify                               | `POST`/`PUT` (merge)                |
| `delete`   | Delete                                         | `DELETE`                            |
| `list`     | List entries under a path                      | `LIST`/`GET ?list=true`             |
| `scan`     | Recursively list                               | `LIST`/`GET ?list=true` (recursive) |
| `sudo`     | Perform the action *as if* holding root        | any                                 |
| `deny`     | Explicitly deny (overrides any wildcard grant) | —                                   |

`deny` is special: it **takes precedence** over a broader wildcard grant. That's
your "allow everything except X" tool.

### Path globbing — the three patterns

```hcl
path "secret/data/myapp"   { capabilities = ["read"] }   # exact
path "secret/data/*"       { capabilities = ["read"] }   # prefix, one segment+
path "secret/data/zip-*"   { capabilities = ["read"] }   # glob within a segment
path "secret/data/+/teamb" { capabilities = ["read"] }   # "+" = any chars in ONE segment
```

| Pattern               | Matches                                          | Does NOT match              |
| --------------------- | ------------------------------------------------ | --------------------------- |
| `secret/data/*`       | `secret/data/a`, `secret/data/a/b`               | `secret/dataX`              |
| `secret/data/+/teamb` | `secret/data/foo/teamb`, `secret/data/bar/teamb` | `secret/data/foo/bar/teamb` |
| `secret/data/+/*`     | `secret/data/foo/anything/deep`                  | —                           |

> ⚠️ **Case sensitivity:** inbound request paths are canonicalized (lower-cased)
> before ACL checks, but **the paths you write in a policy are NOT**. If your
> engine is case-insensitive, write your ACL paths in canonical (lower-case)
> form, or the policy silently won't match.

### Templating — policies that react to identity

```hcl
path "secret/data/{{identity.entity.aliases.auth_userpass_xxx.metadata.username}}/*" {
  capabilities = ["read", "list"]
}
```

This is how you get "each user sees only their own folder" with one policy.

> 🔒 **2.6.0 hardened templating (GHSA-59w7-v8rr-pr4p).** A template value
> containing `+`, `*`, `/` or `,` is now **rejected by default** — because a
> malicious identity metadata value could otherwise escalate into a different
> path. The escape hatches `allow_wildcards_in_identity_templates`,
> `allow_slashes_in_identity_templates`, `allow_commas_in_identity_templates`
> and `allow_globs_in_identity_templates` re-enable the old behaviour.
> **Leave them off.** If a template breaks, fix the source data, don't enable
> the flag.

### Policy composition

A token's effective policy is the **union** of all attached policies, with
`deny` always winning. There's no "deny overrides allow" ordering — it's
pure union + explicit deny.

### Writing policies well

```hcl
# ❌ Bad: too broad
path "secret/*" { capabilities = ["create","read","update","delete","list","scan"] }

# ✅ Good: explicit, minimal, per-app
path "secret/data/myapp"        { capabilities = ["read"] }
path "secret/data/myapp/config" { capabilities = ["read","update"] }
path "secret/metadata/myapp"    { capabilities = ["read","list"] }
path "secret/delete/myapp"      { capabilities = ["read"] }   # metadata only
path "secret/undelete/myapp"    { capabilities = ["update"] }
path "secret/destroy/myapp"     { capabilities = ["update"] }
```

> 💡 **KV v2 needs four paths per secret**, not one. `data/`, `metadata/`,
> `destroy/`, `undelete/`. Forgetting `metadata/` breaks `bao kv metadata get`
> and version listing. Level 4 covers this in detail.

---

## 1.4 Tokens — identity, capability and time

### The token model

```
   Login (auth method)  ──▶  Token
                              ├── policies: ["app-readonly", "default"]
                              ├── TTL: 1h, renewable
                              ├── parent: <the token that created it>
                              ├── accessor: 6f1c...  (safe to store & log)
                              └── metadata: {username: "bob"}
```

Everything about access is on the token. Revoke the token → access gone.

### Token formats (2.7.1)

| Prefix | Example                           |
| ------ | --------------------------------- |
| `s.`   | `s.raPGTZdARXdY0KvHcWSpp5wWZIHNT` |
| `b.`   | `b.n6keuKu5Q6pXhaIcfnC9cFNd`      |
| `r.`   | `r.JaKnR2AIHNk3fC4SGyyyDVoQ9O`    |

Regex: `[sbr]\.[a-zA-Z0-9]{24,}`

> ⚠️ **Token internal structure is volatile.** Never write a script that parses
> the token string. Use the **accessor** instead.

### Service vs batch tokens

|                     | Service                         | Batch                  |
| ------------------- | ------------------------------- | ---------------------- |
| Stored on disk      | ✅                               | ❌ (encrypted blob)     |
| Renewable           | ✅                               | ❌                      |
| Revocable           | ✅                               | ❌ (just stops working) |
| Can create children | ✅                               | ❌                      |
| Can be root         | ✅                               | ❌                      |
| Has accessor        | ✅                               | ❌                      |
| Has cubbyhole       | ✅                               | ❌                      |
| Cost                | Heavy (multiple storage writes) | Light (no storage)     |

**Use case:** batch tokens for high-volume, short-lived, read-only automation
(they scale far better). Service tokens for everything else.

### Token hierarchy and orphans

When a token creates a token, the child is a **child**. Revoking the parent
revokes the whole tree. That is a security feature: you can't escape revocation
by minting grandchildren.

An **orphan token** has no parent — it is the root of its own tree. You need
this when a system issues tokens for other systems and must be able to revoke
just its own subtree.

```bash
# Orphan token
bao token create -policy=app-readonly -ttl=1h -orphan=true

# Revoke a subtree but keep the accessor's token
bao token revoke -accessor <accessor>
```

### Token accessors — the professional way to handle tokens

An accessor is a **safe handle** to a token. It can look up, renew, and revoke
the token — but it **cannot be used to authenticate**. So you can store
accessors in logs, databases and dashboards without leaking a credential.

```bash
# `-field=accessor` does NOT work here: the accessor lives under `auth`,
# and `-field` does not traverse into it. Use:
bao token create -policy=app-readonly -ttl=1h -format=json | jq -r .auth.accessor
# ...or for the token itself, `-field=token` works:
bao token create -policy=app-readonly -ttl=1h -field=token
```

> 💡 **Production pattern:** the service that mints tokens for other services
> stores the **accessor** keyed by job ID. When the job finishes, it revokes by
> accessor — instant, and no credential ever touched disk.

### TTLs, max TTLs, periodic tokens

* **TTL** — how long the token is currently valid.
* **Renew** — extend it. `bao token renew`.
* **Max TTL** — the hard ceiling on lifetime. Determined by:
  1. System `max_lease_ttl` (default `768h` = 32 days)
  2. The mount's `max_lease_ttl` (can override, longer or shorter)
  3. The auth method's suggested max (can only be *shorter*)
* **Explicit max TTL** on the token = absolute limit, wins over everything.
* **Periodic token** — TTL resets on every renewal. The only way (besides root)
  to have an effectively unlimited token, but it dies if you stop renewing. Good
  for long-lived services that must hold a DB connection pool.

```bash
bao token create -policy=app -ttl=1h -renewable=true -explicit-max-ttl=24h
bao token create -policy=app -period=24h          # periodic
```

### Batch tokens (2.7 has no batch token changes, but they're underused)

```bash
bao token create -policy=app-readonly -ttl=5m -batch=true
```

### The `default` policy

Every token gets the `default` policy attached automatically. It grants
`lookup` on `auth/token/lookup-self` and `renew-self`. If you ever see
"permission denied" on `bao token renew`, check that `default` wasn't removed
from the token.

---

## 1.5 Auth methods — proving who you are

An auth method takes a credential, verifies it against an internal or external
system, and returns a **token**.

| Auth method             | Best for                                        | Human/Machine | Built-in in 2.7.1?           |
| ----------------------- | ----------------------------------------------- | ------------- | ---------------------------- |
| `userpass`              | Dev, tiny setups, break-glass                   | Human         | ✅                            |
| `oidc`                  | **Your Keycloak** — browser login               | Human         | ✅                            |
| `jwt`                   | JWTs from any issuer (incl. GitHub Actions)     | Machine       | ✅                            |
| `approle`               | Machines/apps in VMs or containers              | Machine       | ✅                            |
| `kubernetes`            | Pods in K8s                                     | Machine       | ✅                            |
| `cert`                  | mTLS client certs                               | Machine       | ✅                            |
| `token`                 | The token store itself — **cannot be disabled** | —             | ✅ (always mounted)           |
| `ldap`                  | AD/LDAP                                         | Human         | ❌ **plugin now**             |
| `kerberos`              | AD/Kerberos                                     | Human         | ❌ **plugin now**             |
| `radius`                | Network devices                                 | Human         | ❌ **plugin now**             |
| `aws` / `azure` / `gcp` | Cloud IAM                                       | Machine       | ❌ **plugin now**             |
| `github`                | GitHub                                          | Human         | ❌ **plugin** (`auth-github`) |

### How a login works

```
 client                    OpenBao
   │                          │
   │  POST /v1/auth/userpass/login/bob
   │  {password: "..."}       │
   │─────────────────────────▶│
   │                          │─▶ userpass plugin verifies the password
   │                          │─▶ looks up user→policies mapping
   │                          │─▶ creates a token, attaches policies
   │  {auth: {client_token,  │◀│
   │   lease_duration,        │
   │   policies: [...]}}      │
```

The **mapping from external identity → policies** is where the real design work
happens. Two ways:

1. **Direct mapping** — the auth method's own config says "user `bob` gets
   policy `app-readonly`". Simple, brittle at scale.
2. **Identity groups** — create an OpenBao *entity* (an identity), an *alias*
   (that identity's login in a given auth method), and *groups* with policies.
   Then map the auth method's users to groups. This scales and is the right
   model for anything beyond a handful of people. (Level 3.)

### AppRole — the machine auth method you'll actually use

AppRole gives you two values: a `role_id` (like a username) and a `secret_id`
(like a password). Login with both, get a token.

```bash
bao auth enable approle

bao write auth/approle/role/myapp \
    secret_id_ttl=10m \
    secret_id_num_uses=1 \
    token_num_uses=0 \
    token_ttl=20m \
    token_max_ttl=1h \
    secret_id_bound_cidrs="10.0.0.0/8"

bao read -field=role_id auth/approle/role/myapp/role-id/role-id
bao write -f auth/approle/role/myapp/secret-id
```

Login:

```bash
bao write auth/approle/login role_id=... secret_id=...
```

**The security pattern** (this matters): the `role_id` is *not* secret. The
`secret_id` is. In a proper design, the `role_id` is baked into the app
image/config (it's not a secret), and the `secret_id` is **injected at deploy
time by a trusted party** (CI, an orchestrator, an operator). If a `secret_id`
is ever used twice, rotate it. `secret_id_num_uses=1` plus `secret_id_ttl=10m`
means a leaked secret_id is worthless after 10 minutes.

---

## 1.6 Secrets engines — storing, generating, encrypting

| Engine             | Does                                                           | Typical use                                      |
| ------------------ | -------------------------------------------------------------- | ------------------------------------------------ |
| **`kv` / `kv-v2`** | Stores arbitrary key/value, with versioning (v2)               | API keys, connection strings                     |
| **`transit`**      | Encrypt/decrypt/sign/verify as a **service**; keys never leave | App data at rest, envelope encryption            |
| **`pki`**          | Issues X.509 certificates; acts as a CA                        | Internal TLS everywhere, mTLS                    |
| **`database`**     | Creates **real** users in a DB, deletes them on revoke         | Dynamic Postgres/MySQL creds                     |
| **`totp`**         | Generates/validates TOTP codes                                 | Step-up MFA                                      |
| **`ssh`**          | Issues SSH certificates                                        | Replace `authorized_keys` with short-lived certs |
| **`cubbyhole`**    | Per-token private storage                                      | Stash a credential during a multi-step flow      |
| `identity`         | Identity store internals                                       | —                                                |
| `ldap`             | LDAP secrets                                                   | ❌ plugin in 2.7                                  |

### KV v1 vs KV v2 — always use v2

|                                  | KV v1 | KV v2                      |
| -------------------------------- | ----- | -------------------------- |
| Versioning                       | ❌     | ✅ (default 10 versions)    |
| Soft delete / undelete / destroy | ❌     | ✅                          |
| Check-and-Set (CAS)              | ❌     | ✅ (`cas` / `cas_required`) |
| Metadata separate from data      | ❌     | ✅                          |
| Storage overhead                 | Lower | Higher                     |

```bash
bao secrets enable -path=secret kv-v2
```

KV v2 stores data at `secret/data/<key>` and metadata at `secret/metadata/<key>`.
That's why policies need both paths.

### Transit — encryption as a service

Your app encrypts; OpenBao encrypts. The key **never leaves OpenBao**.

```bash
bao secrets enable transit
bao write transit/keys/myapp type=aes256-gcm96
bao write transit/encrypt/myapp plaintext=$(echo -n "hello" | base64)
# {"ciphertext":"vault:v1:..."}
```

`vault:v1:<base64>` — note the `v1` is the **key version**. Rotating the key
(`transit/keys/myapp/rotate`) keeps old ciphertext decryptable. That's the whole
point of key versioning.

### PKI — your internal CA

The production pattern is **offline root → online intermediate → short-lived leaves**:

```
offline root CA (air-gapped, 10-year cert)
        │ signs
        ▼
intermediate CA (in OpenBao, 1-year cert)  ← private key in OpenBao (or External Key / HSM in 2.7)
        │ signs
        ▼
leaf certs for apps (24h–7d, auto-renewed)
```

Short-lived leaves make revocation almost a non-issue: a stolen cert expires
before it's useful.

### Database — dynamic credentials

```bash
bao secrets enable -path=db database
```

OpenBao connects with a **privileged** account, then per-request:

1. Creates a unique username (`v-token-approle-xxx-2026-10-20`).
2. Creates a random password.
3. Sets `VALID UNTIL` = lease expiry.
4. Hands them out with a lease.
5. On revoke/expiry → `DROP` the role.

The privileged account only needs `CREATEROLE` (+ connect), never `SUPERUSER`.

---

## 1.7 Leases — how secrets die on schedule

```
  bao read db/creds/app
  → { "lease_id": "db/creds/app/...", "lease_duration": 3600 }
                    │
                    ├── renew:  bao lease renew -increment=3600 db/creds/app/...
                    └── revoke: bao lease revoke db/creds/app/...
```

* Every **dynamic secret** and every **service token** has a lease.
* When it expires, OpenBao revokes the secret (drops the DB user, etc.).
* **Prefix-based revocation** is a gift during an incident:

```bash
bao lease revoke -prefix auth/userpass/     # kill every userpass login
bao lease revoke -prefix db/creds/           # kill every dynamic DB cred
```

* The KV engine does **not** issue leases (static data), though it may report a
  duration.
* `increment` on renew is **from now**, not from the end of the current lease.

---

## 1.8 Audit devices — the ledger

Every request and every response is written to **every enabled audit device**.

```bash
# 2.7.1: audit devices are declared in the SERVER CONFIG, not via the API.
#         See §5.5 for the declarative `audit "file" "file" { ... }` stanza.
```

> ⚠️ **In OpenBao 2.7.1, audit devices cannot be created via the API by
> default.** `bao audit enable` returns *"cannot enable audit device via API;
> use declarative, config-based audit device management instead"*. Define the
> device in the **server config file** instead (see §5.5):
>
> ```hcl
> audit "file" "file" {
>   description = "Local audit log (declarative)."
>   options {
>     file_path = "/openbao/logs/audit.log"
>     mode      = "0600"
>     log_raw   = "false"
>   }
> }
> ```
>
> The temporary escape hatch is the `unsafe_allow_api_audit_creation` server
> option (togglable with `SIGHUP`).

The audit log is a structured record:

```json
{
  "type": "response",
  "auth": { "client_token": "hmac-sha256:...", "policies": ["app-readonly"] },
  "request": { "id": "...", "client_token": "hmac-sha256:...", "operation": "read",
               "path": "secret/data/myapp" },
  "error": "",
  "response": { "data": { "data": { "api_key": "hmac-sha256:..." } } },
  "auth": { "display_name": "token", "policies": ["app-readonly"] }
}
```

**Secrets are HMAC'd, not logged in plaintext.** OpenBao replaces sensitive values
with `hmac-sha256:<hex>` using a per-device key, so you can correlate values
across logs without exposing them. `log_raw = true` disables that — **never in
production**.

**These paths are NOT audited** (by design):

```
sys/init, sys/seal-status, sys/seal, sys/unseal, sys/leader, sys/health,
sys/storage/raft/bootstrap, sys/storage/raft/join
```

plus, if the listener allows it: `sys/metrics`, `sys/pprof/*`, `sys/in-flight-req`.

**Critical operational rule:** OpenBao considers a request successful if it can
log to **at least one** audit device. If *all* audit devices fail, **OpenBao
refuses to serve requests.** That's the correct fail-closed behaviour for a
security system — and it's why you must monitor the audit sink's disk space and
alert on audit failures.

**Run at least two audit devices** (e.g. a local file + a remote socket) so you
have redundancy *and* tamper-evidence.

---

## 1.9 Identity — entities, aliases, groups

The identity system is a graph, and it's how you scale authorisation.

```
  Entity (a person or machine, namespace-scoped)
    ├── Alias  (how it logs in: auth method + metadata)
    ├── Group  (a named bucket of entities)
    │     └── Policies
    └── Metadata
```

```bash
# Create an entity + alias
bao write identity/entity name="alice" \
    metadata=full_name="Alice Smith" \
    policies=app-readonly

bao write identity/entity-alias \
    name="alice" \
    canonical_id=$(bao read -field=id identity/entity/name/alice) \
    mount_accessor=$(bao auth accessor list -format=json | jq -r '.[]|select(.path=="auth/userpass/").accessor')
```

Groups:

```bash
bao write identity/group name=platform \
    policies=app-readonly,app-admin

bao write identity/entity/id/<id> \
    groups=platform
```

Then in the auth method, map a claim → group:

```bash
bao write auth/userpass/users/alice token_policies=app-readonly
# or for OIDC/JWT:
bao write auth/oidc/role/dev \
    user_claim=preferred_username \
    bound_claims=groups \
    claim_mappings=...
```

> 🔒 **Cross-namespace identity is off by default and should stay off.**
> `unsafe_cross_namespace_identity` exists only for Vault Enterprise compatibility
> and "allows for unconfined permission sharing." Do not enable it.

---

## 1.10 Namespaces — multi-tenancy in one instance

A namespace is a **mini-OpenBao** inside one instance. It has its own:

```
secret engines · auth methods · ACL/EGP/RGP policies · password policies
entities · identity groups · tokens · login paths
```

```bash
bao namespace create platform-team
export BAO_NAMESPACE=platform-team
bao secrets enable kv-v2
bao policy write mypolicy - <<'EOF'
path "secret/data/*" { capabilities = ["read","list"] }
EOF
```

Namespaces are **free** in OpenBao (since 2.3.1) — in HashiCorp Vault they're
Enterprise-only. That alone is often the reason to choose OpenBao.

**2.6.0 added namespace sealing:** you can give a namespace its own Shamir seal
and its own barrier keyring, so a tenant can revoke the *operator's* access to
their namespace without touching other tenants.

Naming rules: no trailing `/`, no spaces, and not one of
`.`, `..`, `root`, `sys`, `audit`, `auth`, `cubbyhole`, `identity`.

---

## 1.11 The `sys/` namespace — the control plane

Everything under `sys/` is OpenBao's own machinery. Learn these:

| Path                         | What it does                                              |
| ---------------------------- | --------------------------------------------------------- |
| `sys/health`                 | Health check (unauthenticated)                            |
| `sys/seal-status`            | Seal state, version (unauthenticated)                     |
| `sys/init`                   | Initialize the cluster (unauthenticated, once)            |
| `sys/seal` / `sys/unseal`    | Seal / unseal (unauthenticated, quorum-guarded)           |
| `sys/mounts`                 | List/enable/disable secret engines                        |
| `sys/auth`                   | List/enable/disable auth methods                          |
| `sys/policies/acl`           | ACL policy CRUD                                           |
| `sys/policies/egp`           | **E**ndpoint **G**overning **P**olicies (parameter rules) |
| `sys/policies/rgp`           | **R**ole **G**overning **P**olicies (time-bound access)   |
| `sys/audit`                  | Audit device CRUD                                         |
| `sys/config/state/sanitized` | Current config with secrets redacted                      |
| `sys/tools/hash`             | Hash arbitrary data (SHA-256 etc.)                        |
| `sys/tools/random`           | Generate cryptographically random bytes                   |
| `sys/capabilities-self`      | "What can I do on this path?"                             |
| `sys/capabilities`           | "What can *that token* do on this path?"                  |
| `sys/leases/lookup`          | Look up a lease                                           |
| `sys/leases/revoke`          | Revoke a lease or a prefix                                |
| `sys/quotas/config`          | Rate limits and lease-count limits                        |
| `sys/leader`                 | Who is the leader                                         |
| `sys/metrics`                | Prometheus metrics (if enabled)                           |
| `sys/wrapping/unwrap`        | Unwrap a response-wrapping token                          |
| `sys/external-keys`          | 2.7: map mounts to HSM/KMS-backed keys                    |
| `sys/workflows`              | 2.6: operator-defined multi-request workflows             |
| `sys/generate-root-token`    | 2.6+: **authenticated** root token generation             |

`sys/capabilities-self` is your best debugging friend:

```bash
# There is no `bao sys capabilities-self` CLI command — it is an API
# endpoint. Use the CLI equivalent, or call the API:
bao token capabilities <token> secret/data/myapp
# → read

curl -s -X POST -H "X-Vault-Token: $BAO_TOKEN" \
  -d '{"path":"secret/data/myapp"}' \
  "$BAO_ADDR/v1/sys/capabilities-self"
# → {"capabilities":["root"],"secret/data/myapp":["root"],...}
```

---

## 1.12 Agent and Proxy — the client-side daemons

`bao agent` and `bao proxy` are separate binaries that run **next to your
application** and handle authentication + caching for you.

|                   | `bao agent`                           | `bao proxy`                         |
| ----------------- | ------------------------------------- | ----------------------------------- |
| Purpose           | Auto-auth + render templates to files | Auto-auth + cache + local API       |
| Talks to OpenBao  | Yes                                   | Yes                                 |
| Talks to your app | No (writes files/env)                 | Yes (local HTTP API)                |
| Best for          | Sidecar, writing secrets to disk      | Any app that speaks the OpenBao API |

`bao agent` supports a `file` sink with templating, so your app reads
`/secrets/db_password` from disk and the agent keeps it fresh.

```hcl
pid_file           = "/tmp/bao-agent.pid"
vault { address = "https://openbao:8200" }

auto_auth {
  method "approle" {
    mount_path = "auth/approle"
    config = { role_id = "..." }
  }
  sink "file" {
    config = {
      path = "/secrets/token"
      mode = 0640
    }
  }
}

template {
  source      = "/secrets/db_password"
  destination = "/secrets/db_password"
  error_on_missing_key = true
  wait { min_duration = "5s" }
}
```

Level 7 wires this into Docker Compose for your FastAPI service.

---

## 1.13 The request lifecycle, end to end

```
  1. TLS handshake
  2. Listener accepts, HTTP request parsed
  3. Token extracted (X-Vault-Token header, or BAO_TOKEN)
  4. Router resolves path → mount → plugin
  5. Policy engine: token policies ∩ path capabilities  → allow / deny
  6. (if login) auth method plugin verifies credential
  7. Plugin executes → result
  8. Result passes through the barrier (decrypt)
  9. Audit device writes request+response  ← happens for every step
 10. HTTP response
```

If step 9 fails for *all* devices → **the request fails**. (Fail closed.)

---

## 1.14 Level 1 checkpoint

1. Explain the three keys (encryption / root / unseal) and how they chain.
2. What's the difference between unseal keys and recovery keys? Which one is
   useless if the KMS dies?
3. Write a policy that lets a token `read` `secret/data/myapp` but not list it.
4. Why does KV v2 need both a `data/` and a `metadata/` path in your policy?
5. When do you want a batch token instead of a service token?
6. What's the difference between a token and its accessor, and which is safe to
   write in a log?
7. Which paths are NOT audited, and what does that mean for your threat model?
8. What happens to OpenBao if all audit devices fail?

**Next → [Level 2: HANDS-ON.md](02-HANDS-ON.md)** — you build a real, working,
policy-controlled OpenBao in Docker from scratch.

---

## 1.15 Scratchpad

```
Barrier chain:    unseal share → root key → encryption key → plaintext
Seal types:       Shamir (default) | auto-unseal (KMS/transit) | static
Policy verbs:     create read update patch delete list scan sudo deny
Token prefixes:   s. (service)  b. (batch)  r. (recovery)
KV v2 paths:      <mount>/data/<key>  <mount>/metadata/<key>  <mount>/destroy/<key>
Unaudited paths:  sys/init sys/seal-status sys/seal sys/unseal sys/leader
                  sys/health sys/storage/raft/{bootstrap,join}
Default policy:   attached to every token (lookup-self + renew-self)
```
