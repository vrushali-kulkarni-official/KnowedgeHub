# Module 01 — Foundations: Your First Production-Shaped OpenBao

> **The story so far.** You just joined **Meridian AI**, a mid-size company that
> sells an enterprise AI assistant platform. Your FastAPI + LangChain harness
> calls Gemini's API, talks to Postgres and Redis, and authenticates humans
> through Keycloak's OIDC. Six weeks ago the platform engineer left the
> Gemini key in a `.env` file that was committed to Git. You are the first
> platform engineer hired since. Your first week: replace the `.env` file with
> a real secret store, without breaking anything.
>
> Everything in this course is built inside that story. We are standing up
> Meridian AI's OpenBao from nothing, the way it should exist on day one.

---

## 0. The 60-second version

If you read nothing else, read this.

| Concept | One-line meaning | Why it exists |
|---|---|---|
| **Secret** | Any credential your app needs to work | API keys, DB passwords, TLS certs |
| **OpenBao** | A server that stores secrets encrypted, and only hands them to authenticated callers | Central place to revoke, rotate, audit |
| **Storage** | The encrypted disk where secrets live (`pebbledb` here) | Durability |
| **Barrier / root key** | The master encryption key | Everything is encrypted with it |
| **Seal** | The server is locked — it literally cannot decrypt anything | Offline attack protection |
| **Unseal key** | A share of the root key (Shamir) | N shares, K needed |
| **Root token** | Unrestricted admin credential | Bootstrap + break-glass |
| **Token** | A scoped, expiring credential | What apps actually use |
| **Policy** | The ACL that decides what a token may do | Least privilege |
| **Mount** | A namespace where an engine stores things | e.g. `ai/platform/` holds KV v2 |
| **Lease** | A time-bound record of a credential | Auto-expiry |
| **Audit device** | Writes every request to a tamper-evident log | Forensics & compliance |

**The one thing to internalize:** OpenBao is *not* a password manager with a
nice UI bolted on. It is a **cryptographic secret distribution system**. The
storage is encrypted at rest with a key that lives nowhere near the data.

---

## 1. Why not just keep secrets in `.env` files?

Let's look at what Meridian AI is doing right now, and be honest about it.

```bash
# What your repo probably looks like today
GEMINI_API_KEY=AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr
DATABASE_URL=postgresql://meridian_app:hunter2@postgres:5432/meridian_ai
REDIS_PASSWORD=lab-only-redis-pass
```

Now ask six uncomfortable questions:

1. **Who can read it?** Everyone with repo read access. On a real org, that's
   contractors, auditors, and everyone who ever cloned the repo.
2. **Is it in git history?** Yes. `git log -p` still shows it. Deleting the
   line does **not** remove it from history — you must rotate the key.
3. **Can you rotate it?** Rotate = find every deployment, edit a file, restart.
   With 12 microservices, that's a Tuesday.
4. **Can you see who accessed it?** No. There is no log. Ever.
5. **Can you scope it?** No. A service that only needs the Gemini key can read
   the database password too.
6. **Does the app get it at runtime?** It reads from disk. The secret exists in
   the container filesystem, in core dumps, in `/proc/<pid>/environ`.

OpenBao fixes all six. That framing matters, because every "why would I even
do this?" moment in the next 8 modules maps back to one of these six problems.

---

## 2. Install it — Docker only (as you prefer)

We use the official image pinned to an exact version. **Never use `latest`.**

```yaml
# lab/docker-compose.yml (excerpt)
openbao:
  image: openbao/openbao:2.7.1
  command: server -config=/openbao/config
  ports:
    - "127.0.0.1:8200:8200"   # loopback only, on purpose
  volumes:
    - ./config:/openbao/config:ro
    - openbao-data:/openbao/data
    - ./logs:/openbao/logs
```

### 2.1 Why `command: server -config=...` and not the default?

The image's default command is `server -dev`. Read that carefully:

| | `-dev` (default) | `server -config=...` (production-shaped) |
|---|---|---|
| Storage | In-memory, wiped on exit | `pebbledb`, durable |
| Sealed on start? | No — always unsealed | **Yes** — needs unseal keys |
| Root token | Fixed, predictable (`root`) | Generated once, random, one-time |
| Audit | Off | On (declarative stanza) |
| Real init flow? | **No** | Yes |
| Production safe? | **Absolutely not** | Yes, with hardening |

`-dev` is a teaching shortcut. It skips the exact thing that makes OpenBao
worth deploying: **the seal**. If you learn on `-dev`, you never build the
muscle memory for unsealing, and your production deployment will be a
mystery outage at 3am.

> **Version note (2.7.x).** The `file` storage backend was **removed** in
> OpenBao v2.7.0. If you follow a tutorial that says
> `storage "file" { path = ... }`, it is out of date. Use `pebbledb`
> (single node) or `raft` (HA).

### 2.2 Why bind to `127.0.0.1:8200` and not `8200:8200`?

Because the OpenBao API is an **unauthenticated attack surface** before you
initialize it. Anyone who can reach the port of an *uninitialized* server can
call `/sys/init` themselves and receive the root token. That is a real
vulnerability class, not a hypothetical.

Binding to loopback means only your machine can reach it. In production you'd
put it behind a firewall/TLS-terminating proxy, or bind to a private network
interface.

### 2.3 Why `cap_add: IPC_LOCK` and `cap_drop: ALL`?

```yaml
cap_drop: [ALL]
cap_add: [IPC_LOCK]
security_opt: ["no-new-privileges:true"]
user: "100:1000"
```

- `mlock` (needs `IPC_LOCK`) prevents OpenBao from swapping decrypted secrets
  to disk. The kernel's swap file would otherwise become an unencrypted copy
  of your entire secret store.
- `cap_drop: ALL` + adding back only what you need follows the principle of
  least privilege. The image already runs as a non-root user.
- `no-new-privileges` blocks setuid escalation inside the container.

### 2.4 Start it

```bash
cd lab
docker compose up -d openbao
docker compose logs -f openbao
```

You should see:

```
==> OpenBao server configuration:
             Api Address: http://127.0.0.1:8200
         Cluster Address: https://127.0.0.1:8201
                 Storage: pebbledb
                 Version: OpenBao v2.7.1, committed 2026-10-01T15:32:54Z
==> OpenBao server started!
```

Notice it says **Storage: pebbledb** and **not** "initialized". Check:

```bash
docker exec -it meridian-openbao bao status
```

```
Key                Value
---                -----
Seal Type          shamir
Initialized        false      <-- NOT initialized yet
Sealed             true
Total Shares       0
Threshold          0
Version            2.7.1
Storage Type       pebbledb
HA Enabled         false
```

**Read that output as a sentence:** "I have an empty encrypted vault, and
because I have no unseal keys yet, I cannot possibly be read by anyone —
including you."

---

## 3. Initialize

Initialization does three things:

1. Generates the **root key** (the barrier key that encrypts everything).
2. Splits it with **Shamir's Secret Sharing** into N shares.
3. Creates the **root token** — an unlimited-lifetime admin credential.

```bash
docker exec -it meridian-openbao bao operator init -key-shares=3 -key-threshold=2
```

Real output from the lab:

```
Unseal Key 1: xXj7nVEdx7qaOUKxzbenO/7O4TvbI1M68vhxmFZkvZSA
Unseal Key 2: QYQpKzedHaFcoH0yulX/Y9jX0aHQxP4ZXtOsC/boCNLj
Unseal Key 3: L6qZD2dgkEAFePtp8mtL13vyX99LCztL+bwUKv+7inZC

Initial Root Token: s.4BZ2u4MnsRKWMZzEBosou7F0

Vault is initialized
```

### 3.1 Why 3 shares and threshold 2?

Shamir's Secret Sharing splits a secret into N shares such that **any K** of
them reconstruct it, and **any K-1** reveal nothing.

- `3 shares, threshold 2` = 2-of-3.
- You can lose 1 share and still unseal. ✅
- One person alone can never unseal. ✅ (no single point of failure)
- But 2 colluding people can. ⚠️ (that's your risk to manage)

**Production sizing:** distribute shares across *different people* in
*different physical locations*. A common real-world choice is **5-of-7** or
**7-of-11** for a company Meridian AI's size. The people holding shares should
be: a CTO, an SRE lead, a security lead, an infrastructure lead, and a
trusted off-site custodian. Written down, sealed in envelopes, in a safe.

### 3.2 ⚠️ The recovery-key trap (this one bites everyone)

You might have read that OpenBao "generates recovery keys" at init. **In
OpenBao 2.7.1 that is false in Shamir mode.** Verified:

```bash
$ bao operator init -key-shares=3 -key-threshold=2 \
      -recovery-shares=5 -recovery-threshold=3 -format=json | jq .recovery_keys_b64
null
```

The CLI help says it plainly:

```
-recovery-shares=<int>
      Number of key shares to split the recovery key into.
      This is only used in Auto Unseal mode. The default is 5.
```

**Why the difference from HashiCorp Vault?** In Vault, recovery keys are a
*second* independent quorum, and `generate-root` accepts either unseal keys
or recovery keys. In OpenBao, recovery keys exist **only for auto-unseal
seals** (Transit, AWS KMS, Azure Key Vault, GCP KMS, HSM, PKCS#11). With the
default Shamir seal, **your unseal keys are the recovery mechanism**. There is
no separate backup set.

This matters operationally: if you lose too many unseal shares in Shamir mode,
**the data is cryptographically unrecoverable.** That is by design, and it is
why Module 04 teaches Transit auto-unseal — it gives you recovery keys *and*
survives server restarts unattended.

> **Migration warning for Vault users.** If you're coming from Vault, note
> OpenBao 2.6+ also **deprecated the unauthenticated `/sys/generate-root`
> endpoints**. Use the authenticated `/sys/generate-root-token` endpoints
> (which the `bao operator generate-root` command now uses automatically).

### 3.3 What if I lose the root token?

You don't need it. The unseal shares can **mint a new root token** — that's
the `generate-root` drill in §5.

### 3.4 Store these immediately

```bash
source lab/scripts/bao-lab.sh
use_lab_token
```

`init-lab.sh` does this for you and writes to `lab/secrets/` with `chmod 600`.
In a real org this goes into a password manager (1Password, Bitwarden,
AWS Secrets Manager) or a printed ceremony document. Never in the repo.
Never in Slack.

---

## 4. Seal and Unseal

### 4.1 What "sealed" actually means

Sealed is not "locked behind a login screen." It is:

- The root key is **unavailable** to the process.
- Stored data is **cryptographically unreadable** — not just unauthorized.
- The API refuses to serve secrets.
- The `sys/` endpoints are still reachable, but only for seal operations.

So if someone steals your Docker volume, they get ciphertext. To read it they
need your unseal keys — which live in three separate people's heads (or
password managers).

### 4.2 Seal it

```bash
bao operator seal
```

```
Key                Value
---                -----
Seal Type          shamir
Initialized        true
Sealed             true
Total Shares       3
Threshold          2
Unseal Progress    0/2
```

### 4.3 Unseal it

```bash
bao operator unseal "xXj7nVEdx7qaOUKxzbenO/7O4TvbI1M68vhxmFZkvZSA"
bao operator unseal "QYQpKzedHaFcoH0yulX/Y9jX0aHQxP4ZXtOsC/boCNLj"
```

```
Key             Value
---             -----
Seal Type       shamir
Initialized     true
Sealed          false
Threshold       2
```

Two submissions, because threshold is 2. **Order and grouping don't matter** —
any 2 of the 3 work. This is the property that lets you unseal in a ceremony
where people arrive at different times.

### 4.4 The restart lesson

Restart the container:

```bash
docker compose restart openbao
docker exec -it meridian-openbao bao status
```

```
Initialized        true
Sealed             true        <-- sealed again
Unseal Progress    0/2
```

**This is the single most important operational fact in this module.** Your
OpenBao comes back sealed after every restart, every deploy, every crash. You
need an automated unseal path in production (Module 04: Transit auto-unseal)
or a runbook (Module 09).

If you use `-dev` mode, you never see this. That's why we don't.

---

## 5. Break-glass recovery: generating a new root token

Scenario: the root token leaked. You need to burn it and mint a fresh one —
**without** rotating the root key, because rotating would invalidate every
unseal share you hold.

`generate-root` does exactly that: it uses your unseal-key quorum to authorize
a brand-new root token.

### 5.1 The 4-step flow (and the two gotchas)

```bash
# STEP 1 — generate an OTP (your personal decryption key)
bao operator generate-root -generate-otp
# Output (just the OTP, nothing else):
#   8BL7xUkLdWlcoY9WmPJBkP9F0Z
```

> **Gotcha #1.** `-generate-otp` prints *only* the OTP string — no label, no
> table. If you write `| grep OTP | awk '{print $2}'` you get an empty
> string and a confusing failure 3 steps later. Capture it with
> `| tail -1`.

```bash
# STEP 2 — start the attempt, binding it to that OTP
bao operator generate-root -init -otp="8BL7xUkLdWlcoY9WmPJBkP9F0Z"
```

```
Nonce         08837b17-2e2e-7b80-7988-e2c818e1c396
Started       true
Progress      0/2
Complete      false
OTP Length    26
```

> **Gotcha #2.** The **nonce** is returned here and is required for *every*
> subsequent call in this attempt. `bao operator generate-root` does **not**
> auto-carry it. Without `-nonce` you get:
> `Missing nonce value: specify it via the -nonce flag`
> Save it. If you lose it, `bao operator generate-root -cancel` (with a
> sudo-capable token) and start over.

Also note: the OTP **must be exactly 26 characters**. A short one is
rejected with a 400.

```bash
# STEP 3 — submit unseal shares, one call per share
bao operator generate-root \
  -nonce="08837b17-2e2e-7b80-7988-e2c818e1c396" \
  -otp="8BL7xUkLdWlcoY9WmPJBkP9F0Z" \
  "xXj7nVEdx7qaOUKxzbenO/7O4TvbI1M68vhxmFZkvZSA"
```

```
Progress      1/2
Complete      false
```

```bash
bao operator generate-root \
  -nonce="08837b17-2e2e-7b80-7988-e2c818e1c396" \
  -otp="8BL7xUkLdWlcoY9WmPJBkP9F0Z" \
  "QYQpKzedHaFcoH0yulX/Y9jX0aHQxP4ZXtOsC/boCNLj"
```

```
Progress      2/2
Complete      true
Encoded Token    JVoBXS0CXXwCAyowNFZeOzczPh8Xei8hK2c
```

> **Gotcha #3 (the field name).** The output field is `Encoded Token` — two
> words. `awk '/^Encoded Root Token/'` matches nothing. Use `$3` with
> `/^Encoded Token/`.

```bash
# STEP 4 — XOR the encoded token with your OTP to get the real token
bao operator generate-root -decode="JVoBXS0CXXwCAyowNFZeOzczPh8Xei8hK2c" \
  -otp="8BL7xUkLdWlcoY9WmPJBkP9F0Z"
# -> s.d5wIhHSwiZrokAEZLSNOylC7
```

> **Why the OTP?** The generated token is XORed with a secret *you* chose.
> Even if the response is captured in a log or a proxy trace, the attacker
> doesn't have the OTP, so they can't reconstruct the token. The server never
> has a plaintext copy of your OTP either — it only stores the hash.

### 5.2 Verify and burn the old token

```bash
export BAO_TOKEN=s.d5wIhHSwiZrokAEZLSNOylC7
bao token lookup
```

```
display_name       root
policies           [root]
creation_ttl       0s
```

Then revoke the compromised one:

```bash
bao token revoke s.4BZ2u4MnsRKWMZzEBosou7F0
```

### 5.3 What `generate-root` does NOT do

It does **not** rotate the root key. The unseal shares you already hold
remain valid. If you *want* new shares (because one was compromised), you need
`bao operator rekey` — and that invalidates the old ones, so you must
distribute the new ones immediately.

### 5.4 Full script (copy-paste, error-handling included)

```bash
#!/usr/bin/env bash
set -euo pipefail
export BAO_ADDR=http://127.0.0.1:8200

K1="xXj7nVEdx7qaOUKxzbenO/7O4TvbI1M68vhxmFZkvZSA"
K2="QYQpKzedHaFcoH0yulX/Y9jX0aHQxP4ZXtOsC/boCNLj"

OTP=$(bao operator generate-root -generate-otp 2>/dev/null | tail -1)
INIT_OUT=$(bao operator generate-root -init -otp="$OTP")
NONCE=$(echo "$INIT_OUT" | awk '/^Nonce/{print $2}')
[ -n "$NONCE" ] || { echo "could not read nonce"; exit 1; }

bao operator generate-root -nonce="$NONCE" -otp="$OTP" "$K1" >/dev/null
OUT=$(bao operator generate-root -nonce="$NONCE" -otp="$OTP" "$K2")
ENC=$(echo "$OUT" | awk '/^Encoded Token/{print $3}')
NEW_TOKEN=$(bao operator generate-root -decode="$ENC" -otp="$OTP" | tr -d '\r' | tail -1)

echo "NEW ROOT TOKEN: $NEW_TOKEN"
```

---

## 6. Quick sanity check — you're operational

```bash
export BAO_ADDR=http://127.0.0.1:8200
export BAO_TOKEN=$(cat lab/secrets/root-token)

bao status                          # Sealed: false
bao token lookup                    # policies: [root]
bao secrets list                    # cubbyhole/, identity/
bao auth list                       # token/
bao policy list                     # default, root
```

### The GUI

Open <http://127.0.0.1:8200/ui> and log in with the root token.

What you'll see, and how it maps to the CLI:

| GUI | CLI equivalent |
|---|---|
| **Secrets →** engines and mounts | `bao secrets list` |
| **Auth Methods →** | `bao auth list` |
| **Policies →** | `bao policy list` |
| **Access →** tokens, policies, user groups | `bao token list`, `bao list auth/token/accessors` |
| **Tools →** random / hash / keymgmt | `bao write sys/tools/random/32` |
| **Wrapping →** | `bao write sys/wrapping/wrap` |
| **Status →** seal state, cluster | `bao status` |

The GUI is a genuine production tool, not a toy. But there's a reason the CLI
is primary in this course: **the GUI cannot do everything.** Declarative audit
devices, some namespace operations, and all of your CI/CD flows need the CLI
or the API.

---

## 7. What you learned

- [x] Why `.env` files fail at a 12-service scale
- [x] `-dev` vs `server -config=...` — and why we refuse `-dev`
- [x] `pebbledb` vs the removed `file` backend (2.7+)
- [x] `bao operator init` with 3/2 Shamir shares
- [x] **Recovery keys are auto-unseal-only** — Shamir mode has none
- [x] Seal / unseal, and that a restart always re-seals
- [x] `generate-root` end to end: OTP → nonce → shares → decode
- [x] Root token vs unseal keys vs leases — three different things

## 8. What's next

**Module 02 — KV v2 and the Gemini key.** We enable the KV v2 engine, store
Meridian AI's real Gemini API key at `ai/platform/llm/gemini`, read it back,
and dig into the metadata layer: versions, CAS, custom metadata, soft delete,
and TTL tuning.

---

### Homework (do this, then we'll continue)

1. Seal the server. Unseal it using shares **2 and 3** instead of 1 and 2.
   Confirm it still works. (This is how you prove the quorum is a quorum.)
2. Run `bao operator generate-root` end to end. Revoke the old root token.
3. Enable the audit device check: `bao audit list` should show `local-file/`.
   Then look at `lab/logs/audit.log` — you should see your own API calls,
   with every secret value HMAC'd:
   ```json
   "api_key": "hmac-sha256:99573bf8d5f6f359999ebb2e953a1b1994fdc3dc6..."
   ```
   Notice the secret is *not* in plaintext. That's `log_raw = false` doing
   its job. (Module 09 covers audit hardening.)
4. Try `bao operator generate-root -init -otp="short"` and read the error.
   Now you know the 26-char rule.
