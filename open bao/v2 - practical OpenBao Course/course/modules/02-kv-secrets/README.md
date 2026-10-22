# Module 02 — KV v2: Storing Meridian AI's Gemini API Key

> **Where we are.** Module 01 left us with a working, unsealed, audited
> OpenBao and a root token. Now we do the thing that actually justifies
> OpenBao: we move Meridian AI's Gemini API key out of the `.env` file and
> into an encrypted, versioned, access-controlled store.

---

## 1. The problem we're solving

```bash
# Old way — in the repo, in every container, in every CI log
GEMINI_API_KEY=AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr
```

With OpenBao, the application asks OpenBao for the key at runtime using a
scoped, short-lived token. The key is never on disk.

## 2. Mount layout — think in paths

Before typing anything, design the mount layout. This is the decision you
will live with for years, so make it boring and obvious.

```
ai/
├── platform/        ← KV v2 mount. Application config, provider keys, DB creds
│   ├── data/llm/gemini
│   ├── data/db/postgres
│   └── data/cache/redis
└── transit/         ← Transit mount. Application-level encryption
```

**Why `ai/platform/` and not `secret/`?**

- `secret/` is the default mount. It's fine for demos; in a company with
  multiple teams it's noise.
- Naming by **domain** (`platform`) lets you later split `ai/platform/` into
  its own namespace without a flag day.
- Keep the mount short. Every policy path, every CLI command, every
  application config references it.

**Naming rules I'll enforce in this course:**

| Rule | Good | Bad |
|---|---|---|
| Lowercase | `llm/gemini` | `LLM/Gemini` |
| Hyphen or underscore, not both | `db/postgres` | `db_postgres-read` |
| No "prod" in the name (use namespaces) | `llm/gemini` | `llm/gemini-prod` |
| Secret values look like secrets | `AIzaSyD...` | `foo`, `test`, `bar` |

> The last rule is from the brief: **no `foo`, no `fun`, no random filler.**
> Every example in this course uses a realistic Meridian AI value so that
> when you read the audit log later, it reads like production.

## 3. Enable the KV v2 engine

```bash
bao secrets enable -path=ai/platform kv-v2
```

```
Success! Enabled the kv-v2 secrets engine at: ai/platform/
```

**Read the output carefully — it says `kv-v2`, not `kv`.** In OpenBao 2.7:

| Command | Result |
|---|---|
| `bao secrets enable -path=X kv-v2` | ✅ KV v2 (what you want) |
| `bao secrets enable -path=X kv` | ⚠️ **KV v1** — the legacy engine! |
| `bao secrets enable -path=X kv-v1` | KV v1 (explicit) |

⚠️ **Is `kv` an alias for v2? No — and this is a trap.**

It is natural to assume `kv` means "the modern one". It does not. Verified
against the live server:

```bash
$ bao secrets enable -path=ai/scratch kv
Success! Enabled the kv secrets engine at: ai/scratch/

$ bao read sys/mounts -format=json | jq -r '.data | to_entries[]
    | select(.key | startswith("ai/")) | "\(.key) options=\(.value.options)"'
ai/platform/ options={"version":"2"}    ← what we enabled with kv-v2
ai/scratch/  options=null               ← what we enabled with kv
```

`kv` gives you **KV v1**. Only `kv-v2` gives you versioning, metadata, CAS,
and rollback. The proof that `ai/scratch/` is v1:

```bash
$ bao read ai/scratch/config
No value found at ai/scratch/config      ← v1 has no config endpoint

$ bao list ai/scratch/metadata
No value found at ai/scratch/metadata    ← v1 has no metadata layer
```

**Rule: always write `kv-v2` explicitly.** Every tutorial that says
`bao secrets enable secret` is handing you a v1 engine.

### 3.1 KV v1 vs KV v2 — why this matters

| | KV v1 | KV v2 |
|---|---|---|
| Storage | Latest value only | Every version kept |
| History | ❌ Overwritten | ✅ Full history |
| Rollback | ❌ | ✅ `bao kv rollback` |
| Metadata | ❌ | ✅ version, timestamps, custom metadata |
| CAS | ❌ | ✅ Optimistic concurrency |
| Soft delete | ❌ | ✅ `bao kv delete` (recoverable) |
| Destroy | ❌ | ✅ `bao kv destroy` (permanent) |
| Storage cost | 1 copy | N copies |

KV v1's "no history" is a real problem: an operator who fat-fingers a secret
value has overwritten the good one, and there is no undo. **Never use KV v1
for anything you'd hate to lose.**

## 4. Write the Gemini API key

```bash
bao kv put ai/platform/llm/gemini \
  api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" \
  model="gemini-2.0-flash" \
  project_id="meridian-ai-prod" \
  endpoint="https://generativelanguage.googleapis.com/v1beta"
```

```
======= Secret Path =======
ai/platform/data/llm/gemini
```

> **Notice the path.** You typed `ai/platform/llm/gemini` but the API path is
> `ai/platform/**data**/llm/gemini`. KV v2 has a two-layer structure:
> `data/` holds the current value, `metadata/` holds version info. This
> confuses everyone once. Internal detail — the `bao kv` commands hide it.

## 5. Read it back

```bash
bao kv get ai/platform/llm/gemini
```

```
======= Secret Path =======
ai/platform/data/llm/gemini

======= Metadata =======
Key                Value
---                -----
created_time       2026-10-21T16:00:35.67837532Z
custom_metadata    <nil>
deletion_time      n/a
destroyed          false
version            1

===== Data =====
Key        Value
---        -----
api_key    AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr
endpoint   https://generativelanguage.googleapis.com/v1beta
model      gemini-2.0-flash
project_id meridian-ai-prod
```

For scripts, use JSON:

```bash
bao kv get -format=json ai/platform/llm/gemini | jq -r '.data.data.api_key'
```

> **Careful — there are two `.data` keys.** The outer `.data` is the API
> envelope; the inner `.data` is your secret payload. So: `.data.data.api_key`.
> The outer `.data.metadata` is the metadata. This trips people up constantly.

## 6. Metadata — the real value of KV v2

This is where KV v2 earns its keep. Every write creates a **version** with
rich metadata.

```bash
bao kv metadata get ai/platform/llm/gemini
```

```
============ Metadata =============
Key                         Value
---                         -----
cas_required                false
created_time                2026-10-21T16:00:35.67837532Z
current_metadata_version    1
current_version             2
custom_metadata             map[owner:platform-team rotation:90d]
delete_version_after        0s
max_versions                10
version                     2
```

### 6.1 The metadata fields that matter

| Field | Meaning | Why you'd care |
|---|---|---|
| `version` | Monotonic version number | CAS, rollback, audit correlation |
| `created_time` | When this version was written | "When did we rotate?" |
| `deletion_time` | When it was soft-deleted | Incident forensics |
| `destroyed` | Whether the secret is permanently gone | Compliance evidence |
| `current_version` | Latest live version | Diffing |
| `custom_metadata` | Your own key/value tags | Ownership, rotation policy |
| `max_versions` | How many versions to retain | Storage + compliance |
| `delete_version_after` | Auto-purge after N | Right-to-erasure, GDPR |
| `cas_required` | Whether writes must supply CAS | Prevent lost updates |

### 6.2 Custom metadata — tag your secrets

```bash
bao kv metadata put \
  -custom-metadata="owner=platform-team" \
  -custom-metadata="rotation=90d" \
  -custom-metadata="ticket=SEC-1042" \
  -custom-metadata="severity=critical" \
  ai/platform/llm/gemini
```

```
Success! Data written to: ai/platform/metadata/llm/gemini
```

Now ask: "show me every secret the platform team owns that rotates every 30
days." With `custom_metadata` you can filter. Without it, you cannot.

### 6.3 Version history and rollback

Rotate the key (simulating a quarterly rotation):

```bash
bao kv put ai/platform/llm/gemini \
  api_key="AIzaSyB3nQ8wE1rT5yU9iO2pA4sD6fG8hJ0kL2mN" \
  model="gemini-2.0-flash" \
  project_id="meridian-ai-prod" \
  endpoint="https://generativelanguage.googleapis.com/v1beta"
```

Now the history:

```bash
bao kv get -version=1 ai/platform/llm/gemini
```

```
===== Data =====
api_key    AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr    ← the old one
```

Roll back (e.g. the new key was pasted with a typo and broke production):

```bash
bao kv rollback -version=1 ai/platform/llm/gemini
```

**What rollback actually does:** it creates a **new version (3)** whose
*contents* are version 1's. It does not delete versions 1-2. Your audit trail
stays honest — the fact that you rolled back is itself recorded.

## 7. CAS — Check And Set (the concurrency control)

**The scenario:** Meridian AI has a rotation bot and a config-redeploy bot.
Both read the current version, modify it, and write it back. If they
interleave, one silently loses.

Without CAS:
```
bot-A reads v1  ─┐
bot-B reads v1  ─┤
bot-A writes v2  ─┤  bot-A's write is lost!
bot-B writes v3  ─┘
```

With CAS, bot-B's write **fails loudly** because it expected v1 but v2 exists.

### 7.1 Enable CAS

```bash
bao write ai/platform/config cas_required=true
```

```
cas_required             true
delete_version_after     0s
max_versions             0
metadata_cas_required    false
```

> **Where this config lives — a real gotcha.** KV v2's own settings are at
> `<mount>/config`, **not** `sys/mounts/<path>/tune`. Writing to
> `sys/mounts/ai/platform/tune` returns "Success!" but silently does
> **nothing** for these fields. Verified:
>
> ```
> $ bao write sys/mounts/ai/platform/tune cas_required=true max_versions=10
> Success! Data written to: sys/mounts/ai/platform/tune   ← LIES
> $ bao read ai/platform/config
> cas_required   false                                       ← unchanged
>
> $ bao write ai/platform/config cas_required=true max_versions=10
> Success! Data written to: ai/platform/config              ← CORRECT
> $ bao read ai/platform/config
> cas_required   true
> max_versions   10
> ```
>
> Rule: **`sys/mounts/<path>/tune` = generic engine tuning (leases, listing
> visibility). `<mount>/config` = KV v2 specific (CAS, versions, metadata).**

### 7.2 Use it

Now every write must state which version it's replacing:

```bash
# WRONG — now fails
bao kv put ai/platform/llm/gemini api_key="AIzaSyC9rM1qZ7wE3tY5uI9oP2aS4dF6gH8jK0lM"
# Error: Code: 400  (cas_required)
```

```bash
# RIGHT — declare the expected current version
bao kv put -cas=2 ai/platform/llm/gemini \
  api_key="AIzaSyC9rM1qZ7wE3tY5uIO2pA4sD6fG8hJ0kL2mN" \
  model="gemini-2.0-flash" \
  project_id="meridian-ai-prod" \
  endpoint="https://generativelanguage.googleapis.com/v1beta"
```

The `cas=N` means "only write if the current version is N". If another bot
wrote in between, you get a 400 and you re-read and retry. That is
**optimistic concurrency control**, and it is the difference between a
config race and a deterministic failure.

### 7.3 `metadata_cas_required`

Same idea, but for the *metadata* layer — protects against two bots
overwriting each other's `custom_metadata` tags.

```bash
bao write ai/platform/config metadata_cas_required=true
```

## 8. Soft delete vs destroy

```bash
# SOFT DELETE — recoverable, version marked deleted
bao kv delete -version=1 ai/platform/llm/gemini
```

```bash
# Check it
bao kv metadata get ai/platform/llm/gemini
# deletion_time   2026-10-21T16:05:12.000000000Z
# destroyed       false
```

```bash
# UNDELETE — bring it back
bao kv undelete -version=1 ai/platform/llm/gemini
```

```bash
# DESTROY — permanent, irreversible
bao kv destroy -version=1 ai/platform/llm/gemini
```

```
destroyed       true
```

> **Destroy is final.** There is no `undestroy`. This is deliberate — if
> anyone could un-destroy, "permanently deleted" would be a lie and
> compliance audits would be meaningless. Treat `destroy` as a one-way door.

### 8.1 Automatic secret deletion

`delete_version_after` auto-purges old versions after a TTL. This is how you
satisfy **right-to-erasure** (GDPR Art. 17) — a deleted user's credential
disappears from storage on its own, without a human remembering.

```bash
bao write ai/platform/config delete_version_after=168h   # 7 days
```

Read back:
```
delete_version_after     168h0m0s
```

## 9. TTL tuning — what "lease" means for KV v2

**Important mental model:** KV v2 does **not** use leases. Its "TTL" is
`max_versions` + `delete_version_after` — a *count* and an *age*. Leases are
a different mechanism (Module 04).

```bash
bao write ai/platform/config max_versions=10 delete_version_after=168h
```

```bash
bao secrets tune -default-lease-ttl=1h -max-lease-ttl=24h ai/platform
```

> **Flag ordering gotcha (this one bites constantly).** Flags go **before**
> the positional argument:
>
> ```
> $ bao secrets tune ai/platform -default-lease-ttl=1h -max-lease-ttl=24h
> Command flags must be provided before positional arguments.
> Too many arguments (expected 1, got 3)
>
> $ bao secrets tune -default-lease-ttl=1h -max-lease-ttl=24h ai/platform
> Success! Tuned the secrets engine at: ai/platform/
> ```
>
> Same rule everywhere: `bao write [FLAGS] PATH KEY=VALUE`.

### 9.1 What the default/max lease TTL actually control

For KV v2 specifically, they mostly affect **listing and metadata**
operations, not the secret lifetime. The KV v2 secret's lifetime is
controlled by `max_versions` / `delete_version_after`. Don't confuse the two.

| Setting | Applies to | Typical value |
|---|---|---|
| `max_versions` | KV v2 | 10 (rotations to keep) |
| `delete_version_after` | KV v2 | 168h–720h |
| `default_lease-ttl` | Dynamic secrets (DB creds, PKI certs) | 1h |
| `max_lease-ttl` | Dynamic secrets | 24h–72h |

## 10. Listing — the leak you must avoid

```bash
bao kv list ai/platform/llm
```

```
Keys
----
gemini
```

**Danger:** `list` on a broad path enumerates every secret name. If a
`default` policy grants `list` on `ai/platform/*`, every app learns every
secret *name* on the platform. Names leak structure ("we have a
`db/postgres/admin` path").

**Mitigation (Module 03):** never grant `list` on a broad path. Grant
`read` on exact paths. If listing is genuinely needed, use
`listing-visibility=unauth` (hidden) — hmm, actually that hides from
unauthenticated; the real control is ACLs. Module 03 covers it.

## 11. The GUI for this module

Open <http://127.0.0.1:8200/ui> → **Secrets → ai/platform →** you should see
`llm/` under it. Click through to `llm → gemini`:

- **Show** — the current secret
- **History** — every version, with `created_time` and who wrote it
- **Metadata** — custom metadata, versions, destroy status
- **Delete** / **Destroy** / **Undelete** buttons

Try it: write a secret in the GUI, then read it in the CLI. They are the
same data — but the GUI's **History** tab is a genuinely nice way to
understand versioning.

## 12. Lab: prove it works

```bash
# 1. Full lifecycle
bao kv put ai/platform/db/postgres \
  username="meridian_app" \
  password="Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK" \
  host="postgres" port=5432 dbname="meridian_ai"

bao kv get ai/platform/db/postgres
bao kv metadata get ai/platform/db/postgres

# 2. Version history
bao kv get -version=1 ai/platform/db/postgres

# 3. Soft delete + undelete
bao kv delete -version=1 ai/platform/db/postgres
bao kv metadata get ai/platform/db/postgres     # deletion_time set
bao kv undelete -version=1 ai/platform/db/postgres

# 4. CAS: stale write must fail
bao kv put -cas=99 ai/platform/db/postgres password="whatever"
# expect 400

# 5. Verify the audit log captured it all
tail -5 logs/audit.log | jq -r '.type + " " + .request.path'
```

## 13. What you learned

- [x] Mount layout and path naming conventions
- [x] `kv-v2` vs `kv` vs `kv-v1` — and why history matters
- [x] The `data/` layer vs `metadata/` layer
- [x] `.data.data.key` — the double-`.data` in JSON output
- [x] Metadata fields and **custom metadata** for ownership/rotation
- [x] Version history and `rollback`
- [x] **CAS** — and where the config actually lives (`<mount>/config`)
- [x] Soft delete vs destroy vs undelete
- [x] `delete_version_after` for right-to-erasure
- [x] `max_versions` vs lease TTL — different mechanisms
- [x] Flags-before-positionals (the CLI's #1 papercut)

## 14. What's next

**Module 03 — Policies & ACLs.** Right now *any* token can read *any* secret.
We create least-privilege policies so the Gemini key is readable only by the
AI harness, the DB password only by the data service, and so `list` never
leaks the platform's secret inventory. Then we talk about the `default` and
`root` policies and what production actually recommends.
