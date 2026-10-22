# Module 02 — KV v2: Storing Meridian AI's Gemini API Key

> **Where we are.** Module 01 left you with a running, unsealed OpenBao 2.7.1
> server, a root token in your shell, and an audit log that records every
> request. The Gemini API key is still living in a `.env` file in a Git
> repository. This module moves it into OpenBao — and, more importantly, gives
> it version history, an ownership trail, a rotation deadline, and the
> ability to roll back a bad write at 3am without lying to the audit log.

**Status:** complete. Every command and every output block in this module was
executed against a live OpenBao **v2.7.1** server (`pebbledb` storage, 3
unseal shares / threshold 2, audit device `local-file` with `log_raw = false`).

---

## 0. The 60-second version

If you read nothing else, read this.

| Concept | One-line meaning | Why it exists |
|---|---|---|
| **Mount** | A named, isolated place inside OpenBao where one kind of secret lives | So the Gemini key and the Postgres password aren't one undifferentiated pile |
| **`kv-v2` vs `kv`** | `kv-v2` is versioned; `kv` is the **legacy v1** engine | v1 has no version history, no metadata, no rollback, no CAS |
| **Two layers** | `data/` holds the secret; `metadata/` holds the version bookkeeping | Lets you read the secret without ever returning bookkeeping to the app |
| **Version** | Every write creates a new immutable version | Rollback, forensics, "what did this key look like last Tuesday" |
| **CAS** (check-and-set) | "Only write if the current version is still N" | Stops two writers from silently clobbering each other |
| **`<mount>/config`** | Where KV v2's knobs really live | `sys/mounts/<path>/tune` accepts these writes and **silently does nothing** |
| **Custom metadata** | Free-form labels attached to a secret | Owner, rotation policy, ticket number, environment |
| **Rollback** | Restores old *content* by writing it **as a new version** | The audit trail stays honest — a rollback is itself an event |
| **Soft delete** | Marks a version deleted; **recoverable** | "I deleted the wrong key" is not a 3am disaster |
| **Destroy** | Permanently erases a version; **irreversible** | True right-to-erasure for a secret you must not keep |
| **`delete_version_after`** | The secret stops being readable at a deadline | Right-to-erasure for PII, session keys, throwaway credentials |
| **`max_versions`** | How many versions of *one secret* to keep | Bounds history growth; unrelated to lease TTL |
| **`list`** | Returns the **names** of secrets under a path | A read-adjacent capability that leaks your secret inventory |

---

## 1. The problem we're solving

Here is the state of Meridian AI's repo as you inherit it:

```bash
# .env  — committed to Git, three weeks ago, still on main
GEMINI_API_KEY=AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr
POSTGRES_PASSWORD=Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK
REDIS_PASSWORD=Yb3mQ8vT1xW6rK4pL9zD2nF7gH5jA0sC4eU
KEYCLOAK_CLIENT_SECRET=meridian-ai-harness-client-secret-rotate-me
```

Ask the six questions from Module 01 about that file:

| Question | Answer for a `.env` file in Git |
|---|---|
| Who can read it? | Everyone with repo read access — contractors, CI, every laptop clone |
| Is it in Git history? | Yes. Deleting the file does not delete the commit. |
| Can you rotate it? | Yes, but only by editing a file and redeploying everything |
| Can you audit it? | No. There is no record of who read the key, or when |
| Can you scope it? | No. The `ai-harness` container gets the Postgres password too |
| Does it reach the app at runtime? | Only as an environment variable, baked into the image layer |

OpenBao gives you a **different kind of answer** to each of those. This
module builds the storage layer of that answer: the Gemini key lives in
OpenBao, encrypted at rest, versioned, attributable, and reachable only
through a scoped token.

> **Production:** *Do not put the `.env` file back once this module is done.
> The point is not "we also have a copy in OpenBao" — the point is that the
> `.env` file no longer exists anywhere in the estate.*

---

## 2. Mount layout — design it before you type a single command

Before you enable anything, decide where things live. You will live with this
layout for years, and every policy path, every CLI command, and every
application config will reference it. Make it boring and obvious.

```
ai/
├── platform/            ← KV v2 mount. Application config and provider credentials
│   ├── data/llm/gemini
│   ├── data/db/postgres
│   ├── data/cache/redis
│   └── data/oidc/keycloak
├── transit/             ← Transit mount. Application-level encryption (Module 06)
├── pki/                 ← PKI mount. Internal TLS (Module 08)
└── ssh/                 ← SSH mount. Signing user certificates (Module 08)
```

**Why `ai/platform/` and not `secret/`?**

| Candidate | Verdict |
|---|---|
| `secret/` | The default mount. Fine for a tutorial. At Meridian AI it is noise — "secret" tells you nothing about the owner or the blast radius. |
| `ai/platform/` | Names the **domain**. If Meridian AI later needs to hand the whole platform to a subsidiary, `ai/platform/` can move into its own namespace without renaming a single path. |
| `ai/` for everything | Tempting and wrong. You will add transit, pki and ssh engines, and then you cannot give the `data-pipeline` service read access to the Gemini key without also giving it the PKI CA. |

**Naming rules I will enforce for the rest of this course:**

| Rule | Good | Bad |
|---|---|---|
| Lowercase only | `llm/gemini` | `LLM/Gemini` |
| One separator style | `db/postgres` | `db_postgres`, `db-postgres` |
| No environment suffix in the path | `llm/gemini` | `llm/gemini-prod`, `llm/gemini-staging` |
| Name the thing, not the value | `db/postgres` | `db/Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK` |
| Values look like real credentials | `AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr` | `foo`, `bar`, `test`, `changeme` |

> **The "no `prod` suffix" rule needs defending.** It looks like a naming
> preference; it is really a *blast-radius* decision. If `gemini-prod` is a
> path, then separating production from staging requires separate mounts,
> separate policies, and separate namespaces — and every one of those is a
> thing you can get wrong. If `gemini` is a path, the separation lives in the
> **namespace** or the **mount**, and the paths inside stay identical. Same
> application code, different mount. Module 04 shows how that works.
>
> **Trade-off:** *no environment in the path means you must remember to pick
> the right mount.* That is a real operational tax, paid at deploy time
> rather than at 3am-when-a-token-expired time. I take that trade every time.

---

## 3. Enable the engine — and do not get this wrong

**What is a mount?** A mount is a named, isolated place inside OpenBao where
one kind of secret lives, with its own engine, its own rules, and its own
access-control surface.

*Why it exists:* so the Gemini key and the Postgres password aren't one
undifferentiated pile. Each engine enforces its own rules about how things
are stored, leased, and revoked.

*What if you skipped it:* everything would live in one generic bucket, and
you could never give the `ai-harness` service access to the Gemini key
without also giving it the database password. Module 03 builds exactly that
separation, on the back of the mount boundary you create here.

### 3.1 The trap: `kv` is KV **v1**

The command you will find in most tutorials is:

```bash
bao secrets enable -path=ai/platform kv-v2
```

But people type `kv` all the time, because "kv" is what the engine is
called, and because Vault's default mount is literally called `secret/`.

**`kv` and `kv-v2` are different engines.** `kv` is the legacy **version 1**
engine. It has no version history, no metadata layer, no rollback, and no
check-and-set. Everything in this module depends on v2, and a v1 mount will
fail in ways that look like bugs.

Here is the proof, run on the live server:

```bash
$ bao secrets enable -path=ai/platform kv-v2
Success! Enabled the kv-v2 secrets engine at: ai/platform/

$ bao secrets enable -path=ai/scratch kv
Success! Enabled the kv secrets engine at: ai/scratch/
```

Notice the two success messages differ: `kv-v2 secrets engine` versus
`kv secrets engine`. The CLI is telling you which one you got, in the one
line most people skim past.

Now the authoritative check — the mount table:

```bash
$ bao read sys/mounts -format=json | jq -r '.data | to_entries[]
    | select(.key|startswith("ai/")) | "\(.key) options=\(.value.options)"'
ai/platform/ options={"version":"2"}
ai/scratch/ options=null
```

`options={"version":"2"}` is the v2 marker. `options=null` is v1. That
single field is the whole difference, and it is the only thing that
distinguishes them.

### 3.2 The listing hides the difference — that is the real trap

```bash
$ bao secrets list
Path            Type         Accessor              Description
----            ----         --------              -----------
ai/platform/    kv           kv_267fde5b           n/a
ai/scratch/     kv           kv_d6a95c53           n/a
cubbyhole/      cubbyhole    cubbyhole_ba31d0f3    per-token private secret storage
identity/       identity     identity_f3d8c479     identity store
sys/            system       system_63c67a9c       system endpoints used for control, policy and debugging
```

Both rows say `Type: kv`. `bao secrets list` does **not** tell you which
version you have. (The `Accessor` column is a random string generated when
the mount is created — yours will be different, and that is fine. What
matters is the `Type` column, and it lies to you here.) If you trust the listing, you will not notice you have a
v1 mount until the day you try to roll back a bad write and OpenBao tells
you it cannot.

> **If you find a tutorial saying `bao secrets enable -path=secret kv` and
> then showing you version history:** it is describing HashiCorp Vault's
> behaviour on a *pre-0.10* Vault, or it is simply wrong. In OpenBao 2.7,
> `kv` is v1 and `kv-v2` is v2. Always check `sys/mounts`.

### 3.3 You already made the mistake — here is the fix

If you already created a v1 mount, you do not have to delete it and start
over. OpenBao can upgrade the mount in place:

```bash
$ bao secrets enable -path=ai/legacy2 kv
Success! Enabled the kv secrets engine at: ai/legacy2/

$ bao read sys/mounts/ai/legacy2 -format=json | jq '{type: .data.type, options: .data.options}'
{
  "type": "kv",
  "options": null
}

$ bao kv put ai/legacy2/llm/gemini api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" model="gemini-2.0-flash"
Success! Data written to: ai/legacy2/llm/gemini

$ bao kv enable-versioning ai/legacy2
Success! Tuned the secrets engine at: ai/legacy2/

$ bao read sys/mounts/ai/legacy2 -format=json | jq '{type: .data.type, options: .data.options}'
{
  "type": "kv",
  "options": {
    "version": "2"
  }
}
```

The pre-existing v1 secret is not orphaned — it is carried across as
version 1 of the new v2 store:

```bash
$ bao kv get -format=json ai/legacy2/llm/gemini | jq .data
{
  "data": {
    "api_key": "AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr",
    "model": "gemini-2.0-flash"
  },
  "metadata": {
    "created_time": "2026-10-21T16:42:47.107962256Z",
    "custom_metadata": null,
    "deletion_time": "",
    "destroyed": false,
    "version": 1
  }
}
```

> **Production:** *If a v1 mount is already in production, `enable-versioning`
> is the low-risk path — no data migration, no downtime. Do it, then check
> `sys/mounts` to confirm `options.version` is `"2"`.*

### 3.4 What a v1 mount cannot do

Here are three commands run against a genuine v1 mount — `ai/scratch`, the
one you created in section 3.1. (`ai/legacy2` will not do: section 3.3
already upgraded it to v2.) These error messages are worth memorising,
because "Metadata not supported on KV Version 1" is what a wrong mount
looks like when it is three weeks old and somebody asks for version history.

```bash
$ bao kv metadata get ai/scratch/llm/gemini
Metadata not supported on KV Version 1
exit=1

$ bao read ai/scratch/config
No value found at ai/scratch/config
exit=2

$ bao kv rollback -version=1 ai/scratch/llm/gemini
K/V engine mount must be version 2 for rollback support
exit=2
```

| Capability | KV v1 (`kv`) | KV v2 (`kv-v2`) |
|---|---|---|
| Version history | ❌ one value, overwritten | ✅ every write is a version |
| Metadata layer | ❌ `Metadata not supported on KV Version 1` | ✅ `bao kv metadata get` |
| Config endpoint | ❌ `No value found at <mount>/config` | ✅ `bao write <mount>/config ...` |
| Rollback | ❌ `K/V engine mount must be version 2 for rollback support` | ✅ `bao kv rollback` |
| Check-and-set | ❌ | ✅ `-cas=N` |
| Custom metadata | ❌ | ✅ `-custom-metadata=owner=...` |
| Soft delete / undelete | ❌ | ✅ |
| `max_versions` | ❌ | ✅ |
| `delete_version_after` | ❌ | ✅ |

---

## 4. Write the Gemini key

**What is a write?** A write creates a new, immutable version of a secret.
It never modifies an existing version in place.

*Why it exists:* so that "what did this key look like on 3 March?" is a
question with an answer.

*What if you skipped it:* you would overwrite the only copy of a credential
the moment somebody fat-fingers a `kubectl set`, and the recovery path
would be "ask the provider to issue a new key and hope nobody noticed".

The command:

```bash
$ bao kv put ai/platform/llm/gemini \
    api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" \
    model="gemini-2.0-flash" \
    project_id="meridian-ai-prod-01"
======= Secret Path =======
ai/platform/data/llm/gemini

======= Metadata =======
Key                Value
---                -----
created_time       2026-10-21T16:41:50.467999281Z
custom_metadata    <nil>
deletion_time      n/a
destroyed          false
version            1
```

Read that output carefully. Three things to notice:

1. `======= Secret Path =======` says `ai/platform/data/llm/gemini`. You
   asked for `ai/platform/llm/gemini`. The `data/` segment was inserted for
   you. That is the v2 layout: **the mount, then `data/`, then your path.**
2. `version 1` — you now have one version.
3. `custom_metadata <nil>` and `deletion_time n/a` — nothing set yet.

### 4.1 The `data/` segment

**What is the `data/` segment?** A literal path component that separates the
secret values from the version bookkeeping inside the same mount.

*Why it exists:* so that reading a secret and reading its metadata are two
different API paths, and so that a policy can grant "read this secret"
without also granting "read every version of every secret".

*What if you skipped it:* you would have to rewrite every path in every
client when you upgraded from v1 to v2 — which is exactly why OpenBao
refuses to do that upgrade for you automatically.

```
ai/platform/            ← the mount
└── data/               ← KV v2 secret values live here
    └── llm/gemini      ← your path
```

The metadata side has its own segment, and you will meet it in section 6:

```
ai/platform/
└── metadata/
    └── llm/gemini
```

---

### 4.2 The other three secrets

Meridian AI does not run on one credential. While you are here, create the
rest of the platform's secrets so the rest of this module has something real
to work on.

> **Read this carefully — it is the single most common way a learner gets
> stuck in this module.** Sections 10 and 11 operate on these three secrets
> (`db/postgres`, `cache/redis`, `oidc/keycloak`). If you skip this section,
> those sections will answer `No value found at ai/platform/data/db/postgres`
> and you will think OpenBao is broken. It is not — you never created them.

Each one is a first write, so each needs `-cas=0`: *"I expect the current
version to be 0, i.e. nothing there yet."* If you skip the `-cas`, the
write is rejected with `check-and-set parameter required for this call`.

```bash
$ bao kv put -cas=0 ai/platform/db/postgres \
    username="meridian_app" \
    password="Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK" \
    host="postgres" port=5432 dbname="meridian_ai" sslmode=require
======= Secret Path =======
ai/platform/data/db/postgres

$ bao kv put -cas=0 ai/platform/cache/redis \
    host="redis" port=6379 \
    password="Yb3mQ8vT1xW6rK4pL9zD2nF7gH5jA0sC4eU" db=0
======= Secret Path =======
ai/platform/data/cache/redis

$ bao kv put -cas=0 ai/platform/oidc/keycloak \
    issuer="http://keycloak:8080/realms/meridian-ai" \
    client_id="ai-harness" \
    client_secret="meridian-ai-harness-client-secret-rotate-me" \
    admin_password="admin"
======= Secret Path =======
ai/platform/data/oidc/keycloak
```

Now you have four secrets, and every later section has something to bite on:

```bash
$ bao kv list ai/platform
Keys
----
cache/
db/
llm/
oidc/
```

> **Production:** *Real stores do not "just have the four secrets I need
> for the tutorial." They have a set of them, and the set is agreed on
> before anyone writes a value. Decide the mount layout and the path
> inventory first (§2), then fill it. A path nobody agreed on is a path
> nobody will rotate.*

---

## 5. Read it back — and meet the double `.data`

```bash
$ bao kv get ai/platform/llm/gemini
======= Secret Path =======
ai/platform/data/llm/gemini

======= Metadata =======
Key                Value
---                -----
created_time       2026-10-21T16:41:50.467999281Z
custom_metadata    <nil>
deletion_time      n/a
destroyed          false
version            1

===== Data =====
Key           Value
---           -----
api_key       AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr
model         gemini-2.0-flash
project_id    meridian-ai-prod-01
```

The human-readable form separates `Metadata` from `Data` for you. The JSON
form does not:

```bash
$ bao kv get -format=json ai/platform/llm/gemini | jq
{
  "request_id": "4ae77d3e-2e89-0486-231e-317332c987ed",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": {
    "data": {
      "api_key": "AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr",
      "model": "gemini-2.0-flash",
      "project_id": "meridian-ai-prod-01"
    },
    "metadata": {
      "created_time": "2026-10-21T16:41:50.467999281Z",
      "custom_metadata": null,
      "deletion_time": "",
      "destroyed": false,
      "version": 1
    }
  },
  "warnings": null
}
```

**There are two `.data` levels.** The outer `.data` is OpenBao's standard
API envelope — every OpenBao response has one. The inner `.data` is the KV v2
secret payload. The secret is therefore at `.data.data.<key>` and the
metadata is at `.data.metadata`.

```bash
# the secret
$ bao kv get -format=json ai/platform/llm/gemini | jq -r '.data.data.api_key'
AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr

# the version number
$ bao kv get -format=json ai/platform/llm/gemini | jq -r '.data.metadata.version'
1
```

> **The number one jq mistake in this entire course.** A team member of mine
> wrote `jq -r '.data.api_key'`, got `null`, and concluded the secret was
> not stored. It was stored. The path was wrong. When `jq` prints `null`,
> check your path *before* you check the server.
>
> **Production:** *In application code, never hand-roll this path. Write one
> helper — `read_secret(path) -> dict` — and have it return `.data.data`.
> Module 07 does exactly that, and it is 15 lines of `urllib`, not a
> dependency.*

### 5.2 The same secret on a v1 mount, for contrast

```bash
$ bao kv put ai/scratch/llm/gemini \
    api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" \
    model="gemini-2.0-flash" \
    project_id="meridian-ai-prod-01"
Success! Data written to: ai/scratch/llm/gemini

$ bao kv get -format=json ai/scratch/llm/gemini | jq
{
  "request_id": "65137c76-19c2-2d8d-735a-d4e8d81bb88b",
  "lease_id": "",
  "lease_duration": 2764800,
  "renewable": false,
  "data": {
    "api_key": "AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr",
    "model": "gemini-2.0-flash",
    "project_id": "meridian-ai-prod-01"
  },
  "warnings": null
}
```

Three differences, all of them real:

| | KV v1 | KV v2 |
|---|---|---|
| Path | `ai/scratch/llm/gemini` | `ai/platform/data/llm/gemini` |
| JSON shape | `.data.api_key` | `.data.data.api_key` |
| Lease | `lease_duration: 2764800` | `lease_duration: 0` |

The lease difference is the subject of section 13. It is the fingerprint of
a v1 mount, and it is worth recognising.

---

## 6. The two layers: `data/` and `metadata/`

**What is the metadata layer?** A parallel set of paths, under
`<mount>/metadata/`, that describe the versions of a secret without
containing the secret itself.

*Why it exists:* so that "list every version of the Gemini key and when
each was created" can be answered by a component that is allowed to read
metadata but not the secret values.

*What if you skipped it:* you would have to read the secret in order to
learn its version number, which means every audit-log reader, every backup
tool, and every "what changed?" query would also handle plaintext
credentials.

```bash
$ bao kv metadata get ai/platform/llm/gemini
======== Metadata Path ========
ai/platform/metadata/llm/gemini

============ Metadata ============
Key                         Value
---                         -----
cas_required                false
created_time                2026-10-21T16:41:50.467999281Z
current_metadata_version    0
current_version             1
custom_metadata             <nil>
delete_version_after        0s
max_versions                0
metadata_cas_required       false
oldest_version              0
updated_time                2026-10-21T16:41:50.467999281Z

====== Version 1 ======
Key              Value
---              -----
created_time     2026-10-21T16:41:50.467999281Z
deletion_time    n/a
destroyed        false
```

### 6.1 The fields, and which ones you actually set

| Field | Meaning | Set it? |
|---|---|---|
| `current_version` | The version a plain read returns | automatic |
| `current_metadata_version` | The version of the *metadata* itself | automatic |
| `oldest_version` | The oldest version still retained | automatic |
| `created_time` | When the secret was first written | automatic |
| `updated_time` | When the secret was last written | automatic |
| `custom_metadata` | Your own labels | **yes** |
| `cas_required` | Does *this* secret require check-and-set? | yes, per secret |
| `max_versions` | Per-secret override of the mount's cap | rarely |
| `delete_version_after` | Per-secret override of the mount's expiry | **yes, for PII** |
| `metadata_cas_required` | Does metadata need its own check-and-set? | yes, in production |
| `deletion_time` (per version) | When this version stops being readable | automatic |
| `destroyed` (per version) | Has this version been permanently erased? | automatic |

### 6.2 Two version series, not one

Look again at the output above: `current_version 1` and
`current_metadata_version 0`. These are **independent counters**.

- `current_version` counts *data* writes.
- `current_metadata_version` counts *metadata* writes (adding custom
  metadata, changing `max_versions`, and so on).

A metadata write does **not** create a new data version, and a data write
does **not** create a new metadata version. Here is the payoff: run the
module's own sequence and look at the block again afterwards.

By the end of **§9** — the data write in §8.4, then the metadata writes in
§8.6, §8.7 and §9 — the two counters read:

```bash
$ bao kv metadata get -format=json ai/platform/llm/gemini \
    | jq -r '.data | "current_version=\(.current_version) current_metadata_version=\(.current_metadata_version)"'
current_version=2 current_metadata_version=3
```

`current_version` is **2** — the §4 seed and the §8.4 write. The three
metadata writes (§8.6's ignored `cas_required=false`, §8.7's `metadata_cas`
write, and §9's `metadata put`) never touched it. `current_metadata_version`
is **3** — and the data writes never touched it.

> ⚠️ **Even a metadata write that the server *ignores* still counts.**
> §8.6 writes `cas_required=false` to the metadata path, the server warns
> that the value "will be ignored", and the value really is ignored — but the
> write still creates a metadata version. The counter tracks *write
> attempts*, not *value changes*.

§9.2's `metadata patch` takes the metadata counter to **4** and leaves the
data counter at **2**. The two counters diverge the first time you touch the
metadata of a secret that already has data, and that is what trips people
up.

> **Production:** *Never use `current_metadata_version` to decide whether to
> write data. Use `current_version`. They are different numbers and they
> will diverge.*

---

## 7. Configuration — where the knobs *really* live

**This is the second headline trap of the module, and it is worse than the
`kv` / `kv-v2` one, because this one lies to you.**

**What is mount configuration?** A set of server-side settings for an
engine: how many versions to keep, whether writes need check-and-set, how
long a version survives.

*Why it exists:* so these rules are enforced by the server, not by
whoever remembers to pass the right flag.

*What if you skipped it:* every client would have to remember to pass
`-cas=0` on first write and `-cas=<n>` thereafter, and one forgotten flag
would be a lost update.

### 7.1 The trap: `sys/mounts/<path>/tune` accepts the write and does nothing

The generic tune endpoint is for engine-wide settings: lease TTLs, cache
behaviour, description. It has nothing to do with KV v2's version settings.
And it will happily take your `cas_required` and `max_versions` and drop
them on the floor:

```bash
$ bao read ai/platform/config
Key                      Value
---                      -----
cas_required             false
delete_version_after     0s
max_versions             0
metadata_cas_required    false

$ bao write sys/mounts/ai/platform/tune cas_required=true max_versions=10
Success! Data written to: sys/mounts/ai/platform/tune

$ bao read ai/platform/config     <-- UNCHANGED
Key                      Value
---                      -----
cas_required             false
delete_version_after     0s
max_versions             0
metadata_cas_required    false
```

**`Success! Data written to: sys/mounts/ai/platform/tune`** — and nothing
about KV v2 changed. Not an error, not a warning. The fields were silently
discarded because they are not generic tune fields.

And here is the tune endpoint's own state, to show you where the two of
your values went (nowhere):

```bash
$ bao read sys/mounts/ai/platform/tune
Key                  Value
---                  ----
default_lease_ttl    768h
description          n/a
force_no_cache       false
max_lease_ttl        768h
options              map[version:2]
```

No `cas_required`. No `max_versions`. They were never stored.

### 7.2 The right endpoint: `<mount>/config`

```bash
$ bao write ai/platform/config cas_required=true max_versions=10 delete_version_after=0s
Success! Data written to: ai/platform/config

$ bao read ai/platform/config     <-- CHANGED
Key                      Value
---                      -----
cas_required             true
delete_version_after     0s
max_versions             10
metadata_cas_required    false
```

| What you want to set | Endpoint |
|---|---|
| `cas_required`, `max_versions`, `delete_version_after`, `metadata_cas_required` | `<mount>/config` — e.g. `ai/platform/config` |
| lease TTLs, description, cache control | `sys/mounts/<path>/tune` |
| per-secret overrides | `<mount>/metadata/<path>` — e.g. `ai/platform/metadata/llm/gemini` |

> **If you find a tutorial saying `bao write sys/mounts/secret/tune cas_required=true`:**
> it is describing HashiCorp Vault, where the KV v2 config also lives at
> `<mount>/config` — the tutorial is wrong there too. In OpenBao 2.7, the
> only way to set `cas_required` is `bao write <mount>/config ...` or the
> per-secret metadata endpoint.
>
> **Production:** *Never trust a "Success!" from a write. Always read the
> value back.* This is not a paranoia about the tool; it is that OpenBao
> will happily accept a write to the wrong endpoint and tell you it
> succeeded. In CI, make your config assertion a `read` and compare, not a
> `write` and hope.*

---

## 8. CAS — check-and-set

**What is CAS?** An extra field on a write that says "only apply this write
if the secret is still at version N".

*Why it exists:* to prevent a **lost update** — two writers both read
version 7, both modify it, both write, and the second write silently
destroys the first writer's change.

*What if you skipped it:* Meridian AI's `secret-rotation-bot` rotates the
Keycloak client secret at the same moment a human re-applies the Gemini key
by hand. Both read version 7. The bot writes version 8. The human writes
version 8 too. The human's write wins, and the bot's rotation is gone — no
error, no log line, no trace. CAS turns that silent loss into a loud 400.

### 8.1 The lost-update race, concretely

```
        t=0   bot:  GET  ai/platform/oidc/keycloak   -> version 7
        t=0   dev:  GET  ai/platform/oidc/keycloak   -> version 7
        t=1   bot:  PUT  (new rotated secret)        -> version 8   OK
        t=2   dev:  PUT  (hand-edited secret)        -> version 8   OK  <-- the bot's rotation is GONE
```

With CAS, the last line becomes:

```
        t=2   dev:  PUT  cas=7                       -> 400 "check-and-set parameter did not match the current version"
```

The developer retries, sees version 8, and re-applies their change on top.

### 8.2 The exact 400 for a missing CAS parameter

With `cas_required=true` on the mount, **every** write needs a CAS value —
including the very first one:

```bash
$ bao kv put ai/platform/llm/gemini \
    api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" \
    model="gemini-2.0-flash" \
    project_id="meridian-ai-prod-01"
Error writing data to ai/platform/data/llm/gemini: Error making API request.

URL: PUT http://127.0.0.1:9185/v1/ai/platform/data/llm/gemini
Code: 400. Errors:

* check-and-set parameter required for this call
exit=2
```

That is the exact error text, verbatim, with the real HTTP status code and
the real request path. Memorise the shape of it: **400, and the bullet
point `check-and-set parameter required for this call`.**

### 8.3 The exact 400 for a stale CAS value

`-cas=N` means "the current version must be exactly N". A stale value fails
with a *different* message — this is the one you will see in production,
because it means somebody else got there first:

```bash
$ bao kv put -cas=0 ai/platform/llm/gemini \
    api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" \
    model="gemini-2.0-flash" \
    project_id="meridian-ai-prod-01"
Error writing data to ai/platform/data/llm/gemini: Error making API request.

URL: PUT http://127.0.0.1:9185/v1/ai/platform/data/llm/gemini
Code: 400. Errors:

* check-and-set parameter did not match the current version
exit=2
```

| Error | Meaning |
|---|---|
| `check-and-set parameter required for this call` | You forgot `-cas=`. The secret's current version is unknown to you. |
| `check-and-set parameter did not match the current version` | You *knew* the version, but it has moved. Somebody else wrote in between. |

### 8.4 The correct write

```bash
$ bao kv put -cas=1 ai/platform/llm/gemini \
    api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" \
    model="gemini-2.0-flash" \
    project_id="meridian-ai-prod-01"
======= Secret Path =======
ai/platform/data/llm/gemini

======= Metadata =======
Key                Value
---                -----
created_time       2026-10-21T16:41:51.96107458Z
custom_metadata    <nil>
deletion_time      n/a
destroyed          false
version            2
```

### 8.5 `-cas=0` means "only create, never overwrite"

`-cas=0` is special: it asserts the secret does **not** exist yet. It is
the safe "create this secret, but fail if somebody beat me to it" write:

```bash
$ bao kv put -cas=0 ai/platform/db/postgres \
    host="meridian-db.internal" port=5432 database="meridian_ai" \
    username="meridian_app" password="Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK" \
    sslmode="verify-full"
======== Secret Path =========
ai/platform/data/db/postgres

======= Metadata =======
Key                Value
---                -----
created_time       2026-10-21T16:41:53.702515393Z
custom_metadata    <nil>
deletion_time      n/a
destroyed          false
version            1
```

**But `-cas=0` is not a create-only guard.** Once the secret exists, `-cas=0`
is simply a *stale* value and it fails with the "did not match" error,
exactly like any other wrong number. You saw that in section 8.3.

> **Production:** *Read the current version, then write with it:*
> ```bash
> v=$(bao kv metadata get -format=json "$path" | jq -r '.data.current_version')
> bao kv put -cas="$v" "$path" key=value
> ```
> *That is still a race — between your read and your write — but CAS shrinks
> the window from "however long the human took to type" to "milliseconds",
> and turns the remaining overlap into a loud error instead of a silent
> loss. A true compare-and-swap needs a server-side transaction; KV v2 does
> not offer one. This is the honest limit of the mechanism.*

### 8.6 Per-secret CAS, and the mandate warning

`cas_required` exists in two places: the mount config and the per-secret
metadata. The **mount** setting *mandates* CAS for every secret under it. The
per-secret setting can *add* the requirement to one secret.

Setting the per-secret flag to `false` while the mount mandates `true` does
nothing, and OpenBao tells you so:

```bash
$ bao write ai/platform/metadata/llm/gemini cas_required=false
WARNING! The following warnings were returned from OpenBao:

  * "cas_required" set to false, but is mandated by backend config. This value
  will be ignored.
```

The reverse direction works the other way round: with the mount's
`cas_required` off, a per-secret `cas_required=true` is still enforced, and
you get the same 400 as in section 8.2.

### 8.7 Metadata has its own CAS: `metadata_cas`

**Metadata is a separate write target, so it needs its own protection.**
The mount-level switch is `metadata_cas_required`:

```bash
$ bao write ai/platform/config metadata_cas_required=true
Success! Data written to: ai/platform/config

$ bao kv metadata put -custom-metadata="owner=platform-team" ai/platform/db/postgres
Error writing data to ai/platform/metadata/db/postgres: Error making API request.

URL: PUT http://127.0.0.1:9185/v1/ai/platform/metadata/db/postgres
Code: 400. Errors:

* metadata check-and-set parameter required for this call
exit=2
```

Note the word **metadata** in the error. That is how you tell a data-CAS
failure from a metadata-CAS failure at a glance.

The value is passed as the `metadata_cas` field. The `bao kv metadata put`
subcommand has no flag for it, so pass JSON on stdin:

```bash
$ echo '{"metadata_cas":0,"custom_metadata":{"owner":"platform-team"}}' | bao write ai/platform/metadata/db/postgres -
Success! Data written to: ai/platform/metadata/db/postgres

$ echo '{"metadata_cas":5,"custom_metadata":{"owner":"data-team"}}' | bao write ai/platform/metadata/db/postgres -
Error writing data to ai/platform/metadata/db/postgres: Error making API request.

URL: PUT http://127.0.0.1:9185/v1/ai/platform/metadata/db/postgres
Code: 400. Errors:

* metadata check-and-set parameter does not match the current version
exit=2
```

`metadata_cas=0` for the *first* metadata write (there is no metadata
version yet), and `metadata_cas=<current_metadata_version>` thereafter. Read
the value, then feed it straight back in:

```bash
$ mc=$(bao kv metadata get -format=json ai/platform/llm/gemini | jq -r '.data.current_metadata_version')
$ echo "{\"metadata_cas\":$mc,\"custom_metadata\":{\"owner\":\"platform-team\"}}" \
    | bao write ai/platform/metadata/llm/gemini -
Success! Data written to: ai/platform/metadata/llm/gemini
```

`metadata_cas=0` on a secret that already has metadata is a *stale* value
and fails with `metadata check-and-set parameter does not match the current
version` — the metadata twin of the data-CAS error.

One last thing before section 9: switch the mount-level metadata CAS back
off, so the friendly `bao kv metadata put` form works again. Section 16
turns it on for good and shows what that costs you.

```bash
$ bao write ai/platform/config metadata_cas_required=false
Success! Data written to: ai/platform/config
```

> **Gotcha:** `bao kv metadata put -cas-required=true` is a **boolean** — it
> means "this secret should require CAS for its *data* writes". It is *not*
> a check-and-set value. The metadata CAS value is the `metadata_cas` data
> field, and it only exists on the raw write path. Two different things,
> one confusingly similar flag name.

---

## 9. Custom metadata

**What is custom metadata?** A set of your own key/value labels stored
alongside a secret.

*Why it exists:* so that "who owns this secret, and when was it last
rotated?" is answerable by OpenBao instead of by a spreadsheet that drifts
out of date on day two.

*What if you skipped it:* your secret store becomes a blob store with extra
steps. Six months later nobody knows which of the four Gemini keys is live,
and rotation becomes a full-team archaeology project.

```bash
$ bao kv metadata put \
    -custom-metadata="owner=platform-team" \
    -custom-metadata="rotation=90d" \
    ai/platform/llm/gemini
Success! Data written to: ai/platform/metadata/llm/gemini
```

The flag is **repeatable** — one `-custom-metadata=` per pair. The result:

```bash
$ bao kv metadata get ai/platform/llm/gemini
...
custom_metadata             map[owner:platform-team rotation:90d]
...
```

### 9.1 A custom metadata scheme for Meridian AI

Pick a scheme and stick to it, or you will have `owner` on one secret,
`team` on another, and `owned-by` on a third.

| Key | Example value | What it is for |
|---|---|---|
| `owner` | `platform-team` | Which team gets paged when it breaks |
| `rotation` | `90d` | The agreed rotation interval |
| `last_rotated` | `2026-10-21` | When it was last changed |
| `ticket` | `MER-1841` | The change request that authorised it |
| `env` | `production` | Which deployment this copy serves |
| `consumed-by` | `ai-harness` | Which service reads it |

> **Production:** *Custom metadata is **not** secret. It is stored in the
> clear and shown in the GUI, in `bao kv metadata get`, and in the audit log
> (HMAC'd, but still a fixed-width string). Never put a password in it.*
> The audit log proves the point — with `log_raw = false`, even the *key
> names* come out HMAC'd:
>
> ```bash
> $ grep '"operation":"list"' logs/audit.log \
>     | jq -c 'select(.type=="response" and .request.path=="ai/platform/metadata/") | .response.data.keys' \
>     | grep -v null | tail -1
> ["hmac-sha256:5115bd6b15e0a486d1a9f93b795e438deceeb7a496272080930131ce89e097d3","hmac-sha256:1c1dedf5476fc1343602055920cf5869f7b57a7d2192e4605b4bfbc1d4fb9a4c","hmac-sha256:06409c028a113bbfde42c495f2e45d4f2217db68e50f7fc4edf0929f1a1f3d7e","hmac-sha256:a9118edc2fd2b231fd6092ecd2d00dde10ae353cea39a1e39c4fe1cc1d55bfb3"]
> ```
>
> So the audit log does not leak your secret inventory either. But custom
> metadata *values* are still readable by anyone with metadata read
> capability. Keep it to ownership metadata.

### 9.2 Patch and remove

`metadata put` replaces the whole custom-metadata map. `metadata patch`
merges, and can remove a single key:

```bash
$ bao kv metadata patch \
    -custom-metadata="last_rotated=2026-10-21" \
    -remove-custom-metadata="rotation" \
    ai/platform/llm/gemini
Success! Data written to: ai/platform/metadata/llm/gemini

$ bao kv metadata get ai/platform/llm/gemini
...
custom_metadata             map[last_rotated:2026-10-21 owner:platform-team]
...
```

`rotation` is gone, `last_rotated` was added, and `owner` was left alone.
Note `current_metadata_version` went up — a metadata write is a write, and
it has its own history.

And to wipe a secret's metadata history entirely, `metadata delete` removes
**every version and all metadata** for that path. It is not recoverable.

---

## 10. Version history and rollback

**What is a version?** An immutable snapshot of a secret, numbered from 1
upwards, with its own creation time and its own deletion state.

*Why it exists:* the whole point of KV v2 over KV v1.

*What if you skipped it:* every write is a gamble.

### 10.1 Build some history

Continuing with the Gemini key: version 1 is the good key, version 2 is a
CAS write, and now somebody fat-fingers the model name at 3am:

```bash
$ bao kv put -cas=2 ai/platform/llm/gemini \
    api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" \
    model="gemini-1.0-pro" \
    project_id="meridian-ai-prod-01"
======= Secret Path =======
ai/platform/data/llm/gemini

======= Metadata =======
Key                Value
---                -----
created_time       2026-10-21T16:41:52.340101492Z
custom_metadata    map[last_rotated:2026-10-21 owner:platform-team]
deletion_time      n/a
destroyed          false
version            3
```

Version 3 is wrong. The `ai-harness` container is now calling a
deprecated model and will start failing requests.

### 10.2 Roll back

```bash
$ bao kv rollback -version=2 ai/platform/llm/gemini
Key                Value
---                -----
created_time       2026-10-21T16:41:52.451532785Z
custom_metadata    map[last_rotated:2026-10-21 owner:platform-team]
deletion_time      n/a
destroyed          false
version            4
exit=0
```

**Look at what just happened.** You asked to go back to version 2. You got
**version 4**.

> **Rollback does not rewind. It appends.**
>
> - `current_version` went 3 → **4**.
> - Version 4 contains the *content* of version 2.
> - Version 3 — the bad write — **still exists and is still readable**.

The current version is now the good content again:

```bash
$ bao kv get ai/platform/llm/gemini            <-- current = version 4
======= Secret Path =======
ai/platform/data/llm/gemini

======= Metadata =======
Key                Value
---                -----
created_time       2026-10-21T16:41:52.451532785Z
custom_metadata    map[last_rotated:2026-10-21 owner:platform-team]
deletion_time      n/a
destroyed          false
version            4

===== Data =====
Key           Value
---           -----
api_key       AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr
model         gemini-2.0-flash
project_id    meridian-ai-prod-01
```

And the bad write is still there, because history is history:

```bash
$ bao kv get -version=3 ai/platform/llm/gemini  <-- the bad write is STILL THERE
======= Secret Path =======
ai/platform/data/llm/gemini

======= Metadata =======
Key                Value
---                -----
created_time       2026-10-21T16:41:52.340101492Z
custom_metadata    map[last_rotated:2026-10-21 owner:platform-team]
deletion_time      n/a
destroyed          false
version            3

===== Data =====
Key           Value
---           -----
api_key       AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr
model         gemini-1.0-pro
project_id    meridian-ai-prod-01
```

**Why does it work this way?** Because a secret store that could *rewrite
history* would be worthless as an audit trail. If a rollback rewound the
version counter, the audit log would show "version 3 never existed" — and
the one artefact you need during an incident would be the one thing the
system was allowed to lie about. A rollback that appends is a rollback that
is itself visible in the log.

The metadata reflects the new reality:

```bash
$ bao kv metadata get ai/platform/llm/gemini
...
current_version             4
...
====== Version 1 ======
...
====== Version 2 ======
...
====== Version 3 ======
...
====== Version 4 ======
```

### 10.3 The trap: `delete_version_after` blocks rollback

This one is not in any tutorial, and it will bite you in production.

Remember `delete_version_after`? It stamps a `deletion_time` on every
version it creates. And a version that carries a `deletion_time` **cannot
be rolled back to** — OpenBao treats it as deleted:

```bash
$ bao write ai/platform/config delete_version_after=168h
Success! Data written to: ai/platform/config

$ bao kv put -cas=4 ai/platform/llm/gemini \
    api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" \
    model="gemini-1.0-pro" \
    project_id="meridian-ai-prod-01"
======= Secret Path =======
ai/platform/data/llm/gemini

======= Metadata =======
Key                Value
---                -----
created_time       2026-10-21T16:41:53.07477273Z
custom_metadata    map[last_rotated:2026-10-21 owner:platform-team]
deletion_time      2026-10-28T16:41:53.07477273Z
destroyed          false
version            5
```

Version 5 now carries a `deletion_time` of seven days from now. Try to roll
back to it:

```bash
$ bao kv rollback -version=5 ai/platform/llm/gemini
Cannot roll back to a version that has been deleted
exit=2
```

And here is the nasty part — turning the setting back off does **not**
rescue it, because the `deletion_time` is stamped on the *version*, not
read from the mount at rollback time:

```bash
$ bao write ai/platform/config delete_version_after=0s   (mount config is NOT enough)
Success! Data written to: ai/platform/config

$ bao kv rollback -version=5 ai/platform/llm/gemini      (still refused)
Cannot roll back to a version that has been deleted
exit=2
```

The same distinction exists for destroyed versions, with a different
message. Destroy the Postgres secret's only version, then try to roll back
to it:

```bash
$ bao kv destroy -versions=1 ai/platform/db/postgres
Success! Data written to: ai/platform/destroy/db/postgres
exit=0

$ bao kv rollback -version=1 ai/platform/db/postgres
Cannot roll back to a version that has been destroyed
exit=2
```

| Situation | Rollback error |
|---|---|
| Target version has a `deletion_time` (soft-deleted, or `delete_version_after` stamped it) | `Cannot roll back to a version that has been deleted` |
| Target version was `destroy`ed | `Cannot roll back to a version that has been destroyed` |

> **Production:** *Do not set `delete_version_after` at the mount level for
> a store where you want rollback. Set it per secret, and only on the
> secrets that genuinely must expire — session keys, one-time credentials,
> anything holding PII. A mount-wide `delete_version_after` silently
> disarms your rollback button for every version created while it was
> active, and versions created while it was active are permanently
> ineligible.*
>
> **Trade-off:** *Right-to-erasure and rollback are in genuine tension.
> "Delete this after 7 days" and "let me roll back to any of my last ten
> versions" cannot both be true for the same version. You have to pick per
> secret, deliberately, and record the decision in custom metadata.*

### 10.4 `max_versions` — the sliding window

`max_versions` caps how many versions of a single secret are retained. The
oldest is pruned automatically as new ones arrive.

```bash
$ bao write ai/platform/config max_versions=3
Success! Data written to: ai/platform/config
```

Now rotate the Keycloak secret five times. Each rotation is a normal write
that declares which version it expects to replace — that is the CAS you
learned in §8, doing its job of stopping two rotations from clobbering each
other:

```bash
$ bao kv put -cas=1 ai/platform/oidc/keycloak \
    issuer="http://keycloak:8080/realms/meridian-ai" \
    client_id="ai-harness" \
    client_secret="meridian-ai-harness-client-secret-rotate-me" \
    admin_password="admin" rotation=2
# rotation 1 -> current_version 2, oldest_version 0

$ bao kv put -cas=2 ai/platform/oidc/keycloak \
    issuer="http://keycloak:8080/realms/meridian-ai" \
    client_id="ai-harness" \
    client_secret="meridian-ai-harness-client-secret-rotate-me" \
    admin_password="admin" rotation=3
# rotation 2 -> current_version 3, oldest_version 1

$ bao kv put -cas=3 ai/platform/oidc/keycloak ... rotation=4
# rotation 3 -> current_version 4, oldest_version 2

$ bao kv put -cas=4 ai/platform/oidc/keycloak ... rotation=5
# rotation 4 -> current_version 5, oldest_version 3

$ bao kv put -cas=5 ai/platform/oidc/keycloak ... rotation=6
# rotation 5 -> current_version 6, oldest_version 4
```

Watch the `oldest_version` climb as the window slides. Three are retained
(the cap you just set), three are pruned.

Five rotations, three retained:

```bash
$ bao kv metadata get ai/platform/oidc/keycloak
...
current_version             6
oldest_version              4
...
====== Version 4 ======
Key              Value
---              -----
created_time     2026-10-21T16:41:55.879091766Z
deletion_time    n/a
destroyed        false

====== Version 5 ======
...
====== Version 6 ======
...
```

Versions 1, 2 and 3 are gone. Not deleted — **pruned**. They are not
recoverable and they never had a deletion event in the audit log:

```bash
$ bao kv get -version=2 ai/platform/oidc/keycloak   (pruned away)
No value found at ai/platform/data/oidc/keycloak
exit=2
```

> **Production:** *Pick `max_versions` per secret class, not one number for
> the whole mount. A 10-version cap is generous for a credential that
> rotates quarterly and absurd for a credential that rotates every hour.
> And remember the interaction: a version pruned by `max_versions` is gone
> with no trace in the metadata — you cannot tell "never existed" from
> "pruned" after the fact. The audit log still knows, but only the audit
> log does.*

---

## 11. Soft delete, undelete, and destroy

Three different operations that people constantly confuse.

| Operation | Command | Data recoverable? | Metadata says |
|---|---|---|---|
| **Soft delete** | `bao kv delete -versions=N` | Yes, with `undelete` | `deletion_time` set, `destroyed: false` |
| **Undelete** | `bao kv undelete -versions=N` | It never went away | `deletion_time` cleared |
| **Destroy** | `bao kv destroy -versions=N` | **No. Ever.** | `destroyed: true` |

### 11.1 The flag is `-versions` (plural) — and `-version` (singular) fails

```bash
$ bao kv delete -version=1 ai/platform/cache/redis     <-- WRONG FLAG
flag provided but not defined: -version
exit=1

$ bao kv delete -versions=1 ai/platform/cache/redis    <-- RIGHT FLAG
Success! Data deleted (if it existed) at: ai/platform/data/cache/redis
exit=0
```

The CLI flag naming is genuinely inconsistent, and it is worth writing down:

| Command | Flag | Type |
|---|---|---|
| `bao kv get` | `-version=N` | singular, int |
| `bao kv rollback` | `-version=N` | singular, int |
| `bao kv put` | `-cas=N` | int |
| `bao kv delete` | `-versions=N` | **plural**, comma-separated list |
| `bao kv undelete` | `-versions=N` | **plural**, comma-separated list |
| `bao kv destroy` | `-versions=N` | **plural**, comma-separated list |

`delete`, `undelete` and `destroy` take a *list*, so you can nuke several
versions in one call: `-versions=1,2,3`.

### 11.2 Soft delete

```bash
$ bao kv get -version=1 ai/platform/cache/redis
======== Secret Path =========
ai/platform/data/cache/redis

======= Metadata =======
Key                Value
---                -----
created_time       2026-10-21T16:41:53.808834247Z
custom_metadata    <nil>
deletion_time      2026-10-21T16:41:54.248972695Z
destroyed          false
version            1
```

Look closely: there is **no `===== Data =====` section**. The secret values
are gone from the read, but the version still exists in the metadata, and
`destroyed` is still `false`. This is a soft delete.

### 11.3 Undelete

```bash
$ bao kv undelete -versions=1 ai/platform/cache/redis
Success! Data written to: ai/platform/undelete/cache/redis
exit=0

$ bao kv get -version=1 ai/platform/cache/redis
======== Secret Path =========
ai/platform/data/cache/redis

======= Metadata =======
Key                Value
---                -----
created_time       2026-10-21T16:41:53.808834247Z
custom_metadata    <nil>
deletion_time      n/a
destroyed          false
version            1

===== Data =====
Key         Value
---         -----
db          0
host        redis
password    Yb3mQ8vT1xW6rK4pL9zD2nF7gH5jA0sC4eU
port        6379
```

The password is back, byte for byte — and it is the *same* payload you wrote
in §4.2 (`host=redis`, `port=6379`, `db=0`, the Redis password), because
`undelete` restores the version that was soft-deleted, it does not invent a
new one. **This is why soft delete exists:** the single most common
secret-store incident is "somebody deleted the wrong thing", and here it is a
one-line undo.

### 11.4 Destroy

```bash
$ bao kv destroy -versions=1 ai/platform/cache/redis
Success! Data written to: ai/platform/destroy/cache/redis
exit=0

$ bao kv get -version=1 ai/platform/cache/redis
======== Secret Path =========
ai/platform/data/cache/redis

======= Metadata =======
Key                Value
---                -----
created_time       2026-10-21T16:41:53.808834247Z
custom_metadata    <nil>
deletion_time      n/a
destroyed          true
version            1
```

`destroyed: true`. The values are gone and there is no way back:

```bash
$ bao kv metadata get ai/platform/cache/redis
...
====== Version 1 ======
Key              Value
---              -----
created_time     2026-10-21T16:41:53.808834247Z
deletion_time    n/a
destroyed        true
```

The version entry remains as a tombstone — proof that a version existed,
without its content. And there is no `undestroy`:

```bash
$ bao kv undestroy -versions=1 ai/platform/cache/redis
Usage: bao kv <subcommand> [options] [args]
...
Subcommands:
    delete               Deletes versions in the KV store
    destroy              Permanently removes one or more versions in the KV store
    enable-versioning    Turns on versioning for a KV store
    get                  Retrieves data from the KV store
    list                 List data or secrets
    metadata             Interact with OpenBao's Key-Value storage
    patch                Sets or updates data in the KV store without overwriting
    put                  Sets or updates data in the KV store
    rollback             Rolls back to a previous version of data
    scan                 Scan data or secrets
    undelete             Undeletes versions in the KV store
exit=1
```

> **Trade-off:** *soft delete keeps your blast radius small but keeps the
> secret material alive in storage. Destroy is a real erasure — the right
> answer for a credential you are legally obliged to forget — but it is
> one-way and unrecoverable. Pick soft delete by default, destroy only
> with a reason.*

### 11.5 `metadata delete` — nuke the whole secret

`bao kv metadata delete <path>` removes **every version and all the
metadata** for a path. The secret then does not exist at all:

```bash
$ bao kv metadata delete ai/platform/cache/redis-session-key
Success! Data deleted (if it existed) at: ai/platform/metadata/cache/redis-session-key
exit=0

$ bao kv get ai/platform/cache/redis-session-key
No value found at ai/platform/data/cache/redis-session-key
exit=2

$ bao kv metadata get ai/platform/cache/redis-session-key
No value found at ai/platform/metadata/cache/redis-session-key
exit=2
```

And it disappears from the listing, because the listing is derived from the
metadata:

```bash
$ bao kv list ai/platform/cache
Keys
----
redis
```

---

## 12. `delete_version_after` — right to erasure

**What is `delete_version_after`?** A duration after which a version stops
being readable, enforced by the server at read time.

*Why it exists:* Meridian AI processes customer transcripts. A session
signing key that is valid forever is a liability; a key that expires in ten
minutes is not.

*What if you skipped it:* you would store credentials that outlive their
purpose, and you would have no way to prove to an auditor that they were
gone.

There are two scopes:

| Scope | How | Overrides |
|---|---|---|
| Mount | `bao write <mount>/config delete_version_after=168h` | applies to every secret under the mount |
| Per secret | `bao kv metadata put -delete-version-after=10s <path>` | applies to that secret only |

**The shorter duration wins.** If the mount says 168h and the secret says
10s, the secret expires in 10 seconds.

### 12.1 Watch it actually happen

```bash
$ bao kv metadata put -delete-version-after=10s \
    -custom-metadata="purpose=session-signing-key" ai/platform/cache/redis-session-key
Success! Data written to: ai/platform/metadata/cache/redis-session-key

$ bao kv put -cas=0 ai/platform/cache/redis-session-key \
    key="mrd_sess_8nD2kL5pR7yT4wC9hB3vX6zQ1sF0gJ8eU"
============== Secret Path ===============
ai/platform/data/cache/redis-session-key

======= Metadata =======
Key                Value
---                -----
created_time       2026-10-21T16:41:57.136769279Z
custom_metadata    map[purpose:session-signing-key]
deletion_time      2026-10-21T16:42:07.136769279Z
destroyed          false
version            1
```

`deletion_time 2026-10-21T16:42:07Z` — exactly ten seconds after
`created_time 16:41:57Z`. The deadline was computed at write time.

```bash
$ bao kv metadata get ai/platform/cache/redis-session-key
...
delete_version_after        10s
...
====== Version 1 ======
Key              Value
---              -----
created_time     2026-10-21T16:41:57.136769279Z
deletion_time    2026-10-21T16:42:07.136769279Z
destroyed        false
```

Now the moment of truth — T+0, then T+12:

```bash
$ curl -s -w '\nHTTP %{http_code}\n' -H "X-Vault-Token: $BAO_TOKEN" \
    "$BAO_ADDR/v1/ai/platform/data/cache/redis-session-key"
```

```bash
--- T+0: the secret is live ---
  GET /v1/ai/platform/data/cache/redis-session-key -> HTTP 200
{"data":{"data":{"key":"mrd_sess_8nD2kL5pR7yT4wC9hB3vX6zQ1sF0gJ8eU"},"metadata":{"created_time":"2026-10-21T16:41:57.136769279Z","custom_metadata":{"purpose":"session-signing-key"},"deletion_time":"2026-10-21T16:42:07.136769279Z","destroyed":false,"version":1}}}

--- T+12: the deadline has passed ---
  GET /v1/ai/platform/data/cache/redis-session-key -> HTTP 404
{"data":{"data":null,"metadata":{"created_time":"2026-10-21T16:41:57.136769279Z","custom_metadata":{"purpose":"session-signing-key"},"deletion_time":"2026-10-21T16:42:07.136769279Z","destroyed":false,"version":1}}}
```

**HTTP 200 with the value, then HTTP 404 with `data.data` set to `null`.**
That is `delete_version_after` actually taking effect. Read the 404 body
carefully: the *envelope* is unchanged and the metadata block is still
there — `deletion_time` is still reported, so you can still prove when it
expired. Only the payload is gone.

From the CLI the same thing looks like this — the metadata block is
returned, but there is no `===== Data =====` section:

```bash
$ bao kv get ai/platform/cache/redis-session-key
============== Secret Path ===============
ai/platform/data/cache/redis-session-key

======= Metadata =======
Key                Value
---                -----
created_time       2026-10-21T16:41:57.136769279Z
custom_metadata    map[purpose:session-signing-key]
deletion_time      2026-10-21T16:42:07.136769279Z
destroyed          false
version            1
```

### 12.2 What this does and does not do

This is the part most people get wrong, so let me be precise about what I
verified:

| Claim | Verified? |
|---|---|
| The secret stops being **readable** at the deadline | ✅ HTTP 200 → HTTP 404, measured above |
| The `deletion_time` is stamped on the version at write time | ✅ visible in `bao kv metadata get` |
| The version becomes **ineligible for rollback** | ✅ `Cannot roll back to a version that has been deleted` |
| The ciphertext is physically erased from storage at the deadline | ❌ **not verified, and I believe it is not what happens** |

The enforcement is at **read time**: OpenBao compares `deletion_time` to
now and returns 404. The underlying ciphertext is only removed when
`max_versions` prunes the version or somebody `destroy`s it.

> **Production:** *`delete_version_after` is a **logical** expiry, not a
> cryptographic erasure. If your compliance requirement is "the key material
> must be unrecoverable from the storage backend", `delete_version_after`
> does not satisfy it on its own — you need `destroy` (or a `max_versions`
> window short enough that the version is pruned soon after). If your
> requirement is "the secret must stop being usable at time T", then
> `delete_version_after` is exactly right, and it is enforced at every read,
> so a stale client cache cannot resurrect it.*

---

## 13. `max_versions` is not a lease TTL

This is the most common confusion in the whole engine, so let me put the
two side by side.

**What is a lease?** A time-limited grant attached to a *dynamic* secret —
a database credential, a certificate. OpenBao tracks it, renews it, and
revokes it when it expires. The client gets a credential that will
*stop working* on its own.

**What is `max_versions`?** A count. How many historical versions of a
static secret to keep. Nothing expires. Nothing is renewed. Nothing is
revoked.

| | `max_versions` | Lease TTL |
|---|---|---|
| What it measures | a **count** of retained versions | a **duration** of validity |
| Applies to | static secrets (KV v2) | dynamic secrets (database creds, PKI) |
| Effect when reached | oldest version is pruned | the credential stops working |
| Renewable? | No — it is a counter | Yes — `sys/leases/renew` |
| Revocable? | No — you delete the version | Yes — `sys/leases/revoke` |
| Where configured | `<mount>/config` or `<mount>/metadata/<path>` | `bao secrets tune`, or per-role |
| Can it expire a secret? | No | Yes |

### 13.1 The fingerprint in the API response

Remember the KV v1 read from section 5.2? Look at its lease fields again:

```bash
$ bao read -format=json ai/scratch/llm/gemini | jq '{lease_id, lease_duration, renewable}'
{
  "lease_id": "",
  "lease_duration": 2764800,
  "renewable": false
}
```

versus a KV v2 secret:

```bash
$ bao read -format=json ai/platform/data/llm/gemini | jq '{lease_id, lease_duration, renewable}'
{
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false
}
```

**KV v2 secrets have `lease_duration: 0`.** A KV v1 secret inherits the
mount's default lease TTL (2764800 seconds = 32 days) because the v1 engine
routes reads through the generic lease machinery. In v2 that machinery is
bypassed entirely: a KV v2 secret is a **static** secret. It does not
expire. It is valid until you rotate it, delete it, or destroy it.

And tuning the lease TTL on a KV v2 mount changes nothing about its data:

```bash
$ bao secrets tune -default-lease-ttl=1h -max-lease-ttl=24h ai/platform
Success! Tuned the secrets engine at: ai/platform/

$ bao read -format=json ai/platform/data/llm/gemini | jq '{lease_id, lease_duration, renewable}'
{
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false
}
```

Unchanged. There is no lease to shorten.

> **Production:** *Do not reach for a lease TTL to "expire" a KV v2 secret.
> It does nothing. Use `delete_version_after` for an expiry, `max_versions`
> to bound history, and the **token** TTL (Module 04) to bound how long a
> *caller* may read the secret. Those are three different lifetimes and
> confusing them is how you end up with a secret that "expired" three weeks
> ago and is still readable.*

---

## 14. Listing leaks names

**What is `list`?** An operation that returns the names of the secrets
under a path. Not their values — their **names**.

*Why it exists:* so a human (or a service) can discover what is stored
where, without reading anything.

*What if you skipped it:* discovery becomes impossible. But that is not the
risk — the risk is the opposite, and it is the thing to watch.

```bash
$ bao kv list ai/platform
Keys
----
cache/
db/
llm/
oidc/

$ bao kv list ai/platform/llm
Keys
----
gemini

$ bao kv scan -format=json ai/platform | jq
[
  "oidc/keycloak",
  "llm/gemini",
  "db/postgres",
  "cache/redis",
  "cache/redis-session-key"
]
```

`gemini` is the **name of the secret that holds the Gemini API key**. Anyone
who can `list` on `ai/platform/llm` learns that Meridian AI has a Gemini
credential, that it lives at a known path, and therefore exactly where to
aim — even if they cannot read a single byte of it.

That is why `list` is a **separate capability** from `read` in OpenBao's
ACL model, and why Module 03 will give the `data-pipeline` service read
access to `ai/platform/db/postgres` **without** list access to
`ai/platform/`.

### 14.1 Listing is not free, and it is not the same on v1 and v2

For KV v2, the list operation happens on the **metadata** path, not the data
path. Doing it the wrong way returns a warning instead of keys:

```bash
$ curl -s -X LIST -H "X-Vault-Token: $BAO_TOKEN" $BAO_ADDR/v1/ai/platform/metadata/llm/ | jq -c '.data'
{"keys":["gemini"]}

$ curl -s -X LIST -H "X-Vault-Token: $BAO_TOKEN" $BAO_ADDR/v1/ai/platform/ | jq -c '.warnings'
["Invalid path for a versioned K/V secrets engine. See the API docs for the appropriate API endpoints to use. If using the OpenBao CLI, use 'bao kv list' for this operation."]
```

Note the `X-Vault-Token` header. Without it the API answers
`{"errors":["permission denied"]}` and tells you nothing about paths —
which is the correct behaviour, and a reminder that the raw HTTP API has
no implicit session.

And note what the audit log recorded for that list — even the key names
are HMAC'd, because `log_raw = false`:

```bash
$ grep '"operation":"list"' logs/audit.log \
    | jq -c 'select(.type=="response" and .request.path=="ai/platform/metadata/") | .response.data.keys' \
    | grep -v null | tail -1
["hmac-sha256:5115bd6b15e0a486d1a9f93b795e438deceeb7a496272080930131ce89e097d3","hmac-sha256:1c1dedf5476fc1343602055920cf5869f7b57a7d2192e4605b4bfbc1d4fb9a4c","hmac-sha256:06409c028a113bbfde42c495f2e45d4f2217db68e50f7fc4edf0929f1a1f3d7e","hmac-sha256:a9118edc2fd2b231fd6092ecd2d00dde10ae353cea39a1e39c4fe1cc1d55bfb3"]
```

The audit log does not leak your secret inventory. **The API response to an
authorised `list` call does** — that is the difference.

> **Production:** *Treat `list` as a privileged operation. Grant it to
> humans and to the platform-admin service. Do **not** grant it to
> application services: `ai-harness` knows the exact path of the secret it
> needs; it has no reason to enumerate the store. Module 03 turns this into
> an explicit policy stanza.*

### 14.2 `bao kv scan` versus `bao kv list`

`list` is one level. `scan` is recursive and returns every path under the
prefix. Use `scan` for audits and inventories; never wire it into an
application.

```bash
$ bao kv scan -format=json ai/platform | jq
[
  "oidc/keycloak",
  "llm/gemini",
  "db/postgres",
  "cache/redis",
  "cache/redis-session-key"
]
```

---

## 15. The GUI for this module

Open <http://127.0.0.1:8200/ui> (or whatever port your lab server is on) and
log in with your root token.

**The path in the GUI is the same path in the CLI.** Click
**Secrets engines** in the left-hand navigation → `ai/platform/` → `llm/` →
`gemini`.

> **What I verified about the GUI, and what I did not.** The OpenBao web UI
> is a browser application, so I could not click through it in this
> environment. What I *did* verify: the UI is served and returns
> `HTTP 200`; the server exposes a mount-information endpoint that the UI
> reads to decide how to render an engine; and the shipped UI bundle
> contains the KV v2 page components — including the version-history route
> and the per-version delete / undelete / destroy actions. The menu paths
> below are the standard OpenBao KV v2 pages; every API call they make is
> listed and verified in section 14.1.
>
> **One correction worth reading.** The left-hand nav section is
> **`Secrets engines`**, not `Secrets` — and `Enable new engine` (not
> "Enable secrets engine") is the button that mounts a new engine. I
> pulled the nav templates out of the UI's own JavaScript bundle to
> confirm it:
>
> ```bash
> $ curl -s http://127.0.0.1:8200/ui/ \
>     | grep -oE 'assets/[a-zA-Z0-9._-]+\.js' | sort -u
> $ for f in $(curl -s http://127.0.0.1:8200/ui/ \
>       | grep -oE 'assets/[a-zA-Z0-9._-]+\.js' | sort -u); do
>     curl -s "http://127.0.0.1:8200/ui/$f" -o "$(basename $f)"
>   done
> $ cat *.js > all.js
> $ grep -o '"vault.cluster.secrets[^"]*","[^"]*"' all.js | sort -u
> "vault.cluster.secrets","vault.cluster.secrets vault.cluster.settings.mount-secret-backend vault.cluster.settings.configure-secret-backend"
> "vault.cluster.secrets.backend","policy-show"
> "vault.cluster.secrets.backend","secrets-cert"
> "vault.cluster.secrets.backend.","credentials"
> "vault.cluster.secrets.backend.create-root","connection"
> "vault.cluster.secrets.backend.create-root","role"
> "vault.cluster.secrets.backend.list","show"
> "vault.cluster.secrets.backend.show","show"
> ```
>
> That grep shows the *routes*, not the label — which is exactly why it is
> the wrong tool for this job. The route array is a three-element list
> ("current route, plus the sibling routes that should also light up the nav
> item"), and the human-readable label lives in a **different array**, in
> the nav template. Grep for the label itself:
>
> ```bash
> $ grep -oE '.{0,60}"Secrets engines".{0,60}' all.js
> et-backend vault.cluster.settings.configure-secret-backend","Secrets engines"]],null],[1,"\\n"],[41,[28,[37,2],["access"],null],[[[1,"
> ```
>
> The label is right there — `"Secrets engines"` — sitting at the end of the
> route array's sibling list, followed by the `access` nav item. That is the
> nav item you click.

```bash
$ curl -s -o /dev/null -w 'GET /ui/  -> HTTP %{http_code}\n' "$BAO_ADDR/ui/"
GET /ui/  -> HTTP 200

$ bao read sys/internal/ui/mounts/ai/platform -format=json | jq '{path: .data.path, type: .data.type, options: .data.options, accessor: .data.accessor}'
{
  "path": "ai/platform/",
  "type": "kv",
  "options": {
    "version": "2"
  },
  "accessor": "kv_267fde5b"
}
```

Note that even the UI's own mount information carries `options.version` —
the one field that tells the truth about v1 versus v2.

| GUI | CLI equivalent |
|---|---|
| Secrets engines → `ai/platform` → `llm` → `gemini` | `bao kv get ai/platform/llm/gemini` |
| The **Data** view (key/value rows) | `bao kv get -format=json ... \| jq .data.data` |
| The **Metadata** view (`max_versions`, `delete_version_after`, `cas_required`, custom metadata) | `bao kv metadata get ai/platform/llm/gemini` |
| The **History** view (the list of versions) | `bao kv metadata get ai/platform/llm/gemini` (the per-version blocks) |
| **Create new version** | `bao kv put ...` |
| **Enable new engine** (the mount button) | `bao secrets enable -path=ai/platform kv-v2` |
| The `…` menu → **Delete** (soft) | `bao kv delete -versions=N ...` |
| The `…` menu → **Undelete** (after a soft delete) | `bao kv undelete -versions=N ...` |
| The `…` menu → **Destroy** (permanent) | `bao kv destroy -versions=N ...` |
| Browse a folder (the `cache/`, `db/`, `llm/` list) | `bao kv list ai/platform` |
| Engines → `ai/platform` → **Configuration** | `bao read ai/platform/config` |

> **Where these labels come from.** *The three version-menu labels are the
> literal button texts in the shipped UI bundle's `secret-delete-menu`
> component: **`Undelete`**, **`Delete`** and **`Destroy`**. The same
> component opens a modal whose text begins "There are three ways to delete
> or destroy the …" and explains "This deletes Version … of the secret. It
> can be un-deleted later." — that modal is where the soft-delete /
> destroy / delete-all distinction actually lives.*
>
> Note what is **not** there: there is no "Roll back to this version" and no
> "Show version data" button in the 2.7.1 UI. Rollback is CLI-only, which
> is one more reason the CLI stays primary.

### 15.1 What the GUI does *not* expose

This is why the CLI stays primary in this course.

| Not in the GUI | Why you need the CLI |
|---|---|
| **Check-and-set on a write** | The shipped UI bundle contains no `options.cas` value on the KV v2 write path. A write from the browser can therefore **silently clobber** a concurrent write from the rotation bot. Use the CLI for anything automated. |
| **`metadata_cas`** | No field for it anywhere. The metadata CAS value can only be set with a raw `bao write` of JSON. |
| **Bulk version operations** | `delete -versions=1,2,3` in one call; the GUI is one version at a time. |
| **Raw JSON output** | The whole point of `-format=json` for piping into jq, or into an application. |
| **Scanning a whole prefix** | No recursive scan in the GUI. `bao kv scan` is CLI-only. |
| **The `sys/mounts` options diff** | The GUI's engine list shows `Type: kv` for both v1 and v2 — exactly the trap from section 3.2. Only the CLI shows you the truth. |

> **Production:** *The GUI is for *humans doing one-off work*: reading a
> secret during an incident, attaching an owner label, checking a version
> history. The CLI is for *everything a machine does*: rotations, the
> deployment pipeline, the rotation bot. Never put a credential into the GUI
> browser session and then close the tab thinking it is gone — the browser
> keeps it, and it may end up in a session store.*

---

## 16. The full lifecycle lab

Everything below is one continuous, runnable sequence. It is the "put it all
together" exercise — run it top to bottom on a fresh mount and you will
have exercised every behaviour in this module.

### 16.1 Set up

This lab is self-contained: it starts from a **clean mount** so that every
`-cas=0` below genuinely means "create, and fail if it already exists".

```bash
# 0. Start from a clean slate. If you followed sections 3-15, ai/platform/
#    already exists - and `secrets enable` on an existing path is an error.
bao secrets disable ai/platform 2>/dev/null || true

# 1. The mount
bao secrets enable -path=ai/platform kv-v2

# 2. Prove it is v2 before you build anything on it
bao read sys/mounts/ai/platform -format=json | jq '.data.options'
# -> { "version": "2" }

# 3. The configuration, at the RIGHT endpoint
bao write ai/platform/config \
    cas_required=true \
    max_versions=10 \
    delete_version_after=0s \
    metadata_cas_required=true

# 4. Read it back. Always.
bao read ai/platform/config
```

```
Key                      Value
---                      -----
cas_required             true
delete_version_after     0s
max_versions             10
metadata_cas_required    true
```

> **What `metadata_cas_required=true` costs you.** It is the right
> production setting — it protects the ownership labels from the same
> lost-update race as the secret itself. But it also means the ergonomic
> `bao kv metadata put -custom-metadata=...` form **stops working**, because
> that subcommand has no way to send a `metadata_cas` value. You have to use
> the raw-JSON form shown in section 16.3.
>
> **Trade-off:** *I would still turn it on. A lost owner label is a smaller
> incident than a lost secret, but it is the same class of bug, and the
> cost of the fix is one shell function that reads the current metadata
> version and pipes JSON. Put that function in your platform tooling once
> and nobody has to think about it again.*

### 16.2 Seed the four Meridian AI secrets

```bash
bao kv put -cas=0 ai/platform/llm/gemini \
    api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" \
    model="gemini-2.0-flash" \
    project_id="meridian-ai-prod-01"

bao kv put -cas=0 ai/platform/db/postgres \
    host="postgres" port=5432 dbname="meridian_ai" \
    username="meridian_app" password="Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK" \
    sslmode=require

bao kv put -cas=0 ai/platform/cache/redis \
    host="redis" port=6379 \
    password="Yb3mQ8vT1xW6rK4pL9zD2nF7gH5jA0sC4eU" db=0

bao kv put -cas=0 ai/platform/oidc/keycloak \
    issuer="http://keycloak:8080/realms/meridian-ai" \
    client_id="ai-harness" \
    client_secret="meridian-ai-harness-client-secret-rotate-me" \
    admin_password="admin"
```

`bao kv put -cas=0` works here because step 0 wiped the mount, so none of
these exist yet. It is the safe "create, but fail if it already exists"
form — which is exactly what you want in a seeding script, because a
mistyped path fails loudly instead of quietly overwriting a live secret.

> **Note the hosts.** `postgres`, `redis` and `keycloak` are the Docker
> service names from `lab/docker-compose.yml`. In production these become
> resolvable names like `meridian-db.internal` — and that is exactly the
> kind of value you would change with a staged rotation, which is what the
> rest of this lab does.

### 16.3 Attach ownership metadata

Because `metadata_cas_required=true`, the friendly form is blocked:

```bash
$ bao kv metadata put -custom-metadata="owner=platform-team" ai/platform/llm/gemini
Error writing data to ai/platform/metadata/llm/gemini: Error making API request.

URL: PUT http://127.0.0.1:9185/v1/ai/platform/metadata/llm/gemini
Code: 400. Errors:

* metadata check-and-set parameter required for this call
exit=2
```

So you use the raw form, and you need the secret's **current metadata
version** — not its current data version:

```bash
# one helper, reused for every secret
metacas() {
  bao kv metadata get -format=json "$1" 2>/dev/null | jq -r '.data.current_metadata_version // 0'
}

$ echo '{"metadata_cas":0,"custom_metadata":{"owner":"platform-team","rotation":"90d","ticket":"MER-1841"}}' \
    | bao write ai/platform/metadata/llm/gemini -
Success! Data written to: ai/platform/metadata/llm/gemini

$ echo '{"metadata_cas":0,"custom_metadata":{"owner":"data-team","rotation":"60d"}}' \
    | bao write ai/platform/metadata/db/postgres -
Success! Data written to: ai/platform/metadata/db/postgres

$ echo '{"metadata_cas":0,"custom_metadata":{"owner":"platform-team","rotation":"30d"}}' \
    | bao write ai/platform/metadata/cache/redis -
Success! Data written to: ai/platform/metadata/cache/redis

$ echo '{"metadata_cas":0,"custom_metadata":{"owner":"platform-team","rotation":"90d"}}' \
    | bao write ai/platform/metadata/oidc/keycloak -
Success! Data written to: ai/platform/metadata/oidc/keycloak
```

> **`metadata_cas=0` is only valid for the very first metadata write on a
> secret.** It asserts "this secret has no metadata yet". On a secret that
> already has metadata, `0` is a stale value and you get:
>
> ```
> * metadata check-and-set parameter does not match the current version
> ```
>
> Which is exactly the same class of error as a stale data CAS. On a fresh
> mount all four secrets report `current_metadata_version` of `0`, so all
> four writes above use `0`. Run any one of them a second time and it
> fails — that is the metadata CAS doing its job.

### 16.4 Rotate the Gemini key, safely

```bash
# read the current version
v=$(bao kv metadata get -format=json ai/platform/llm/gemini | jq -r '.data.current_version')

# write against it
bao kv put -cas="$v" ai/platform/llm/gemini \
    api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" \
    model="gemini-2.0-flash" \
    project_id="meridian-ai-prod-01"
```

If the rotation bot wrote in between, this fails loudly with
`check-and-set parameter did not match the current version` — and nothing
is lost.

### 16.5 Make a mistake, then roll it back

```bash
# the bad write
bao kv put -cas=<current> ai/platform/llm/gemini \
    api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" \
    model="gemini-1.0-pro" \
    project_id="meridian-ai-prod-01"

# roll back to the good version
bao kv rollback -version=<good> ai/platform/llm/gemini

# the bad write is still there, and that is correct
bao kv get -version=<bad> ai/platform/llm/gemini
```

### 16.6 Delete, undo, and destroy

```bash
# soft delete the previous version
bao kv delete -versions=1 ai/platform/cache/redis

# change your mind
bao kv undelete -versions=1 ai/platform/cache/redis

# this time you mean it
bao kv destroy -versions=1 ai/platform/cache/redis
```

### 16.7 Set an expiry on the throwaway secret

```bash
# metadata_cas_required is on, so the friendly form is blocked here too
echo '{"metadata_cas":0,"delete_version_after":"1h","custom_metadata":{"purpose":"session-signing-key"}}' \
    | bao write ai/platform/metadata/cache/redis-session-key -
Success! Data written to: ai/platform/metadata/cache/redis-session-key

bao kv put -cas=0 ai/platform/cache/redis-session-key \
    key="mrd_sess_8nD2kL5pR7yT4wC9hB3vX6zQ1sF0gJ8eU"
```

### 16.8 Inventory, without reading a single value

```bash
bao kv list ai/platform
bao kv scan -format=json ai/platform | jq
bao kv metadata get ai/platform/llm/gemini
```

### 16.9 The final state

```bash
$ bao read ai/platform/config
Key                      Value
---                      -----
cas_required             true
delete_version_after     0s
max_versions             10
metadata_cas_required    true

$ bao kv list ai/platform
Keys
----
cache/
db/
llm/
oidc/

$ bao kv scan -format=json ai/platform | jq
[
  "oidc/keycloak",
  "llm/gemini",
  "db/postgres",
  "cache/redis",
  "cache/redis-session-key"
]

$ bao kv get ai/platform/llm/gemini
======= Secret Path =======
ai/platform/data/llm/gemini

======= Metadata =======
Key                Value
---                -----
created_time       2026-10-21T16:42:20.311971506Z
custom_metadata    map[owner:platform-team rotation:90d ticket:MER-1841]
deletion_time      n/a
destroyed          false
version            4

===== Data =====
Key           Value
---           -----
api_key       AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr
model         gemini-2.0-flash
project_id    meridian-ai-prod-01
```

And the metadata view of the same secret — note the two version counters
sitting side by side:

```bash
$ bao kv metadata get ai/platform/llm/gemini
...
current_metadata_version    1
current_version             4
custom_metadata             map[owner:platform-team rotation:90d ticket:MER-1841]
...
```

`current_version 4` is four data writes: the seed in 16.2, the rotation in
16.4, the bad write in 16.5, and the rollback in 16.5. The rollback
*appended*, it did not rewind. `current_metadata_version 1` is the single
metadata write from 16.3. Two counters, two histories, one secret.

### 16.10 `bao kv patch` — one more tool you will want

`put` replaces the whole payload. `patch` merges:

```bash
# version 1 was destroyed in 16.6, so the secret has to be re-created first
bao kv put -cas=1 ai/platform/cache/redis \
    host="meridian-cache.internal" port=6379 username="meridian_app" \
    password="Yb3mQ8vT1xW6rK4pL9zD2nF7gH5jA0sC4eU"

$ bao kv patch -cas=2 ai/platform/cache/redis tls=false pool_size=32
======== Secret Path ========
ai/platform/data/cache/redis

======= Metadata =======
Key                Value
---                -----
created_time       2026-10-21T16:42:26.928411299Z
custom_metadata    map[owner:platform-team rotation:30d]
deletion_time      n/a
destroyed          false
version            3

$ bao kv get ai/platform/cache/redis
======== Secret Path ========
ai/platform/data/cache/redis

======= Metadata =======
Key                Value
---                -----
created_time       2026-10-21T16:42:26.928411299Z
custom_metadata    map[owner:platform-team rotation:30d]
deletion_time      n/a
destroyed          false
version            3

====== Data ======
Key          Value
---          -----
host         meridian-cache.internal
password     Yb3mQ8vT1xW6rK4pL9zD2nF7gH5jA0sC4eU
pool_size    32
port         6379
tls          false
username     meridian_app
```

`tls` was updated, `pool_size` was added, and `host`, `password`, `port`
and `username` were left alone. With `put`, a single missing key would
have wiped the rest of the secret.

> **Production:** *Use `patch` for additive changes and `put` for
> declarative "this is the complete value" writes. A `put` that omits a key
> **deletes** that key from the new version — which is exactly how a
> rotation script that forgets one field silently removes it.*

---

## 17. What you learned

- [ ] `kv` is KV **v1**; `kv-v2` is v2. The only reliable way to tell is
      `bao read sys/mounts/<path> -format=json | jq .data.options` →
      `{"version":"2"}`. `bao secrets list` shows `kv` for both.
- [ ] `bao kv enable-versioning <mount>` upgrades a v1 mount in place, no
      downtime, no data migration.
- [ ] A KV v2 secret lives at `<mount>/data/<path>`; its metadata at
      `<mount>/metadata/<path>`.
- [ ] In JSON output the secret is at `.data.data.<key>` and the metadata
      at `.data.metadata`. Two `.data` levels.
- [ ] KV v2 configuration lives at `<mount>/config`.
      `sys/mounts/<path>/tune` accepts `cas_required` and `max_versions`,
      reports `Success!`, and **does nothing**.
- [ ] With `cas_required=true`, every write needs `-cas=N`, including the
      first. A missing value gives
      `check-and-set parameter required for this call`; a stale one gives
      `check-and-set parameter did not match the current version`. Both are
      HTTP 400.
- [ ] `-cas=0` asserts "this secret does not exist yet".
- [ ] Metadata has its own CAS (`metadata_cas`), its own error messages
      (`metadata check-and-set parameter required for this call`), and its
      own version counter (`current_metadata_version`). `metadata_cas=0` is
      only valid for a secret's *first* metadata write.
- [ ] A mount-level `cas_required=true` **mandates** CAS; a per-secret
      `cas_required=false` is ignored, with a warning.
- [ ] Every write creates a new version. Versions are immutable.
- [ ] **Rollback appends.** It creates a *new* version with the old
      content and leaves the bad version in place. The audit trail stays
      honest.
- [ ] A version carrying a `deletion_time` cannot be rolled back to:
      `Cannot roll back to a version that has been deleted`. A destroyed
      version: `Cannot roll back to a version that has been destroyed`.
- [ ] `delete_version_after` and mount-wide rollback are mutually
      exclusive. Set the expiry per secret, not per mount.
- [ ] `max_versions` prunes the oldest versions automatically, with no
      deletion event recorded.
- [ ] `delete_version_after` is enforced **at read time** — HTTP 200
      before the deadline, HTTP 404 after. It is a logical expiry, not a
      cryptographic erasure.
- [ ] `delete` is soft and reversible with `undelete`; `destroy` is
      permanent and has no `undestroy`; `metadata delete` removes the
      secret entirely.
- [ ] The delete flag is `-versions` (plural, a list); `get` and
      `rollback` use `-version` (singular, an int).
- [ ] `max_versions` is a **count**; a lease TTL is a **duration**. KV v2
      secrets have `lease_duration: 0` — they are static and do not expire.
      Tune the lease TTL and nothing about a KV v2 secret changes.
- [ ] `list` and `scan` reveal secret **names**. Treat list as a
      privileged capability.
- [ ] `bao kv patch` merges; `bao kv put` replaces.

---

## 18. What's next

The Gemini key is in OpenBao — but right now **any token can read it**,
because the root token can do everything and there are no other tokens yet.
Module 03 fixes that: policies, the allow-list model, the read/write
separation pattern, and the five Meridian AI policies that let
`ai-harness` read `ai/platform/llm/gemini` without being able to read
`ai/platform/db/postgres` or list the store.

---

## 19. Homework

Do these on your own lab server. Each one has a check you can run.

**1. Prove your mount is v2 — and prove the trap.**
Enable `ai/scratch` with `kv` and `ai/platform` with `kv-v2`. Show that
`bao secrets list` reports `kv` for both, and that
`bao read sys/mounts -format=json | jq` shows `options={"version":"2"}`
for one and `options=null` for the other. Then run `bao kv metadata get`
against the v1 mount and record the exact error.

**2. Demonstrate the silent no-op, and reproduce both CAS errors.**
On a fresh v2 mount, run
`bao write sys/mounts/<mount>/tune cas_required=true max_versions=10`,
then `bao read <mount>/config`. Record both outputs. Then do the same via
`bao write <mount>/config ...` and read it back again. In your notes,
answer: *what would have happened in production if you had only run the
first command and trusted the "Success!"?*

Then, with `cas_required=true` on the mount, produce the exact output of
(a) a write with no `-cas`, and (b) a write with a stale `-cas`. Then
produce a successful write using the value from `bao kv metadata get`.
Include all three outputs verbatim.

**3. Build a version history, roll it back, and find the rollback trap.**
Write three versions of `ai/platform/llm/gemini` where the third has a
different `model`. Roll back to the second. Show that the current version
number went *up*, and that the bad version is still readable with
`-version=3`.

Then set `delete_version_after=168h` on the mount, write a new version, and
try to roll back to it. Record the error. Then set `delete_version_after=0s`
and try again — the error should persist. Write down in one sentence why
that is the correct behaviour and what it means for your retention policy.

**4. Make a secret expire in front of your own eyes.**
Use `bao kv metadata put -delete-version-after=15s` on a throwaway path,
write a value, read it (should be HTTP 200 via `curl`), wait 20 seconds,
read it again (should be HTTP 404). Paste both `curl -w '%{http_code}'`
outputs. Then answer: *is the ciphertext physically gone from storage at
that moment, or only unreachable? How would you find out?*

**5. Build a metadata scheme for all four secrets, and scope CAS to one.**
Give `llm/gemini`, `db/postgres`, `cache/redis` and `oidc/keycloak` each a
consistent set of custom metadata (`owner`, `rotation`, `ticket`). Then
use `bao kv metadata patch -remove-custom-metadata=...` to remove one key
from one secret and confirm the others are untouched.

Finally, enable `cas_required` on **one** secret only (not the mount) and
show that a write to *it* without `-cas` fails, while a write to a
*different* secret without `-cas` still succeeds. Record the exact error
text for the first.

---

> **Up next:** [Module 03 — Policies & ACLs: Least Privilege](../03-policies/README.md)
> · **Previous:** [Module 01 — Foundations](../01-foundations/README.md)
