# Module 01 — Foundations: Your First Production-Shaped OpenBao

> **Where we are.** You are the first platform engineer Meridian AI has hired
> since the previous engineer quit. Six weeks before they left, they committed
> a `.env` file containing the Gemini API key, the Postgres password, the
> Redis password, and the Keycloak client secret to Git. It is still in the
> history. You have been handed a laptop, a GitHub org, and a mandate to build
> Meridian AI's secret store properly, from zero, in a way that survives a
> security review.
>
> This module is the foundation. By the end of it you will have a running
> OpenBao 2.7.1 with durable storage, a Shamir-sealed root key, a documented
> break-glass recovery path, and a working answer to the question every
> engineer eventually asks: *"who can read the secrets, and what happens if
> they die?"*

**Status:** Every command in this module was executed against a live
OpenBao **v2.7.1** server (`a5db72cef75c24b920ade02065b18dd8eb666bac`,
committed 2026-10-01T15:32:54Z). Output blocks are transcripts, not
transcriptions from a blog post.

---

## 0. The 60-second version

If you read nothing else, read this table.

| Concept | One-line meaning | Why it exists |
|---|---|---|
| **Secret** | Any credential an app needs to work | API keys, DB passwords, client secrets |
| **OpenBao** | A server that stores secrets encrypted and hands them only to authenticated, authorized callers | One place to revoke, rotate, audit |
| **Storage** | The encrypted disk where secrets live (`pebbledb` here) | Durability across restarts |
| **Barrier key** | The master key that encrypts every value in storage | Nothing readable without it |
| **Root key** | The barrier key, before it is split into shares | The thing Shamir splits |
| **Seal** | The server is locked — it *cannot* decrypt anything | A stolen disk is useless |
| **Unseal key** | One **share** of the root key (Shamir) | N shares exist, K are needed |
| **Root token** | Unrestricted admin credential, no expiry | Bootstrap and break-glass only |
| **Token** | A scoped, expiring credential | What applications actually use |
| **Policy** | The ACL that decides what a token may do | Least privilege (Module 03) |
| **Mount** | An isolated path where one kind of secret lives | `ai/platform/` will hold KV v2 (Module 02) |
| **Lease** | A time-bound record of a credential | Automatic expiry, automatic revocation |
| **Audit device** | Writes every request to a tamper-evident log | "Who read the Gemini key?" |

**The one thing to internalize:** OpenBao is not a password manager with a
nice UI bolted on. It is a **cryptographic secret distribution system**. The
data on disk is encrypted with a key that does not exist in the server's
memory while the server is sealed. That single property is why the rest of
this module exists.

---

## 1. Why not just keep secrets in `.env` files?

Let's look at what Meridian AI has today. Not hypothetically — here is the
actual content of the file that is sitting in your Git history:

```bash
# meridian-ai/platform/.env   (committed 2026-08-14, still in git log)
GEMINI_API_KEY=AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr
DATABASE_URL=postgresql://meridian_app:Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK@postgres:5432/meridian_ai
REDIS_PASSWORD=Yb3mQ8vT1xW6rK4pL9zD2nF7gH5jA0sC4eU
KEYCLOAK_CLIENT_SECRET=meridian-ai-harness-client-secret-rotate-me
```

Now ask six uncomfortable questions about this file.

1. **Who can read it?** Everyone with read access to the repository. In a
   real org that is every engineer, every contractor, every auditor, and
   every CI job that clones the repo — including the people who have since
   left.
2. **Is it in git history?** Yes, permanently. `git log -p` still shows it.
   Deleting the file today does not remove it. The *only* fix is to rotate
   every one of those four credentials, which is exactly what you cannot do
   quickly, which is exactly why people don't.
3. **Can you rotate it?** Rotate means: find every deployment, edit a file,
   restart the service, pray. With four services and a rolling deploy, that
   is an afternoon and a small outage.
4. **Can you audit it?** No. There is no log. Ever. You cannot answer "did
   anyone read the Gemini key after the leak?" — you can only guess.
5. **Can you scope it?** No. The `ai-harness` service needs the Gemini key
   and the Keycloak client secret. It does not need the Postgres password.
   But the file hands it all four, and it hands the same four to
   `data-pipeline` and `secret-rotation-bot`.
6. **Does the app get it at runtime?** It reads it from disk at startup. The
   secret then lives in the container filesystem, in the process
   environment, in `/proc/<pid>/environ`, and in every core dump.

OpenBao is the answer to all six. Every "why would I even do this?" moment
in the next eight modules maps back to one of these six problems. Keep them
in your head as the *why*; the *how* is the rest of this module.

> **Production:** *Rotate first, migrate second.* Before you build anything,
> rotate the four credentials above at the source (Google AI Studio, Postgres,
> Redis, Keycloak). Migrating a leaked secret into a new system just moves
> the leak. The new secrets you mint for Meridian AI are what you will put
> in OpenBao in Module 02.*

---

## 2. The mental model

### 2.1 The architecture, drawn out

Here is the whole system in one picture. Read it left to right.

```
   you write a secret
          │
          ▼
  ┌──────────────────────────────────────────┐
  │  ai-harness  ──POST /v1/ai/platform/data/llm/gemini──┐
  └──────────────────────────────────────────┘             │
                                                            ▼
                                            ┌───────────────────────────┐
                                            │  OpenBao API             │
                                            │  1. authenticate (token)  │
                                            │  2. authorize  (policy)   │
                                            │  3. encrypt with BARRIER  │
                                            │     KEY, write ciphertext │
                                            └───────────────────────────┘
                                                            │
                                                            ▼
                                            ┌───────────────────────────┐
                                            │  storage (pebbledb)       │
                                            │  {"api_key":"AQBx...cipher│
                                            │   text..."}   ← garbage   │
                                            └───────────────────────────┘
```

Three properties fall out of that diagram:

- **The server can encrypt.** It holds the barrier key in memory.
- **The disk cannot read.** It holds only ciphertext.
- **A sealed server can do neither**, because sealing *destroys* the
  barrier key from the process's memory.

### 2.2 What "sealed" physically means

This is the part that confuses people, so let's be precise.

When OpenBao starts, it reads its storage and finds a **security barrier**.
The barrier is the master encryption key for the whole store. OpenBao
decrypts it with the unseal shares you supply, holds it in memory, and uses
it as the key for every value it stores.

**Sealing** means: OpenBao encrypts the barrier key again with a key it
generates *in memory*, throws that key away, and drops the unsealed barrier
key from the process.

The consequence is not "the API returns 403 for unauthorized users". The
consequence is:

> **The data is cryptographically unreadable.** Not "unauthorized" —
> *unreadable*. There is no code path that returns the plaintext, because
> the key needed to produce it no longer exists in the process.

This is why "sealed" is a security feature and not a feature flag. If someone
steals your Docker volume, they get ciphertext. If someone gets a memory
dump of a sealed process, they get ciphertext. The unseal shares are the
only thing that turns ciphertext back into secrets, and those live with
people, not on a disk.

You can watch the barrier appear in the server log. From the lab:

```
2026-10-21T16:33:23.107Z [INFO]  core: security barrier initialized: shares=3 threshold=2
2026-10-21T16:33:23.115Z [INFO]  core: post-unseal setup starting
2026-10-21T16:33:23.205Z [INFO]  core: post-unseal setup complete
```

And you can watch it disappear when you seal:

```
2026-10-21T16:36:52.379Z [INFO]  core: marked as sealed
2026-10-21T16:36:52.827Z [INFO]  core: vault is sealed
```

> ⚠️ **If you find a tutorial saying the server is "locked" when sealed:** *it
> is describing a login screen, which is a different concept. OpenBao's seal
> is a cryptographic lock on the storage, not an authorization state.*

### 2.3 The three credentials you will confuse in your first week

You will mix these up on day one. There are exactly three:

- **Unseal key** — one *share* of the barrier key. Unlocks the **storage**.
  Held by 3 separate people, offline, forever.
- **Root token** — an unlimited-lifetime **administrator credential**. Unlocks
  the **API**. Held by break-glass custodians, in a safe.
- **Token** — a **scoped, expiring** credential. Unlocks only what its policy
  allows. Held by applications, in memory, for minutes or hours.

A **lease** is not a fourth credential — it is the *record* OpenBao keeps
about a token so it knows when to expire it. The lease is what makes `ttl`
enforceable. You will see all three as real output in
[§7](#7-the-three-credentials-side-by-side).

---

## 3. Install it, production-shaped

### 3.1 The image and the pin

Meridian AI runs OpenBao in Docker, like everything else. The image is the
official one, pinned to an exact version:

```yaml
image: openbao/openbao:2.7.1
```

**Never `latest`.** `latest` means "whatever was pushed most recently", which
means your production cluster and your laptop can be running different
binaries, which means a bug report is unreproducible and a rollback is a
guess. Pin the version, and if you want supply-chain guarantees, pin the
digest instead of the tag.

### 3.2 `server -config=` versus the image default

The `openbao/openbao` image's default command is `server -dev`. Read that
carefully — it is the single most consequential detail in this section.

| | `-dev` (image default) | `server -config=...` (production-shaped) |
|---|---|---|
| Storage | `inmem` — gone when the process exits | `pebbledb` — durable |
| Sealed on start? | No, always unsealed | **Yes** — needs unseal keys |
| Unseal shares | 1, printed in the log | 3, threshold 2, printed once at init |
| Root token | Random, but printed to the log **and** saved to `~/.vault-token` | Random, printed once at init, then gone |
| Real init ceremony | No | Yes |
| Audit device | Off | On, declaratively |
| Production safe? | **Absolutely not** | Yes, with hardening |

Here is a real `-dev` server, running side by side with our production-shaped
one, so you can see the difference rather than take it on faith:

```console
$ bao status
Key             Value
---             -----
Seal Type       shamir
Initialized     true
Sealed          false
Total Shares    1
Threshold       1
Version         2.7.1
Commit Date     2026-10-01T15:32:54Z
Storage Type    inmem
Cluster Name    vault-cluster-3cdf3dc1
Cluster ID      30633af0-8102-91c3-ca5c-27b75937ab1d
HA Enabled      false
```

Compare with the production-shaped server from the same lab: `Storage Type
pebbledb`, `Total Shares 3`, `Threshold 2` — the full table is in
[§9.1](#91-bao-status--the-fields-that-matter).

And here is what `-dev` prints on startup — note the root token at the
bottom:

```console
$ grep -iE "root token|Storage:|vault is unsealed" dev-server.log
                 Storage: inmem
2026-10-21T17:05:06.742Z [INFO]  core: root token generated
2026-10-21T17:05:06.756Z [INFO]  core: vault is unsealed
and starts unsealed with a single unseal key. The root token is already
The unseal key and root token are displayed below in case you want to
Root Token: s.jZ2q1tFA0mnHoW1h79VZggwQ
```

The last line is the one that matters: a **random** `s.`-prefixed token,
printed once, on stdout. The two lines before it are the dev-mode banner
explaining where the unseal key and root token are displayed.

> ⚠️ **The dev root token is random in 2.7.1 — it is not `root`.** OpenBao
> 2.7.1's dev server generates a random root token and prints it on stdout.
> You only get the literal string `root` if you ask for it explicitly with
> `-dev-root-token-id=root`. **If you find a tutorial saying the dev root
> token is `root`, it is describing HashiCorp Vault's default, not
> OpenBao's.**
>
> The token is also written to the CLI's token helper file
> (`~/.vault-token`, mode `600`) unless you start the server with
> `-dev-no-store-token` — which is exactly what the container image's default
> command does, `server -dev -dev-no-store-token`. So in the image, the token
> exists only in the container's stdout. On a laptop, run `bao server -dev`
> and it lands in your home directory.

> **What breaks if you run `-dev` in production:**
>
> 1. **Every secret is lost on restart.** `inmem` means a container restart
>    wipes the store. Your platform comes back empty and every service fails
>    to find the Gemini key.
> 2. **The root token lands in a file and in your logs.** Anyone who can
>    read `~/.vault-token` or the container log is an administrator. That is
>    not a theoretical risk — see §3.4.
> 3. **There is no seal.** You never learn to unseal, so your first real
>    restart in production is an outage you have never rehearsed.
> 4. **There is no init ceremony**, so you never build the muscle memory of
>    handling unseal shares — the exact muscle you need at 3am.

The lab server in this module runs `server -config=`, exactly as production
will.

### 3.3 Storage: `pebbledb`, `raft`, and the removed `file` backend

OpenBao 2.7.1 offers two real storage backends:

| Backend | Use it for | Notes |
|---|---|---|
| `pebbledb` | Single node | New in 2.7.0. Durable, non-HA. **Refuses to run multi-node** (a deliberate split-brain guard). |
| `raft` | HA clusters | The integrated HA backend. Needs an odd number of voters. |

> ⚠️ **Changed in 2.7:** *the `file` storage backend was **removed** in
> v2.7.0.* Any tutorial — including most Vault-era material on the internet —
> that says `storage "file" { path = ... }` is out of date. OpenBao 2.7.1
> refuses to start with that config, and the error is unusually quiet:

```console
$ bao server -config=file-storage.hcl
2026-10-21T16:39:24.909Z [INFO]  proxy environment: http_proxy="" https_proxy="" no_proxy=""
unknown storage type file
```

Two lines, no stack trace, no mention of "removed". If you see this, you
are reading a pre-2.7 tutorial.

### 3.4 Publishing the port: loopback only

```yaml
ports:
  - "127.0.0.1:8200:8200"   # loopback only, on purpose
```

**Why not `8200:8200`?** Because an **uninitialized** OpenBao server has no
root token yet, and the init endpoint is unauthenticated by design. Anyone
who can reach the port can initialize the server and walk away with the root
token and the unseal shares.

This is not theoretical. Here is an uninitialized server, and a single
`curl` from a machine that should not have been able to talk to it:

```console
$ curl -s http://127.0.0.1:9401/v1/sys/init | jq
{
  "initialized": false
}
```

```console
$ curl -s -X POST http://127.0.0.1:9401/v1/sys/init -d '{"secret_shares":3,"secret_threshold":2}' | jq
{
  "keys": [
    "f055aff7f279e804c422df48649b92c7f15422f960a816b2344edd22298fc4b44e",
    "2d84e36fb4543491ae1bd3ef313da3d2cd302217fc52b922b88ad22be4fe04b2c8",
    "37fc5e0e5aa75de1c04eb1ea3b4b43073cda220b4ae809f67f2725ed8fc17e835c"
  ],
  "keys_base64": [
    "8FWv9/J56ATEIt9IZJuSx/FUIvlgqBayNE7dIimPxLRO",
    "LYTjb7RUNJGuG9PvMT2j0s0wIhf8UrkiuIrSK+T+BLLI",
    "N/xeDlqnXeHATrHqO0tDBzzaIgtK6An2fycl7Y/BfoNc"
  ],
  "root_token": "s.qpV7RxWH7uUiSiaOkOHAE44u"
}
```

That is a complete takeover of the secret store, in one HTTP request, with no
credentials. In production the OpenBao port belongs on a private network
segment, behind a TLS-terminating proxy, or on loopback with an SSH tunnel —
never on a routable interface where untrusted hosts can reach it.

> **What breaks if you publish on `0.0.0.0`:** *the first person to scan
> your subnet owns your secret store.* You will not notice, because the
> server looks perfectly healthy.

> **Production:** *Loopback + SSH tunnel, or a private VPC subnet with
> security groups, or mTLS. If you bind to a routable address, you must also
> enable TLS — and TLS on the cluster port is a separate topic that
> Module 09 covers properly.*

### 3.5 Container hardening: the four lines that matter

```yaml
cap_drop:
  - ALL
cap_add:
  - IPC_LOCK
security_opt:
  - no-new-privileges:true
user: "100:1000"
```

- **`cap_drop: ALL` + `cap_add: IPC_LOCK`** — `mlock` needs `IPC_LOCK`. It
  prevents OpenBao from swapping decrypted secrets to disk. Without it, the
  kernel's swap file becomes an unencrypted copy of your entire secret
  store, readable by any process that can read `/proc/*/mem` or the swap
  device. Dropping every other capability follows least privilege: the
  container has no business doing anything else.
- **`no-new-privileges:true`** — blocks setuid escalation inside the
  container. If a binary in your image is compromised, it cannot use a
  setuid bit to become root.
- **`user: "100:1000"`** — the `openbao/openbao` image runs as the
  non-root `openbao` user, **uid 100, gid 1000**. You do not need to
  override it; you need to *not break it*.

> ⚠️ **The `/openbao/file` quirk.** *The image chowns `/openbao/{config,logs,file}`
> at startup and **aborts if the chown fails** (`set -e`). It does **not**
> chown `/openbao/data`.* So if you mount a named volume at `/openbao/data`,
> it arrives root-owned and the server will not start. Mount the data
> volume at **`/openbao/file`** (one of the three directories the image
> creates) instead, and set `SKIP_CHOWN=true` with pre-owned host
> directories if you run truly non-root. Module 09 does the full container
> hardening pass; this is here so you do not lose an afternoon to it.

### 3.6 The configuration file we actually ran

Everything in this module was executed against a server started with this
config. It is the config the lab uses, with the port and paths adjusted.
**Your port is 8200** (the default); the transcript below was captured on a
separate instance, so the paths and port differ. Change the port and the two
paths to match your machine:

```hcl
ui            = true
api_addr      = "http://127.0.0.1:8200"
listener "tcp" {
  address     = "127.0.0.1:8200"
  tls_disable = true
}
storage "pebbledb" {
  path = "./data"
}
audit "file" "local-file" {
  description = "Local JSON audit log"
  options = {
    file_path = "./logs/audit.log"
    log_raw   = "false"
  }
}
telemetry {
  prometheus_retention_time = "30s"
  disable_hostname          = true
}
```

> Run this from inside the `lab/` directory of the course repo, so the
> relative `./data` and `./logs` paths resolve next to your config file.
> In Docker the same config uses `/openbao/file` and `/openbao/logs` — see
> `lab/config/openbao.hcl` in the repo for the container version and the
> reason those paths are named that way.

> ⚠️ **Config gotchas, all verified on 2.7.1:**
>
> | Mistake | What OpenBao 2.7.1 actually does |
> |---|---|
> | `storage "file" { path = ... }` | `unknown storage type file` — the backend was removed in 2.7.0 |
> | `api_addr = "127.0.0.1:8200"` (no scheme) | `Error parsing synthesized cluster address 127.0.0.1:9408: parse "127.0.0.1:9408": invalid URI for request` — it wants a full URL |
> | `audit "file" { file_path = ... }` (one label) | **Refuses to start:** `error loading configuration from ...: error parsing 'audit': audit.0: audit type must be specified` — 2.7 needs **two** labels **and** an `options` map |
> | `audit "file" "local-file" { file_path = ... }` (two labels, field inline) | Starts, but logs `[WARN] unknown or unsupported field file_path found in configuration at ...` and the field is **ignored** |
> | `disable_mlock = true` in HCL | `unknown or unsupported field disable_mlock` — it is a CLI **flag**, not a config key |
>
> The audit rules in 2.7 are a direct consequence of CVE-2025-54997 /
> HCSEC-2025-14: API-driven audit creation let an API-level admin write to
> arbitrary host files, breaking privilege separation. Audit devices are now
> **declarative only** — configured in the server config file, created
> before the server ever starts.

---

## 4. Initialize: the root key and Shamir's Secret Sharing

### 4.1 What `init` actually does

Initialization does three things, and only three things:

1. Generates the **root key** (the barrier key) — 32 bytes of randomness.
2. Splits it with **Shamir's Secret Sharing** into *N* shares, *K* of which
   are needed to reconstruct it.
3. Creates the **root token** — an unlimited-lifetime administrator
   credential.

Then it prints all of it, **once**, and throws it away. OpenBao does not
store the root key. That is the whole point.

```console
$ bao operator init -key-shares=3 -key-threshold=2
Unseal Key 1: Se/6XEz7UlG2IrFza40eiZ8GDQ9QO/3KNLz9nKw5Bcr+
Unseal Key 2: vnAUUf9ZXmJ7QRzfe6KUTPaUdS4yeLPttvjGoBNOFMQp
Unseal Key 3: gIk+5918yWt+9s0vXRruWhDblEOkg/5G3+TcXaZbExFb

Initial Root Token: s.ylB7Fg7H0zSg0XqCPATPuvWA

Vault initialized with 3 key shares and a key threshold of 2. Please securely
distribute the key shares printed above. When the Vault is re-sealed,
restarted, or stopped, you must supply at least 2 of these keys to unseal it
before it can start servicing requests.

Vault does not store the generated root key. Without at least 2 keys to
reconstruct the root key, Vault will remain permanently sealed!

It is possible to generate new unseal keys, provided you have a quorum
of existing unseal keys shares. See "bao operator rotate-keys" for more
information.
```

Read the last paragraph again: *"It is possible to generate new unseal keys,
provided you have a quorum of existing unseal keys shares."* That sentence
is the difference between a survivable mistake and a dead company.

Initialization can only happen once. Try it again on a live server and you
get:

```console
$ bao operator init -key-shares=3 -key-threshold=2
Error initializing: Error making API request.

URL: PUT http://127.0.0.1:9306/v1/sys/init
Code: 400. Errors:

* Vault is already initialized
```

You can ask without doing:

```console
$ bao operator init -status
Vault is initialized
```

### 4.2 Shamir's Secret Sharing, in plain language

You have a secret — the root key. You want to split it into *N* pieces so
that **any K pieces** rebuild it and **any K-1 pieces** tell an attacker
nothing at all.

That second property is the one people miss. With a 3-share / 2-threshold
split:

- **2 shares** → you can unseal.
- **1 share** → you learn *literally nothing* about the root key. Not
  "a little". Not "most of it". Nothing. This is a mathematical guarantee,
  not a heuristic: every possible root key is equally consistent with the
  share you hold.
- **3 shares** → you can also **rotate** the shares (§6.8).

With `3 shares, threshold 2` you have:

- A **2-of-3 quorum**: you can afford to lose one share (a laptop failure, a
  resignation, a fire).
- **No single point of failure**: no one person can unseal alone, so one
  compromised laptop is not a compromise of the store.
- **A collusion risk**: two people can unseal alone. That is the price of
  the quorum, and it is the reason shares go to *different* people, not to
  the same person's three password managers.

> **Trade-off:** *higher threshold = stronger against collusion, weaker
> against loss.* 5-of-7 tolerates losing two shares but needs five people
> in the same ceremony. 2-of-3 tolerates losing one share but needs two
> people. Pick the quorum your organization can actually staff at 3am.

### 4.3 Sizing shares for Meridian AI

| Organization | A defensible split | Who holds them |
|---|---|---|
| 3-5 engineers | 3 / 2 | CTO, SRE lead, one infra lead |
| ~20 engineers | 5 / 3 | CTO, SRE lead, security lead, infra lead, an off-site custodian |
| Enterprise / regulated | 7 / 5 | Add a second off-site custodian, split across two physical sites |

Rules that matter more than the numbers:

1. **One share per human.** Never two shares in the same person's custody.
2. **Different physical locations.** A share in the same data centre as the
   server protects you from nothing.
3. **Not in the same password manager as the root token.** They are two
   halves of the same key; keep them apart.
4. **Written down, sealed, in a safe.** Paper beats a laptop for a share
   that should survive a decade.
5. **The threshold must be *less than* the number of shares.** Always.

### 4.4 ⚠️ The recovery-key trap

This is the mistake that catches almost every new operator, including people
who have run HashiCorp Vault for years. Read it twice.

**In Shamir mode, OpenBao generates NO recovery keys.** Not "it is hidden",
not "it is optional" — the JSON field comes back `null` and the share count
comes back `0`. Here is the full JSON output of an init that explicitly
*asks* for recovery shares:

```console
$ bao operator init -key-shares=3 -key-threshold=2 -recovery-shares=5 -recovery-threshold=3 -format=json
{
  "unseal_keys_b64": [
    "Zbz9jzIWnILCF1E5Hd3vxqfjsDffGQSQfNJTbbdukYkv",
    "2OSXScygVChszWprBoLXZevhcH+q5ZfN12APBxBDhAPq",
    "PYRKN3RJlqIh0DVwO7wRDX0PJy6Ns6wdKk6o2r8EBesN"
  ],
  "unseal_keys_hex": [
    "65bcfd8f32169c82c21751391dddefc6a7e3b037df1904907cd2536db76e91892f",
    "d8e49749cca054286ccd6a6b0682d765ebe1707faae597cdd7600f0710438403ea",
    "3d844a37744996a221d035703bbc110d7d0f272e8db3ac1d2a4ea8dabf0405eb0d"
  ],
  "unseal_shares": 3,
  "unseal_threshold": 2,
  "recovery_keys_b64": null,
  "recovery_keys_hex": null,
  "recovery_keys_shares": 0,
  "recovery_keys_threshold": 0,
  "root_token": "s.jDMdri68EkgOECkaMEdxklEz"
}
```

And the one-liner that makes the point:

```console
$ bao operator init -key-shares=3 -key-threshold=2 -recovery-shares=5 -recovery-threshold=3 -format=json | jq .recovery_keys_b64
null
```

`null`. Not an empty array. Not a list of five keys. **`null`** — the
recovery keys were never generated, because Shamir mode has no recovery
key.

The CLI help text says so in as many words. This is the relevant excerpt
of `bao operator init -help` — quote it when someone asks you why:

```console
$ bao operator init -help
...
Auto Unseal Options:

  -recovery-pgp-keys=<keybase:user1, keybase:user2, ...>
      Behaves like -pgp-keys, but for the recovery key shares. This is only
      used in Auto Unseal mode.

  -recovery-shares=<int>
      Number of key shares to split the recovery key into. This is only used
      in Auto Unseal mode. The default is 5.

  -recovery-threshold=<int>
      Number of key shares required to reconstruct the recovery key. This is
      only used in Auto Unseal mode. The default is 3.
```

> **If you find a tutorial saying OpenBao "generates recovery keys at
> init":** *it is either describing HashiCorp Vault, or it is describing
> OpenBao in **auto-unseal mode** (Transit / KMS / HSM seal), where recovery
> keys do exist.*

**What this means operationally:**

- In **Shamir mode**, your **unseal keys ARE the recovery mechanism**. There
  is no second, independent quorum. There is no "break-glass backup" you
  are holding somewhere.
- If you lose too many unseal shares in Shamir mode, **the data is
  cryptographically unrecoverable**. By design. There is no back door, no
  support hotline, no vendor key.
- `generate-root` (§6) needs a **quorum of unseal shares**, not recovery
  keys. In Shamir mode, "generate root token" and "unseal" are gated by the
  same 2-of-3 quorum.

> **Production:** *This is exactly why Module 09 teaches Transit auto-unseal
> as the production answer. With an auto-unseal seal you get **real recovery
> keys** — a second, independent quorum that survives losing unseal shares —
> and the server comes back unsealed after a restart with nobody on site.
> Shamir + a human ceremony is the right answer for a small team; Shamir +
> nobody on site is a 3am page.*

### 4.5 Where the outputs go

Immediately after init, before you do anything else:

1. **Unseal shares** → one per named person, offline, in an envelope. Not in
   the repo, not in Slack, not in the same password manager as the root
   token.
2. **Root token** → a break-glass password manager (1Password, Bitwarden) or
   a sealed envelope in a safe. It is an unlimited-lifetime administrator
   credential; treat it like a nuclear launch key.
3. **The init output itself** → delete it from your shell history and your
   terminal scrollback.

The lab keeps them in a directory with `chmod 600` so you can run the
exercises; you should never keep them like that.

---

## 5. Seal and unseal

### 5.1 Seal it

```console
$ bao operator seal
Success! Vault is sealed.
```

Now the server is cryptographically closed. Here is `bao status` while
sealed:

```console
$ bao status
Key                Value
---                -----
Seal Type          shamir
Initialized        true
Sealed             true
Total Shares       3
Threshold          2
Unseal Progress    0/2
Unseal Nonce       n/a
Version            2.7.1
Commit Date        2026-10-01T15:32:54Z
Storage Type       pebbledb
HA Enabled         false
```

And the API is refusing to serve anything:

```console
$ bao read sys/mounts
Error reading sys/mounts: Error making API request.

URL: GET http://127.0.0.1:9306/v1/sys/mounts
Code: 503. Errors:

* Vault is sealed
```

```console
$ bao read sys/health
Error reading sys/health: Error making API request.

URL: GET http://127.0.0.1:9306/v1/sys/health
Code: 503. Errors:
```

The raw health endpoint still answers, and it is the one your monitoring
should watch, because it is available while sealed:

```console
$ curl -s http://127.0.0.1:9306/v1/sys/health
{"initialized":true,"sealed":true,"standby":true,"replication_performance_mode":"unknown","replication_dr_mode":"unknown","server_time_utc":1792600615,"version":"2.7.1"}
```

> **Production:** *alert on `sealed == true` in `sys/health`. A sealed
> OpenBao returns **503** on every business endpoint, so your uptime check
> on `/v1/ai/platform/data/llm/gemini` will fire at the same moment. But
> you want the alert to say "sealed, needs unseal ceremony", not "5xx from
> the secrets API".* Module 09 wires the Prometheus metrics for this.

### 5.2 Unseal it — one share at a time

The threshold is 2, so it takes two submissions. They do not have to be
adjacent, they do not have to be in order, and they do not have to arrive at
the same time. That is the whole point of a quorum: people can arrive at
different times.

```console
$ bao operator unseal <share 3>
Key                Value
---                -----
Seal Type          shamir
Initialized        true
Sealed             true
Total Shares       3
Threshold          2
Unseal Progress    1/2
Unseal Nonce       ae643808-6704-7afb-8fd0-982cd4fa24e3
Version            2.7.1
Commit Date        2026-10-01T15:32:54Z
Storage Type       pebbledb
HA Enabled         false
```

Note **Unseal Progress 1/2** and the **Unseal Nonce**. The nonce is what
binds the two submissions to the same unseal attempt; the server will reject
a share submitted under a stale nonce. If you seal and re-unseal, you get a
new nonce.

The second share completes it:

```console
$ bao operator unseal <share 1>
Key             Value
---             -----
Seal Type       shamir
Initialized     true
Sealed          false
Total Shares    3
Threshold       2
Version         2.7.1
Commit Date     2026-10-01T15:32:54Z
Storage Type    pebbledb
Cluster Name    vault-cluster-fcdbc432
Cluster ID      482546e4-34a1-dfc7-2a27-5aff92a13ed5
HA Enabled      false
```

`Sealed false`. The barrier key is back in memory, and the API serves
secrets again.

**Typo handling.** A malformed key is rejected before it ever reaches the
crypto, and the error tells you exactly what was wrong:

```console
$ bao operator unseal "BAD-KEY"
Error unsealing: Error making API request.

URL: PUT http://127.0.0.1:9306/v1/sys/unseal
Code: 400. Errors:

* 'key' must be a valid hex or base64 string
```

### 5.3 The one fact that will page you: a restart always re-seals

This is not a quirk. It is the design. The unsealed barrier key lives in
process memory; a new process has no memory of it. So the server comes back
**sealed** after every restart, every deploy, every crash, every node
reboot.

Let's prove it. Stop the server, start it again on the same data directory,
and look:

```console
$ kill $(cat server.pid)
$ bao server -config=./config/openbao.hcl &

$ bao status
Key                Value
---                -----
Seal Type          shamir
Initialized        true
Sealed             true
Total Shares       3
Threshold          2
Unseal Progress    0/2
Unseal Nonce       n/a
Version            2.7.1
Commit Date        2026-10-01T15:32:54Z
Storage Type       pebbledb
HA Enabled         false
```

**`Sealed true`.** The data is still there — `Initialized true`, storage
type `pebbledb` — but the server cannot read it until you unseal. And the
API confirms it:

```console
$ bao read sys/mounts
Error reading sys/mounts: Error making API request.

URL: GET http://127.0.0.1:9306/v1/sys/mounts
Code: 503. Errors:

* Vault is sealed
```

Unseal it again and everything is back — **including your root token**:

```console
$ bao operator unseal <share 1>
Key                Value
---                -----
Seal Type          shamir
Initialized        true
Sealed             true
Total Shares       3
Threshold          2
Unseal Progress    1/2
Unseal Nonce       1efb07dc-8519-e3d1-e65b-3c0bb170f04f
Version            2.7.1
Commit Date        2026-10-01T15:32:54Z
Storage Type       pebbledb
HA Enabled         false

$ bao operator unseal <share 2>
Key             Value
---             -----
Seal Type       shamir
Initialized     true
Sealed          false
Total Shares    3
Threshold       2
Version         2.7.1
Commit Date     2026-10-01T15:32:54Z
Storage Type    pebbledb
Cluster Name    vault-cluster-fcdbc432
Cluster ID      482546e4-34a1-dfc7-2a27-5aff92a13ed5
HA Enabled      false
```

The root token survived the restart, because it is stored *in* the storage —
encrypted by the barrier key — not in the process:

```console
$ bao token lookup -format=json | jq '.data | {id, path, policies, ttl, expire_time}'
{
  "id": "s.FZVXG2YTSoYkWmarDVZ1BvOn",
  "path": "auth/token/root",
  "policies": [
    "root"
  ],
  "ttl": 0,
  "creation_ttl": 0,
  "expire_time": null
}
```

> **What breaks if nobody has the unseal shares:** *the company is dead.*
> Not "degraded" — dead. The data is not encrypted with a password you can
> change; it is encrypted with a key that only exists as a mathematical
> function of the shares. Below the threshold, there is no brute force. There
> is no vendor. There is no reset button. **The data is unrecoverable.**
>
> This is why §4.3's rules are not bureaucracy. And it is why "we'll just
> keep the shares in the same team's password manager" is a *bad* plan: it
> protects against a stolen laptop and does nothing against a departing
> employee who takes the whole vault with them.

---

## 6. Break-glass: generating a new root token

### 6.1 The scenario

Meridian AI's root token leaked. A former contractor still has it. You
cannot simply *rotate* the root key (`rotate-keys`), because that would
invalidate every unseal share your team holds — and re-distributing shares
to five people is a two-week ceremony you cannot start while the store is
compromised.

`generate-root` solves exactly this: it uses your **unseal quorum** to
authorize a **brand-new root token**, without touching the root key and
without invalidating a single share.

### 6.2 Step 1 — generate a one-time password

```console
$ bao operator generate-root -generate-otp
vrbbBHGZ6YOq3WVgFaLsLH9AqI
```

That is the *entire* output. 26 characters, no label, no table.

> **Gotcha #1 — the OTP capture.** *The CLI prints the bare string. If you
> write `| grep OTP | awk '{print $2}'` you get an empty string, and the
> failure surfaces three steps later as a baffling 400. Capture it with
> `| tail -1`.*

Here is that empty string, for real:

```console
$ echo "[$(bao operator generate-root -generate-otp | grep OTP | awk '{print $2}')]"
[]                       <-- empty: there is no "OTP" field in the output to grep for

$ bao operator generate-root -generate-otp | tail -1
Kls45ELqYpI6s1djbyaARiMmNf
```

**What the OTP is for:** the generated root token is XORed with the OTP
before it is returned to you. If the response is captured in a proxy log, a
shell history file, or a CI log, an attacker still cannot reconstruct the
token without the OTP. The server stores only a *hash* of the OTP, so the
server cannot reconstruct it either. Both halves are needed, and you need
both to decode.

### 6.3 Step 2 — start the attempt

```console
$ bao operator generate-root -init -otp="vrbbBHGZ6YOq3WVgFaLsLH9AqI"
Nonce         fd5ec9e8-3e9f-9697-8177-b5d3ff01dcfb
Started       true
Progress      0/2
Complete      false
OTP Length    26
```

> **Gotcha #2 — the nonce.** *The nonce is returned here and it is required
> on **every** subsequent call in this attempt. The CLI does **not**
> auto-carry it.* Submit a share without it and you get:
>
> ```console
> $ bao operator generate-root -otp="vrbbBHGZ6YOq3WVgFaLsLH9AqI" "<share 1>"
> Missing nonce value: specify it via the -nonce flag
> ```
>
> Save the nonce. If you lose it, cancel the attempt and start over:
>
> ```console
> $ bao operator generate-root -cancel
> Success! Root token generation canceled (if it was started)
> ```

The OTP must be **exactly 26 characters**. A short one is rejected:

```console
$ bao operator generate-root -init -otp="short"
Error initializing root generation: Error making API request.

URL: PUT http://127.0.0.1:9306/v1/sys/generate-root-token/attempt
Code: 400. Errors:

* OTP string has incorrect length
```

You can inspect an in-flight attempt at any time without submitting
anything:

```console
$ bao operator generate-root -status
Nonce         fd5ec9e8-3e9f-9697-8177-b5d3ff01dcfb
Started       true
Progress      0/2
Complete      false
OTP Length    26
```

### 6.4 Step 3 — submit the shares

```console
$ bao operator generate-root -nonce="fd5ec9e8-3e9f-9697-8177-b5d3ff01dcfb" -otp="vrbbBHGZ6YOq3WVgFaLsLH9AqI" "<share 1>"
Nonce       fd5ec9e8-3e9f-9697-8177-b5d3ff01dcfb
Started     true
Progress    1/2
Complete    false
```

```console
$ bao operator generate-root -nonce="fd5ec9e8-3e9f-9697-8177-b5d3ff01dcfb" -otp="vrbbBHGZ6YOq3WVgFaLsLH9AqI" "<share 2>"
Nonce            fd5ec9e8-3e9f-9697-8177-b5d3ff01dcfb
Started          true
Progress         2/2
Complete         true
Encoded Token    IRstGgk+BHQhJ10bai44BiJUJncGXQMrIFk
```

> **Gotcha #3 — the field name.** *The field is **`Encoded Token`** — two
> words, and it is field number 3 on the line. `awk '/^Encoded Root Token/`
> matches nothing, and `awk '/^Encoded Token/{print $2}'` captures the
> literal word "Token". Use `$3`.*

Also note: **the attempt is consumed on completion.** To re-read the
encoded token you must start a fresh `-init` with a fresh OTP.

### 6.5 Step 4 — decode with the same OTP

```console
$ bao operator generate-root -decode="IRstGgk+BHQhJ10bai44BiJUJncGXQMrIFk" -otp="vrbbBHGZ6YOq3WVgFaLsLH9AqI"
s.jwafE6uTeQ9BbVT6c5OetZM3
```

That is a brand-new root token. It works:

```console
$ BAO_TOKEN=s.jwafE6uTeQ9BbVT6c5OetZM3 bao token lookup -format=json | jq '.data | {id, path, policies, ttl, creation_ttl, expire_time}'
{
  "id": "s.jwafE6uTeQ9BbVT6c5OetZM3",
  "path": "auth/token/root",
  "policies": [
    "root"
  ],
  "ttl": 0,
  "creation_ttl": 0,
  "expire_time": null
}
```

**Use the same OTP you started with.** A mismatched OTP does not error — it
produces a *plausible-looking* string, because the operation is a
position-wise XOR. Here is a real capture, with the wrong OTP differing from
the right one in exactly **one character** (the last):

```console
$ bao operator generate-root -decode="EUYtIiUoOiklFRk+HAhJGnELIiEEPA0icyo" -otp="bhdShjyQhdqLyaps7RUGgxCh0"
s.IqMBCxMqhrei9iFYwfcDNJCF

$ bao operator generate-root -decode="EUYtIiUoOiklFRk+HAhJGnELIiEEPA0icyo" -otp="bhdShjyQhdqLyaps7RUGgxCh0X"
s.IqMBCxMqhrei9iFYwfcDNJCr
```

Look at those two lines very carefully. The wrong OTP produced a string that
**differs from the right answer in exactly one character** — and it **still
starts with `s.`**. It still looks like a token. It is 26 characters of the
right shape and one byte wrong.

> ⚠️ **Never validate a decoded root token by looking at it.** A one-character
> OTP typo produces a one-character corruption, and there is no way to tell
> from the string alone. The only real check is to **use the token**:
>
> ```console
> $ BAO_TOKEN=s.IqMBCxMqhrei9iFYwfcDNJCr bao token lookup
> Error looking up token: Error making API request.
>
> URL: GET http://127.0.0.1:9306/v1/auth/token/lookup-self
> Code: 403. Errors:
>
> * 1 error occurred:
> 	* permission denied
> ```
>
> A corrupted token is simply not a token — the server has no record of it,
> so it answers 403. The good one answers with the real thing:
>
> ```console
> $ BAO_TOKEN=s.IqMBCxMqhrei9iFYwfcDNJCF bao token lookup
> Key                 Value
> ---                 -----
> accessor            qbE2x7gonMH3UbZhbRMHd6cz
> creation_time       1792611468
> creation_ttl        0s
> display_name        root
> entity_id           n/a
> expire_time         <nil>
> explicit_max_ttl    0s
> id                  s.IqMBCxMqhrei9iFYwfcDNJCF
> meta                <nil>
> num_uses            0
> orphan              true
> path                auth/token/root
> policies            [root]
> ttl                 0s
> type                service
> ```
>
> `display_name root` and `policies [root]` — that is what a real root token
> looks like. **If the lookup 403s, you used the wrong OTP.** Start the whole
> attempt over with a fresh `-generate-otp`; the attempt is consumed on
> completion, so there is no way to re-decode the same encoded token.
>
> This matters more than it looks. A break-glass root token that "looks
> right" but is one byte wrong is an outage *at the worst possible moment* —
> and the symptom is a 403, not a clear "wrong OTP" message. Make the
> verification step part of the script, not something you do when you
> remember.

### 6.6 The permission requirement (this bites in production)

`generate-root` calls the **authenticated** `/sys/generate-root-token/*`
endpoints (added in OpenBao 2.6, replacing Vault's unauthenticated
`/sys/generate-root/*`). Those endpoints require **`sudo`**. A token
without `sudo` gets a flat 403:

```console
$ BAO_TOKEN=<a token with only the "default" policy> bao operator generate-root -init -otp="vrbbBHGZ6YOq3WVgFaLsLH9AqI"
Error initializing root generation: Error making API request.

URL: PUT http://127.0.0.1:9306/v1/sys/generate-root-token/attempt
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

```console
$ BAO_TOKEN=<a token with only the "default" policy> bao operator generate-root -status
Error getting root generation status: Error making API request.

URL: GET http://127.0.0.1:9306/v1/sys/generate-root-token/attempt
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

> **If you find a tutorial calling the unauthenticated `/sys/generate-root`
> endpoint:** *it is describing HashiCorp Vault. OpenBao 2.6+ deprecated the
> unauthenticated endpoints, and 2.7's `bao operator generate-root` uses the
> authenticated, `sudo`-gated ones.*

This is also the reason `generate-root` needs a **working token** at all —
which creates a chicken-and-egg problem: you need *some* valid token to
mint a new root token. In practice that token is the existing root token
(the leak scenario) or a token with the `root` policy. If you have lost
*both* the root token and your unseal shares, you are out of options, and
that is by design.

### 6.7 The complete copy-paste script

This is the script you will actually use during an incident. It was executed
end to end in the lab and it works:

```bash
#!/usr/bin/env bash
# Meridian AI — break-glass root token generation, end to end.
# Requires: BAO_ADDR, BAO_TOKEN (a sudo-capable token), and 2 of 3 unseal shares.
set -euo pipefail

UNSEAL_KEY_1="${UNSEAL_KEY_1:?set UNSEAL_KEY_1}"
UNSEAL_KEY_2="${UNSEAL_KEY_2:?set UNSEAL_KEY_2}"

# 1. One-time password. The CLI prints ONLY the bare 26-char string.
OTP=$(bao operator generate-root -generate-otp | tail -1)
echo "[1/6] OTP captured (${#OTP} chars)"

# 2. Start the attempt. The nonce comes back here and is required from now on.
INIT_OUT=$(bao operator generate-root -init -otp="$OTP")
NONCE=$(printf '%s\n' "$INIT_OUT" | awk '/^Nonce/{print $2}')
if [ -z "$NONCE" ]; then
  echo "could not read the nonce; aborting" >&2
  exit 1
fi
echo "[2/6] attempt started, nonce=$NONCE"

# 3. Submit each share. The nonce MUST be passed on every call.
bao operator generate-root -nonce="$NONCE" -otp="$OTP" "$UNSEAL_KEY_1" >/dev/null
echo "[3/6] share 1 of 2 accepted"

OUT=$(bao operator generate-root -nonce="$NONCE" -otp="$OTP" "$UNSEAL_KEY_2")
echo "[4/6] share 2 of 2 accepted"

# 4. The output field is "Encoded Token" (two words), field number 3.
ENC=$(printf '%s\n' "$OUT" | awk '/^Encoded Token/{print $3}')
if [ -z "$ENC" ]; then
  echo "could not read the encoded token; aborting" >&2
  exit 1
fi

# 5. Decode with the SAME OTP.
NEW_TOKEN=$(bao operator generate-root -decode="$ENC" -otp="$OTP" | tr -d '\r' | tail -1)
echo "[5/6] new root token minted"

# 6. VERIFY it. A wrong-OTP decode produces a plausible-looking string that
#    differs from the real token in a single character — it still starts with
#    "s." and it still has the right length. The ONLY way to know is to use it.
if ! BAO_TOKEN="$NEW_TOKEN" bao token lookup -field=display_name 2>/dev/null | grep -qx root; then
  echo "the new token did not authenticate - wrong OTP; start over" >&2
  exit 1
fi
echo "[6/6] new root token verified (display_name: root)"

echo
echo "NEW ROOT TOKEN: ${NEW_TOKEN}"
```

Its real output:

```console
$ ./breakglass.sh
[1/6] OTP captured (26 chars)
[2/6] attempt started, nonce=df1e1451-015f-fecc-ff34-8e50745a9048
[3/6] share 1 of 2 accepted
[4/6] share 2 of 2 accepted
[5/6] new root token minted
[6/6] new root token verified (display_name: root)

NEW ROOT TOKEN: s.QGAG9JhXSTVl3AgBk5uoUteY
```

Four defensive details are worth noticing, because each one corresponds to a
real failure mode:

- `| tail -1` on the OTP (gotcha #1).
- `awk '/^Nonce/{print $2}'` on the **init** output — and a hard `exit 1`
  if the nonce is empty, so you never proceed into a doomed attempt.
- `awk '/^Encoded Token/{print $3}'` on the **share** output (gotcha #3),
  with the same guard.
- **Step 6 — actually use the token.** A wrong-OTP decode yields a string
  that looks perfect and is one character wrong (§6.5). The only way to
  know is `bao token lookup`; the script does it for you and aborts if the
  token does not authenticate.

### 6.8 What `generate-root` does **not** do

| Question | Answer |
|---|---|
| Does it rotate the root key? | **No.** Your existing unseal shares stay valid. |
| Does it invalidate the old root token? | **No.** Revoke it yourself: `bao token revoke <old-token>`. |
| Does it need a quorum of *recovery* keys? | Only with `-recovery-token`. In Shamir mode, it needs unseal shares. |
| Can it be used to change the number of shares? | No. That is `bao operator rotate-keys`. |

And the command you *actually* want when shares have been compromised:

```console
$ bao operator rekey -help
Usage: bao operator rekey [options] [KEY]

  WARNING: this method is deprecated, please use:
    $ bao operator rotate-keys
  instead.

  Generates a new set of unseal keys. This can optionally change the total
  number of key shares or the required threshold of those key shares to
  reconstruct the root key. This operation is zero downtime, but it requires
  that the OpenBao instance is unsealed and a quorum of existing unseal keys
  are provided.
```

Note: `rekey` is **deprecated** in 2.7.1 in favour of `bao operator
rotate-keys`. And note the price: **rotating the shares invalidates every
old share immediately**. If you rotate and then discover you cannot reach
two of the new share holders, you have bricked the store. Rotate only when
you have all the new shares physically in hand.

> **Production:** *Write the break-glass runbook before you need it. Two
> named custodians, the script in a password manager, the shares in a safe,
> and a quarterly drill. A drill you have run is worth ten runbooks you have
> read.*

---

## 7. The three credentials, side by side

Now that you have all three in your hands, look at them again — this time as
real output.

**The root token** — unlimited, no expiry, `policies [root]` (from §5.3):

```console
$ bao token lookup -format=json | jq '.data | {id, path, policies, ttl, creation_ttl, expire_time}'
{
  "id": "s.FZVXG2YTSoYkWmarDVZ1BvOn",
  "path": "auth/token/root",
  "policies": [
    "root"
  ],
  "ttl": 0,
  "creation_ttl": 0,
  "expire_time": null
}
```

**A scoped, expiring token** — the shape an application should use:

```console
$ bao token create -policy=default -ttl=10m -orphan -field=token
s.GICL4GOw6Bj9Pc9KzKxKHe8J

$ BAO_TOKEN=s.GICL4GOw6Bj9Pc9KzKxKHe8J bao token lookup
Key                 Value
---                 -----
accessor            dxrPOcnj3fuKncjQeFAzHoiV
creation_time       1792600659
creation_ttl        10m
display_name        token
entity_id           n/a
expire_time         2026-10-21T16:47:39.137516113Z
explicit_max_ttl    0s
id                  s.GICL4GOw6Bj9Pc9KzKxKHe8J
issue_time          2026-10-21T16:37:39.137529558Z
meta                <nil>
num_uses            0
orphan              true
path                auth/token/create
policies            [default]
renewable           true
ttl                 6m3s
type                service
```

Read the difference aloud: `ttl 0s` and `expire_time <nil>` for the root
token, versus `creation_ttl 10m` and a real `expire_time` for the scoped
one. **The root token never expires. The scoped token always does.**

**The lease** is the record behind that `expire_time`. When the lease
expires, OpenBao revokes the token server-side. Nobody has to remember to
do it. You can list the live lease prefixes and the token accessors:

```console
$ bao list sys/leases/lookup
Keys
----
auth/

$ bao list auth/token/accessors
Keys
----
5xkFaE2b7rl8DUixQx8HmzPj
Ji7a9JWLw9fDgmAIZnefJ45f
dxrPOcnj3fuKncjQeFAzHoiV
s725SBBREBvsaktIiXri9MG8
```

(Module 04 covers the full lease lifecycle and the 2.7 lease-endpoint
changes. For now the only thing to take away is that **tokens are leases
with an expiry, and OpenBao enforces the expiry for you**.)

**The unseal key** is not a token at all. You cannot put it in a
`Authorization` header, you cannot scope it, you cannot rotate it
individually. It is a share of a mathematical secret, and it unlocks the
*store*, not the *API*.

| | Unseal key | Root token | Scoped token |
|---|---|---|---|
| Type of thing | Cryptographic share | Bearer credential | Bearer credential |
| Presented to | `bao operator unseal` | `X-Vault-Token` header | `X-Vault-Token` header |
| Scope | None — it unlocks everything | Everything | Policy-defined |
| Lifetime | Forever | Forever | `creation_ttl`, e.g. 10m |
| Stored in | Envelopes / safe | Password manager | The application's memory |
| Needed by | Humans, in a ceremony | Break-glass custodians | Machines, continuously |
| Fits in a lease? | No | No (it is the parent) | Yes |

> **Production:** *The root token should exist in exactly two places: a
> break-glass password manager and a sealed envelope. If you find yourself
> putting a root token in a `.env` file, in CI variables, or in a
> Kubernetes Secret, you have reintroduced the problem this whole course
> exists to solve.*

---

## 8. The GUI tour

The OpenBao UI is a genuine production tool, not a toy. You will use it for
onboarding a colleague, for one-off reads during an incident, and for
showing a security auditor what a secret store actually looks like.

> **How this section was verified.** *The UI is a JavaScript single-page
> app, so "clicking through" is not reproducible in a terminal. Everything
> below was verified two ways: (a) by reading the **nav component
> definitions out of the shipped UI bundle** (`/ui/assets/vault.js`), which
> contain the literal menu labels and route names, and (b) by hitting the
> **API endpoints that back each screen** and recording the HTTP status
> codes. Where a screen needs a secret engine to exist, that is stated.*
>
> The exact places to look if you want to check this yourself:
>
> ```bash
> curl -s http://127.0.0.1:8200/ui/ | grep -oE 'assets/[a-zA-Z0-9._-]+\.js'
> curl -s http://127.0.0.1:8200/ui/assets/vault.js \
>   | grep -o 'vault\.cluster\.[a-z.]*' | sort -u
> ```
>
> The sidebar templates live in that bundle as
> `vault/components/sidebar/nav/cluster.hbs` (the top level),
> `.../nav/access.hbs` (the **Access** groups), `.../nav/tools.hbs` (the
> **Tools** list) and `.../nav/policies.hbs`. The **Tools** entries are
> generated from a helper that returns
> `["wrap","lookup","unwrap","rewrap","random","hash"]`, and the UI
> capitalises them — which is why the menu says **Wrap**, not **Wrap Data**.

### 8.1 Signing in

Open <http://127.0.0.1:8200/ui> and you land on the **Authenticate** page
("Sign in to OpenBao"). It has a **Method** dropdown (which auth method to
use) and a **Token** field. To sign in with the root token, leave the method
on the token option and paste the root token.

Verify the UI is actually served:

```console
$ curl -sI http://127.0.0.1:9306/ui
HTTP/1.1 307 Temporary Redirect
Cache-Control: no-store
Content-Type: text/html; charset=utf-8
Location: /ui/
Strict-Transport-Security: max-age=31536000; includeSubDomains
Date: Wed, 21 Oct 2026 16:38:04 GMT
```

A `307` to `/ui/` is the normal, healthy response for `/ui`.

### 8.2 The main navigation

The left sidebar's top level is titled **OpenBao** and contains exactly
these entries:

| Menu path in the UI | What is on it | UI route |
|---|---|---|
| **Secrets engines** | Every enabled secret engine (mount). Click one to browse its secrets. | `vault.cluster.secrets` |
| **Access** | The identity and administration section (see below) | `vault.cluster.access` |
| **Policies** | ACL policy list and editor | `vault.cluster.policies` |
| **Tools** | Wrap / Lookup / Unwrap / Rewrap / Random / Hash | `vault.cluster.tools.tool` |
| **Monitoring** | A section title, not a link. Shown in the root namespace only. Its two entries are **Raft Storage** (`vault.cluster.storage`) and **Seal OpenBao** (`vault.cluster.settings.seal`). | — |

**Access** expands into three groups:

| Group | Menu item | UI route |
|---|---|---|
| *Authentication* | **Authentication methods** | `vault.cluster.access.methods` |
| | **Multi-factor authentication** | `vault.cluster.access.mfa.methods` |
| | **OIDC provider** | `vault.cluster.access.oidc` |
| *Organization* | **Namespaces** | `vault.cluster.access.namespaces` |
| | **Groups** | `vault.cluster.access.identity` |
| | **Entities** | `vault.cluster.access.identity` |
| *Administration* | **Leases** | `vault.cluster.access.leases` |

And here is the API behind each screen, with the HTTP status codes actually
observed on the running server:

```console
$ T=$(cat root-token)
$ for p in /v1/sys/internal/ui/mounts /v1/sys/auth /v1/sys/policy \
           /v1/sys/seal-status /v1/sys/leader /v1/sys/health \
           /v1/sys/internal/ui/namespaces /v1/sys/internal/ui/resultant-acl; do
    printf '%-42s -> ' "$p"
    curl -s -o /dev/null -w '%{http_code}\n' -H "X-Vault-Token: $T" "http://127.0.0.1:9306$p"
  done
/v1/sys/internal/ui/mounts                 -> 200
/v1/sys/auth                               -> 200
/v1/sys/policy                             -> 200
/v1/sys/seal-status                        -> 200
/v1/sys/leader                             -> 200
/v1/sys/health                             -> 200
/v1/sys/internal/ui/namespaces             -> 200
/v1/sys/internal/ui/resultant-acl          -> 200
```

**Monitoring** contains **Raft Storage** (only when the cluster is running
`raft` — our `pebbledb` cluster does not show it) and **Seal OpenBao**,
which is the GUI's version of `bao operator seal`.

### 8.3 GUI versus CLI

| What you want | GUI path | CLI equivalent |
|---|---|---|
| See which engines exist | **Secrets engines** | `bao secrets list` |
| Enable an engine | **Secrets engines → Enable new engine** (form button: **Enable Engine**) | `bao secrets enable -path=ai/platform kv-v2` |
| Browse secrets | **Secrets engines → ai/platform → llm → gemini** | `bao kv get ai/platform/llm/gemini` |
| See auth methods | **Access → Authentication methods** | `bao auth list` |
| Enable an auth method | **Access → Authentication methods → Enable new method** (form button: **Enable Method**) | `bao auth enable approle` |
| Read / edit a policy | **Policies → ACL Policies → <name>** | `bao policy read meridian-ai-harness` |
| List active leases | **Access → Leases** | `bao list sys/leases/lookup` |
| Who am I / what can I do | *not shown anywhere* | `bao token lookup`, `bao token capabilities` |
| Wrap a value | **Tools → Wrap** | `bao write sys/wrapping/wrap text="..."` |
| Unwrap a value | **Tools → Unwrap** | `bao write sys/wrapping/unwrap token="s.xxx"` |
| Random bytes | **Tools → Random** | `bao write sys/tools/random/32` |
| Hash a value | **Tools → Hash** | `bao write sys/tools/hash input="..."` |
| Seal the server | **Monitoring → Seal OpenBao** | `bao operator seal` |
| Unseal the server | *not in the GUI* | `bao operator unseal "<key>"` |
| Generate a root token | *not in the GUI* | `bao operator generate-root` |
| Rotate unseal keys | *not in the GUI* | `bao operator rotate-keys` |
| Create a scoped token | *not in the GUI* | `bao token create -policy=... -ttl=...` |
| Read the audit log | *not in the GUI* | read the audit file |

### 8.4 Why the CLI is primary in this course

Look at the bottom half of that table. The GUI cannot unseal, cannot
generate a root token, cannot rotate shares, and cannot mint a scoped
token. Those are exactly the operations an incident needs.

There is a second reason, and it is the one that matters at Meridian AI:
**the GUI is a browser session.** Every action you take in it is a click
that depends on a JS bundle, a CDN-free local asset, and a session cookie.
In a CI pipeline, a Terraform-style bootstrap script, or a container
entrypoint, there is no browser. If your production procedure only exists
in the GUI, it does not exist.

> **Production:** *Use the GUI to *understand* and to *demonstrate*; use the
> CLI to *operate*. The two are the same API — the GUI is just a client of
> it. When a screen confuses you, run the equivalent CLI command and read
> the raw JSON; that is where the truth is.*

---

## 9. Debugging

### 9.1 `bao status` — the fields that matter

```console
$ bao status
Key             Value
---             -----
Seal Type       shamir
Initialized     true
Sealed          false
Total Shares    3
Threshold       2
Version         2.7.1
Commit Date     2026-10-01T15:32:54Z
Storage Type    pebbledb
Cluster Name    vault-cluster-fcdbc432
Cluster ID      482546e4-34a1-dfc7-2a27-5aff92a13ed5
HA Enabled      false
```

| Field | Read it as | When it is wrong |
|---|---|---|
| `Seal Type` | Which seal protects the barrier key | `shamir` → you need a human ceremony; `transit`/`awskms`/… → auto-unseal |
| `Initialized` | Has the store ever been initialized | `false` → nobody has done the init ceremony yet |
| `Sealed` | Can the API serve secrets right now | `true` → this is your outage |
| `Total Shares` / `Threshold` | N and K of your Shamir split | `0 / 0` → uninitialized |
| `Unseal Progress` | How many shares are already in | `1/2` → one more share needed |
| `Unseal Nonce` | The nonce of the *current* unseal attempt | changes on every seal |
| `Storage Type` | `pebbledb`, `raft`, or `inmem` | `inmem` → you are running `-dev` |
| `Cluster Name` / `Cluster ID` | Which cluster you are talking to | mismatch → you are pointed at the wrong server |
| `HA Enabled` | Is this an HA cluster | `false` + you expected `true` → wrong storage backend |

In JSON form, the same facts, which is what you want when you are
pasting into a ticket:

```console
$ bao status -format=json
{
  "type": "shamir",
  "initialized": true,
  "sealed": false,
  "t": 2,
  "n": 3,
  "progress": 0,
  "nonce": "",
  "version": "2.7.1",
  "commit_date": "2026-10-01T15:32:54Z",
  "migration": false,
  "cluster_name": "vault-cluster-fcdbc432",
  "cluster_id": "482546e4-34a1-dfc7-2a27-5aff92a13ed5",
  "recovery_seal": false,
  "storage_type": "pebbledb",
  "build_date": "",
  "ha_enabled": false
}
```

Note `"recovery_seal": false` — the machine-readable form of the §4.4 trap.
If that field is `true`, you are on an auto-unseal seal and you *do* have
recovery keys.

The endpoint the GUI polls is `sys/seal-status`, which is available even
while sealed:

```console
$ bao read sys/seal-status
Key              Value
---              -----
cluster_id       482546e4-34a1-dfc7-2a27-5aff92a13ed5
cluster_name     vault-cluster-fcdbc432
commit_date      2026-10-01T15:32:54Z
initialized      true
migration        false
n                3
nonce            n/a
progress         0
recovery_seal    false
sealed           false
storage_type     pebbledb
t                2
type             shamir
version          2.7.1
```

### 9.2 The barrier key's own status

```console
$ bao operator key-status
Key Term            1
Install Time        21 Oct 26 16:33 UTC
Encryption Count    8
```

**Key Term** is the generation of the barrier key. Term 1 is the original
key; it only changes when you rotate.

> ⚠️ **Encryption Count does *not* track seal/unseal cycles.** This is worth
> saying out loud, because the common advice — *"if the encryption count
> climbs, something is sealing your vault on a schedule"* — is a **guaranteed
> false alarm**. Verified on 2.7.1: the count was `223` before a full
> seal → unseal cycle and still `223` after it, and still `223` after a
> second cycle:
>
> ```console
> $ bao operator key-status | grep -i "Encryption Count"
> Encryption Count    223
>
> $ bao operator seal
> $ bao operator unseal "<share 1>"
> $ bao operator unseal "<share 2>"
>
> $ bao operator key-status | grep -i "Encryption Count"
> Encryption Count    223      # unchanged
> ```
>
> The counter moves on **key rotation**, not on sealing. So treat it as a
> key-lifecycle indicator, not a tamper alarm.
>
> **The signals that actually work** for "is it being sealed?":
>
> | Signal | Where | Why it is reliable |
> |---|---|---|
> | `"sealed": true` | `curl -s $BAO_ADDR/v1/sys/health` | The raw health endpoint keeps answering while sealed — unlike every business endpoint, which returns 503 |
> | `core: marked as sealed` | `server.log` | Written on every seal, with a timestamp |
> | `Sealed true` | `bao status` | Same fact, CLI view |
>
> Use the health endpoint in your monitoring, not the encryption count.

### 9.3 Reading `server.log`

The log is your best friend at 3am. The lines that matter for this module:

```console
$ grep -E "security barrier|sealed|unseal" logs/server.log
2026-10-21T16:33:18.778Z [INFO]  core: security barrier not initialized
2026-10-21T16:33:23.107Z [INFO]  core: security barrier initialized: shares=3 threshold=2
2026-10-21T16:33:23.115Z [INFO]  core: post-unseal setup starting
2026-10-21T16:33:23.205Z [INFO]  core: post-unseal setup complete
2026-10-21T16:33:23.529Z [INFO]  core: vault is unsealed
2026-10-21T16:36:52.379Z [INFO]  core: marked as sealed
2026-10-21T16:36:52.827Z [INFO]  core: vault is sealed
2026-10-21T16:36:58.697Z [INFO]  core: post-unseal setup starting
2026-10-21T16:36:58.708Z [INFO]  core: post-unseal setup complete
2026-10-21T16:36:58.708Z [INFO]  core: vault is unsealed
```

```console
$ bao operator diagnose -config=./config/openbao.hcl -skip=listener
OpenBao v2.7.1 (a5db72cef75c24b920ade02065b18dd8eb666bac), committed 2026-10-01T15:32:54Z

Results:
[ failure ] Vault Diagnose
  [ success ] Check Operating System
    [ success ] Check Open File Limits: Open file limits are set to 1048576.
  [ success ] Parse Configuration
  [ failure ] Check Telemetry: incomplete Stackdriver telemetry configuration, missing stackdriver_project_id
  [ success ] Check KMS Plugin Catalog
  [ failure ] Check Storage: Diagnose could not initialize storage backend.
    [ failure ] Create Storage Backend: error initializing storage of type pebbledb: failed to open database: resource temporarily unavailable
```

Read that last line carefully — it is **not** a corrupt database. It is the
pebbledb **file lock**: the running server already holds the data
directory, so a second process cannot open it. The exact same error is what
you get if you accidentally start two OpenBao containers against the same
volume, and it is the single most common "my vault will not start" report.

`-skip=listener` tells `diagnose` not to try to bind the port, which is why
you can run it against a live server.

A quick decision tree:

```
bao status says Sealed: true
├── Is Initialized: false?  → nobody has run `bao operator init` yet.
│                             The store is empty. Do the init ceremony.
├── Do you have N shares?    → `bao operator unseal "<key>"` K times.
│                             Check "Unseal Progress" to see how many you need.
├── Did it just restart?     → expected. A restart always re-seals.
│                             Unseal, or configure auto-unseal (Module 09).
└── Does the log show        → someone or something is sealing it on a
   "marked as sealed"        schedule. Find that schedule.
   without a restart?
```

```console
$ bao operator diagnose
Must specify a configuration file using -config.
```

`bao operator diagnose` exists in 2.7.1 and is the intended first command
when the server will not start. Run it with the **same** config and
environment as the server, so the startup path is actually reproduced — the
`-config` flag is not optional.

### 9.4 What the audit log looks like

Because the lab runs a **declarative** audit device, every API call is
written to `logs/audit.log`. Here is a real entry — the `sys/seal` call from
§5.1 — with the token HMAC'd rather than stored in the clear:

```console
$ jq 'select(.request.path=="sys/seal") | {time, type, auth: {display_name: .auth.display_name, policies: .auth.policies, client_token: .auth.client_token}, request: {id: .request.id, operation: .request.operation, path: .request.path, remote_address: .request.remote_address, remote_port: .request.remote_port}}' logs/audit.log
{
  "time": "2026-10-21T16:36:52.37882131Z",
  "type": "request",
  "auth": {
    "display_name": "root",
    "policies": [
      "root"
    ],
    "client_token": "hmac-sha256:e038cf6bd4779af4e5855efaf16c2276d52f633f375a8469c00f71128edd2bed"
  },
  "request": {
    "id": "a7f11610-1acb-5434-1585-61fda76db5c0",
    "operation": "update",
    "path": "sys/seal",
    "remote_address": "127.0.0.1",
    "remote_port": 41176
  }
}
```

And a real secret write — note that the **value** is HMAC'd, not stored in
the clear, because the device is configured with `log_raw = "false"`:

```console
$ bao write cubbyhole/meridian-check value="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr"
Success! Data written to: cubbyhole/meridian-check

$ jq -c 'select(.request.path=="cubbyhole/meridian-check") | {request: {path: .request.path, data: .request.data, operation: .request.operation}}' logs/audit.log
{"request":{"path":"cubbyhole/meridian-check","data":{"value":"hmac-sha256:73dd0caec76c7ac8031fa07e242dfdb0cd1e3ecb31e223059e57739996f6ecc8"},"operation":"create"}}
{"request":{"path":"cubbyhole/meridian-check","data":{"value":"hmac-sha256:73dd0caec76c7ac8031fa07e242dfdb0cd1e3ecb31e223059e57739996f6ecc8"},"operation":"create"}}
```

Two lines, not one — and that is not a duplicate. OpenBao writes **two** audit
records per API call: a `request` record and a `response` record. Both carry
the same `request.path` and the same HMAC'd body, so this filter (which
selects on `request.path` and does not look at `type`) matches both. If you
want exactly one line per API call, add the type to the filter:

```bash
$ jq -c 'select(.type=="request" and .request.path=="cubbyhole/meridian-check") | {request: {path: .request.path, data: .request.data, operation: .request.operation}}' logs/audit.log
{"request":{"path":"cubbyhole/meridian-check","data":{"value":"hmac-sha256:73dd0caec76c7ac8031fa07e242dfdb0cd1e3ecb31e223059e57739996f6ecc8"},"operation":"create"}}
```

The HMAC is keyed, so two audit entries of the same secret produce the same
HMAC (you can correlate them) but you cannot recover the value. That is the
correct design: the audit log answers *who touched what, when*, without
becoming a second copy of the secret store.

The log is **JSON Lines** — one JSON object per line — not a JSON array. So
use `jq -c` per line, or `jq -s` to slurp it into an array. Treating it as
an array trips people up:

```console
$ jq -r '.[0].request.path' logs/audit.log
jq: error (at logs/audit.log:1): Cannot index object with number
jq: error (at logs/audit.log:2): Cannot index object with number
...one error per line, because jq reads the file as a stream of JSON values
```

The fix is `jq -r 'select(.type=="request") | .request.path'`.

> **Trade-off:** *`log_raw = "false"` means your audit log cannot be used to
> recover a secret. That is the point, and it is the right default. But it
> also means an incident responder cannot see *what* was leaked from the
> audit log alone — you will need the secret store (or the rotation
> provider) for that. Module 09 covers the full audit architecture, including
> shipping logs off-host so a compromised host cannot delete the evidence.*

---

## 10. What you learned

- [x] Why a `.env` file fails at Meridian AI's scale — the six questions
- [x] The architecture: plaintext → barrier key → ciphertext at rest
- [x] What "sealed" *physically* means — the barrier key is not in the process
- [x] `-dev` vs `server -config=`, and what each one breaks
- [x] `pebbledb` vs `raft`, and that `file` storage was removed in 2.7.0
- [x] Why the port must be loopback-only — and the one-request takeover
- [x] `cap_drop: ALL` + `IPC_LOCK` + `no-new-privileges` + uid 100, and the
      `/openbao/file` volume quirk
- [x] `bao operator init` with 3 shares / threshold 2, and what Shamir's
      Secret Sharing actually guarantees
- [x] **That Shamir mode has NO recovery keys** — `recovery_keys_b64` is
      `null`, and the help text says so
- [x] Seal, unseal, and the quorum behaviour
- [x] **That a restart always re-seals** — demonstrated, not asserted
- [x] The complete `generate-root` flow: OTP → nonce → shares → `Encoded
      Token` → decode, plus every real error message
- [x] **That a wrong-OTP decode still looks like a token** — and that the
      only way to know is to *use* it (`bao token lookup`), never to eyeball
      the string
- [x] Why `generate-root` needs a `sudo` token in OpenBao 2.6+
- [x] Root token vs unseal key vs scoped token vs lease
- [x] The GUI's real menu tree, and the operations the GUI cannot do
- [x] Where to look in `server.log` and `bao status` when something breaks

## 11. What's next

**Module 02 — KV v2: Storing Meridian AI's Gemini API Key.** You will enable
the KV v2 engine at `ai/platform/`, write the real Gemini key at
`ai/platform/llm/gemini`, read it back, and dig into the metadata layer:
versions, check-and-set, custom metadata, soft delete versus destroy, and
the two-layer `data` / `metadata` structure that makes JSON output trip
people up.

## 12. Homework

Do these in order. Each one has a specific thing to observe.

1. **Prove the quorum is a quorum.** Seal the server
   (`bao operator seal`), then unseal it using **shares 2 and 3** instead of
   1 and 2. Confirm it unseals and that `bao status` shows `Sealed false`.
   Then repeat with only one share and confirm it stays sealed. Write down
   the exact `Unseal Progress` value at each step.

2. **Run the break-glass script.** Use the script from §6.7 with two of your
   three shares. Verify the new root token with
   `bao token lookup`. Then **revoke the old one**:
   `bao token revoke <old-token>`. Try using the revoked token and read the
   error — it should be a 403.

3. **Break the OTP rules on purpose.** Run
   `bao operator generate-root -init -otp="short"` and read the error. Then
   run `bao operator generate-root -generate-otp | grep OTP | awk '{print $2}'`
   and confirm you get an **empty string** (§6.2) — this is gotcha #1, and
   you want to recognise it instantly. Then run the same command with
   `| tail -1` and confirm you get the 26 characters. Finally, submit a
   share **without** `-nonce` and confirm the CLI refuses with
   `Missing nonce value: specify it via the -nonce flag`.

   Then do the one that matters: mint a root token, change **one character**
   of the OTP you used to decode it, and decode again (§6.5). Observe that
   the result still starts with `s.` and still has the right length. Run
   `bao token lookup` with both tokens and confirm that only the correct
   one authenticates and reports `display_name: root`. **Never install a
   break-glass root token you have not used.**

4. **Do the restart drill, properly.** Stop the server, start it again, and
   confirm `bao status` shows `Sealed true`. Then check the log:
   `grep -E "security barrier|sealed" logs/server.log`. Finally, unseal it
   and confirm your **root token still works** — the token was encrypted in
   the store, not held in the process.

5. **Read your own audit log.** Find the entry for the `sys/seal` call you
   made in exercise 1:
   `jq 'select(.request.path=="sys/seal")' logs/audit.log`. Confirm the
   `client_token` is HMAC'd, not plaintext, and note the `remote_address`
   and `remote_port` fields. Those are the fields that answer "who did
   this?" — which is question 4 from §1. Then write the one-page Meridian
   AI unseal-ceremony runbook: who holds which share, where the shares
   physically live, who may run the ceremony, and what the first three
   commands are after a restart. Show it to whoever will be on call. A
   runbook nobody has read is a runbook that does not exist.

---

[← Course index](../../README.md) ·
[Next: Module 02 — KV v2 Secrets](../02-kv-secrets/README.md)
