# Level 0 — Foundations

> **Goal of this level:** you finish it able to explain to a colleague, in plain
> English, what OpenBao does, what problem it solves, what it explicitly does
> *not* do, and you have OpenBao running in Docker on your laptop.

---

## 0.1 The problem, stated brutally

Picture a normal enterprise codebase. Where do secrets live?

```
.env file          →  git-committed (oops), on every dev's laptop, in every image layer
K8s Secret         →  base64, NOT encrypted, visible to anyone with get-secret RBAC
CI/CD variables    →  masked in logs, but plaintext at rest in the CI vendor's DB
Config file        →  committed, rotated never
Hardcoded          →  in the git history forever
```

Every one of those is the same four problems:

1. **No expiry.** A leaked key from 2023 still works today.
2. **No attribution.** Who read the production DB password? The logs don't say.
3. **No blast-radius control.** The same key is in 40 services, so you can't rotate it.
4. **No revocation.** You need the app restarted to pick up a new value.

And a fifth, sneakier one:

5. **Static secrets scale linearly with risk.** Every replica of every service that
   holds a long-lived credential multiplies your attack surface.

**OpenBao attacks exactly this.** It is a *centralised, encrypted, policy-controlled,
audited* place where secrets live, plus a machine that can *mint short-lived
credentials on demand* so that step 5 stops being a problem.

---

## 0.2 What OpenBao actually is (and is not)

### It IS

* An **encrypted key/value + policy store** with an HTTP API.
* An **identity broker**: it logs users in against *your existing* IdP (Keycloak,
  LDAP, GitHub, Kubernetes, cloud IAM) and maps them to OpenBao policies.
* A **dynamic credential factory**: it creates real credentials in your database,
  your cloud IAM, your SSH, and then destroys them on a timer.
* A **certificate authority** (PKI) that issues and rotates internal TLS certs.
* An **encryption service** (Transit) so apps never hold a raw encryption key.
* An **audit ledger**: every request and response is written to a tamper-evident
  log you ship to a SIEM.

### It is NOT

* A general-purpose config store. Don't put non-secret config in it.
* A password manager for humans. It's for machines; humans get tokens from it.
* A database. It stores *small* things: passwords, keys, certs, connection strings.
* A replacement for your IdP. Keycloak stays Keycloak. OpenBao just trusts it.
* Automatically safe. **A secrets manager with bad policies is worse than no
  secrets manager**, because now everything routes through one place.

---

## 0.3 The one architectural diagram you need to remember

```
                    ┌──────────────────────────────────────────┐
   Humans ────────▶ │              OpenBao Server              │
   (browser/CLI)   │                                          │
                    │  ┌────────────┐   ┌──────────────────┐  │
   Machines ──────▶ │  │ Auth       │──▶│  Token           │  │
   (CI, k8s pod)   │  │ Methods    │   │  (policy + TTL)  │  │
                    │  └────────────┘   └────────┬─────────┘  │
                    │                            │            │
                    │  ┌────────────┐   ┌────────▼─────────┐  │      ┌──────────┐
                    │  │ Policies   │◀──│  Router / Core    │──┼─────▶│  Audit   │
                    │  │ (HCL)      │   │                   │  │      │ Devices  │
                    │  └────────────┘   │  ┌──────────────┐ │  │      └────┬─────┘
                    │                   │  │ Secrets      │ │  │           │
                    │                   │  │ Engines      │ │  │      ┌────▼─────┐
                    │                   │  │ (KV/PKI/...) │ │  │      │ Audit log│
                    │                   │  └──────┬───────┘ │  │      │ (SIEM)   │
                    │                   └─────────┼─────────┘  │      └──────────┘
                    │                             │            │
                    │                   ┌─────────▼─────────┐  │
                    │                   │  BARRIER          │  │
                    │                   │  (encrypt/decrypt)│  │
                    │                   └─────────┬─────────┘  │
                    └─────────────────────────────┼────────────┘
                                                  │
                                    ┌─────────────▼─────────────┐
                                    │  Storage Backend          │
                                    │  (Raft  or  PostgreSQL)   │
                                    │  — always encrypted —     │
                                    └───────────────────────────┘
```

**Read it bottom-up:**

1. **Storage holds only ciphertext.** If someone steals your Postgres disk or your
   Raft snapshot, they get encrypted blobs. Useless without the root key.
2. **The barrier** is the crypto engine that encrypts/decrypts everything crossing
   that boundary. It lives in memory and its key is protected by the *seal*.
3. **The seal** is the master secret. If it's Shamir, humans hold shares. If it's
   auto-unseal, a KMS/HSM holds it.
4. **The router** takes a request path, asks the **policy engine** "is this token
   allowed to do this to this path?", and if yes dispatches to the right
   **auth method** (to verify identity) or **secrets engine** (to get data).
5. **Every request and response is written to every enabled audit device.**
6. **Tokens** are the currency: they carry identity + policies + TTL.

Everything in OpenBao is a **path** and a **capability** on that path. That single
idea explains policies, plugins, namespaces, and why `sys/` is just another path.

---

## 0.4 Ten vocabulary words that make everything else obvious

Read this table twice. It's the densest value in the whole course.

| Word | Plain English | Where you see it |
|---|---|---|
| **Path** | A URL-ish string. `secret/data/myapp`, `sys/health`, `auth/userpass/login/bob`. | Everything. OpenBao is a virtual filesystem. |
| **Mount** | Attaching a plugin to a path prefix. `bao secrets enable -path=secret kv-v2` attaches "the KV engine" to `secret/`. | `bao secrets enable` / `bao auth enable` |
| **Token** | A session credential. Carries *which policies* and *how long*. Not a password — a lease. | `s.xxx` prefix |
| **Policy** | HCL rules: "this token may `read` on path X". **Deny by default.** | `bao policy write` |
| **Capability** | The verb: `create`, `read`, `update`, `patch`, `delete`, `list`, `scan`, `sudo`, `deny`. | Inside policies |
| **Lease** | A timer attached to a dynamic secret or service token. When it expires → secret revoked. | `lease_duration` in responses |
| **Seal / Unseal** | Locking / unlocking the master key. Sealed OpenBao serves almost nothing. | `bao status`, `bao operator unseal` |
| **Auth method** | A way to *prove who you are* (→ a token). `userpass`, `oidc`, `approle`, `jwt`, `kubernetes`. | `auth/` paths |
| **Secrets engine** | A way to *store, generate or encrypt* secrets. `kv`, `transit`, `pki`, `database`. | `secret/`, `pki/`, `transit/` paths |
| **Audit device** | A place every request/response gets written. `file`, `socket`, `syslog`, `http`. | `sys/audit/` |

Two more you'll meet fast:

| Word | Plain English |
|---|---|
| **Root token** | A token with the `root` policy. Can do anything. Treat like the nuclear key. |
| **Namespace** | An isolated mini-OpenBao inside one instance (multi-tenancy). Free in OpenBao. |

---

## 0.5 Threat model — what is OpenBao actually protecting you from?

This matters, because "security" without a threat model is just vibes.

**In scope (OpenBao defends against these):**

| Threat | Defence |
|---|---|
| Stolen disk / stolen DB backup | Barrier encryption; storage holds only ciphertext |
| Stolen laptop with `.env` | Secrets live server-side, not on the laptop |
| Insider with prod read access | Path-scoped policies, per-token TTLs, audit trail |
| Leaked key in a git repo | Rotation; and if you use the PKI, certs rotate automatically |
| Compromised service A reading service B's secret | Separate paths + separate policies per app |
| Long-lived credential abuse | Dynamic creds that die in an hour |
| "Who did it?" | Audit log, requester identity, source IP |
| Insider tampering with logs | Ship audit logs to a separate immutable store (SIEM/WORM) |

**Out of scope (you must handle these yourself):**

| Threat | Why OpenBao can't help |
|---|---|
| Someone with the **root token** | Root is root. It can read every secret. |
| Someone who **stole your unseal shares** | Threshold secrets: you need *k of n*. |
| A **malicious application** that legitimately has a token | Policies are your defence — write them well. |
| **Runtime memory scraping** of your app | A process with the secret in RAM can leak it. OpenBao can't stop that. |
| **Supply-chain compromise of your app** | If your app is malicious, its token is effectively the attacker's. |
| **Compromised host root** | A root attacker can read the unseal key from memory. Use encrypted swap + a bare-metal host. |
| **OpenBao itself having a bug** | Mitigated by patching. That's it. |

> **The honest truth:** OpenBao moves the blast radius from "N services × M
> secrets scattered everywhere" to "one hardened, audited, encrypted service." That
> is an enormous improvement. It is not magic.

---

## 0.6 Install it: Docker first (as you prefer)

You said you like Docker over manual installs. Agreed — and OpenBao is designed
for it. Two images matter:

| Image | Use |
|---|---|
| `openbao/openbao:2.7.1` | Standard. Has a shell, useful for debugging. |
| `openbao/openbao-distroless:2.7.1` | Production-hardened: `distroless/static`, contains **only** the `bao` binary. Smaller, fewer CVEs. (New in 2.6.0.) |

> ⚠️ **2.7.0 changed container behaviour you must know:**
> * The image now runs as the **`openbao` user**, not `root`. The entrypoint drops
>   privileges automatically. If you mounted host paths, they must be writable by
>   uid `100` / gid `1000` (check with `docker run --rm openbao/openbao:2.7.1 id`).
> * **All `VOLUME` instructions were removed** in 2.7.0 — you must declare your
>   own volumes.
> * Architecture-specific tags (`2.7.1-arm64`) are **not published**. Use the
>   multi-arch tag.

### 0.6.1 Dev mode (5 seconds, for learning)

```bash
docker run --rm -it \
  --name openbao-dev \
  -p 8200:8200 \
  -e BAO_DEV_ROOT_TOKEN_ID="dev-root-token" \
  -e BAO_DEV_LISTEN_ADDRESS="0.0.0.0:8200" \
  openbao/openbao:2.7.1 \
  server -dev
```

You should see:

```
==> OpenBao server configuration:
...
Unseal Key: ...
Root Token: dev-root-token
```

**`server -dev` is a learning tool only.** It is:
* in-memory storage (everything is lost on exit),
* unsealed automatically,
* root token printed in the logs and fixed to `dev-root-token`,
* running with a permissive setup.

Never ship `-dev`. In Level 2 we build the real thing.

While it's running, in another terminal:

```bash
export BAO_ADDR=http://127.0.0.1:8200
export BAO_TOKEN=dev-root-token

bao status          # -> Sealed: false, Initialized: true
bao secrets list
bao policy list
```

> 💡 **`server -dev` already mounts a KV v2 engine at `secret/`.** If you run
> `bao secrets enable -path=secret kv-v2` you'll get
> `path is already in use at secret/`. That's expected, not a bug.

### 0.6.2 Production-shaped single node (the "real" dev box)

Even locally, run it the way you'd run it in prod. This is the single biggest
habit difference between people who learn this tool and people who get paged.

```bash
mkdir -p ~/openbao-lab/{data,config,logs}
```

`~/openbao-lab/config/openbao.hcl`:

```hcl
ui            = true
api_addr      = "127.0.0.1:8200"
cluster_addr  = "127.0.0.1:8201"

storage "raft" {
  path   = "/openbao/data"
  node_id = "openbao-node-1"
}

listener "tcp" {
  address         = "0.0.0.0:8200"
  cluster_address = "0.0.0.0:8201"
  tls_disable     = true          # dev only! see Level 5 for production TLS
}
```

> ⚠️ **There is no `disable_mlock` option in OpenBao 2.x.** It was removed in
> **2.0.0** (the "mlock removal" RFC, GH-363) and the config parser will
> **refuse to start** if you leave it in:
>
> ```
> OpenBao has dropped support for mlock. Please remove the line "disable_mlock" = false
> from your config and disable or encrypt swap instead.
> ```
>
> OpenBao no longer calls `mlock()` at all. The hardening it now asks for is
> **swap**: disable swap for the OpenBao process, or encrypt it. Level 5 covers
> the full story (and the Docker equivalent is `--memory-swappiness=0`).

Run it:

```bash
docker run --rm -it \
  --name openbao-1 \
  -p 8200:8200 \
  -v ~/openbao-lab/data:/openbao/data \
  -v ~/openbao-lab/config:/openbao/config \
  openbao/openbao:2.7.1 \
  server -config=/openbao/config/openbao.hcl
```

### 0.6.3 The first interaction — read the *unauthenticated* surface

Before you authenticate, learn what OpenBao exposes to the world. This is a
**security exercise you should do on every system you deploy**.

```bash
curl -s http://127.0.0.1:8200/v1/sys/health | jq
curl -s http://127.0.0.1:8200/v1/sys/seal-status | jq
curl -s http://127.0.0.1:8200/v1/sys/init | jq        # {"initialized":false}
```

`sys/health`, `sys/seal-status`, `sys/init`, `sys/leader` are the intended
unauthenticated endpoints. They are *not* audited (see the audit chapter) and
they leak version + seal state. **Do not expose them to the internet.**

Version fingerprinting note: `sys/seal-status` returns `version` and `commit_date`.
That's useful for you and useful to an attacker. Restrict at the network layer.

### 0.6.4 The `bao` CLI without installing it

You don't need the binary on your host. Run it in a throwaway container that
shares the network with the server:

```bash
docker run --rm -it --network host \
  -e BAO_ADDR=http://127.0.0.1:8200 \
  openbao/openbao:2.7.1 \
  status
```

Or install it locally for convenience (a single static binary — no deps):

```bash
# Linux
wget -qO- https://github.com/openbao/openbao/releases/download/v2.7.1/openbao_2.7.1_linux_amd64.zip
unzip openbao_2.7.1_linux_amd64.zip && sudo install -m 0755 bao /usr/local/bin/bao
bao version
```

```powershell
# Windows (PowerShell) — you said Windows 11
winget install OpenBao.OpenBao     # or download the zip from the releases page
bao version
```

---

## 0.7 Your very first authenticated session

```bash
export BAO_ADDR=http://127.0.0.1:8200
export BAO_TOKEN=dev-root-token

# Who am I?
bao token lookup
```

```json
{
  "data": {
    "accessor": "...",
    "creation_time": 1758...,
    "display_name": "token",
    "entity_id": "",
    "expire_time": null,
    "id": "dev-root-token",
    "meta": { "username": "dev-root-token" },
    "orphan": true,
    "policies": ["root"],
    "renewable": false,
    "ttl": 0
  }
}
```

Note `policies: ["root"]` and `ttl: 0` (never expires). That is the *worst*
possible token to keep around, and in Level 5 you'll learn how to make sure it
only ever exists for the 90 seconds you need it.

---

## 0.8 The "3 requests" that teach you the whole product

Do these three in order. They are the spine of the entire course.

```bash
# 1. STORE a secret
bao secrets enable -path=secret kv-v2
bao kv put -mount=secret myapp db_password="s3cr3t" api_key="abc123"
bao kv get -mount=secret myapp
```

```json
{
  "data": {
    "data": { "api_key": "abc123", "db_password": "s3cr3t" },
    "metadata": { "created_time": "...", "version": 1 }
  }
}
```

```bash
# 2. CONTROL who can read it
bao policy write app-readonly - <<'EOF'
path "secret/data/myapp" {
  capabilities = ["read"]
}
EOF

# 3. GET a *temporary* credential, not a static one
bao secrets enable -path=db database
bao write db/config/postgres \
    plugin_name=postgresql-database-plugin \
    connection_url="postgresql://{{username}}:{{password}}@127.0.0.1:5432/app?sslmode=disable" \
    username="openbao_admin" \
    password="openbao_admin_pw" \
    allowed_roles="app"

bao write db/roles/app \
    db_name=postgres \
    creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT SELECT ON ALL TABLES IN SCHEMA public TO \"{{name}}\";" \
    default_ttl="1h" max_ttl="24h"

bao read db/creds/app
```

```json
{
  "data": {
    "username": "v-token-approle-abc123-2026-10-20",
    "password": "A1b2C3d4E5f6...",
    "lease_duration": 3600,
    "lease_id": "db/creds/app/..."
  }
}
```

**That third one is the whole point of OpenBao.** The password is for a database
user that did not exist a second ago and will be deleted when the lease expires
or is revoked. You never store it. You never rotate it. You just ask again.

---

## 0.9 Level 0 checkpoint

You are done with Level 0 when you can answer these without looking anything up:

1. What problem does OpenBao solve that a `.env` file does not?
2. What is stored on disk, and in what form?
3. What is a path? A capability? A lease?
4. What is the difference between an auth method and a secrets engine?
5. Which three things are **out** of OpenBao's threat model?
6. What is the difference between `server -dev` and a real server?

**Next → [Level 1: CONCEPTS.md](01-CONCEPTS.md)** — the full mental model, from
the barrier up to namespaces.

---

## 0.10 Scratchpad

```
OpenBao version taught:  2.7.1
BAO_ADDR (dev):          http://127.0.0.1:8200
Dev root token:          dev-root-token
First KV mount:          secret/  (kv-v2)
First policy:            app-readonly
Lab dir:                 ~/openbao-lab/
```

> 🔒 **From this point on, every `export BAO_TOKEN=...` in your terminal history
> is a liability.** Use `bao login` and the token helper, or `BAO_TOKEN` only in
> throwaway shells. Level 5 covers the professional workflow.
