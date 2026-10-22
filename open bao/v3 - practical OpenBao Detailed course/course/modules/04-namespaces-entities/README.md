# Module 04 — Namespaces, Entities, Groups & Leases

> **Where we are.** Module 03 gave us policies: named rules that say what a
> token may do. That answers *what*, but not *where*, not *who*, and not
> *for how long*. Meridian AI is about to onboard its first two paying
> customers into the same OpenBao instance — a customer tenant and Meridian
> AI's own platform, side by side, with a hard boundary between them — and
> the platform team needs a way to hand `aisha.rahman` a credential that
> expires on its own and dies instantly when something goes wrong.
>
> This module completes the mental model: **namespaces** decide *where*,
> **entities and groups** decide *who*, **leases** decide *how long*.

**Status:** fully written and verified against **OpenBao v2.7.1**
(`openbao/openbao:2.7.1`, commit `a5db72cef75c24b920ade02065b18dd8eb666bac`).
Every command output in this module was captured from a live server.

> **A note on ports and paths.** The transcripts below were captured on a
> lab instance listening on `127.0.0.1:9373` with the `BAO_TOKEN` exported
> in the shell. Your lab uses the standard `http://127.0.0.1:8200`. The
> port appears in the error blocks because it is part of the real error
> text — everything else is identical.

---

## 0. The 60-second version

| Concept | One line |
|---|---|
| **Namespace** | An isolated subtree of OpenBao with its own mounts, policies, auth methods and `sys/`. It is the multi-tenancy boundary. |
| **`-namespace=`** | The flag that puts you *inside* a namespace. It is not a path prefix — it changes which server tree you are talking to. |
| **What a namespace isolates** | Mounts, policies, auth methods, tokens, identity store, audit view. What it does **not** isolate: the seal state of the whole server, the storage backend, the cluster. |
| **Entity** | The canonical identity record (`identity/entity`). It outlives every token, and every auth method that logs the same person in points at it. |
| **Alias** | The pointer from an auth method (OIDC, userpass, AppRole…) to an entity. One entity, many aliases. |
| **Group** | A named set of entities. Policies attach to groups, so onboarding and offboarding is one membership change, not twelve policy edits. |
| **Lease** | OpenBao's record of a time-bound credential: an ID, a TTL, and a maximum TTL, plus the ability to renew or revoke it. |
| **TTL** | How long the credential is valid *right now*. |
| **max_ttl** | The ceiling. A credential can be renewed repeatedly but never past this. |
| **Expiry** | TTL hits zero, OpenBao revokes the credential automatically. Nobody has to remember. |
| **Revocation** | You kill it early — either one lease or every lease under a prefix. |
| **Dynamic secret** | A credential OpenBao generates on request (DB user, PKI cert) — and tracks as a lease *when the engine is configured to*. |
| **Token** | Not a lease. A token's TTL lives in the token store; a dynamic secret's TTL lives in the expiration manager. |
| **`auth.lease_duration`** | Where a *token's* TTL is reported. |
| **top-level `lease_id`** | Where a *dynamic secret's* lease is reported. A plain token's is `""`. |
| **2.7 breaking change** | `sys/renew`, `sys/revoke`, `sys/revoke-prefix`, `sys/revoke-force` are **gone (404)**. Use `sys/leases/*`. CVE-2026-45808. |

---

## 1. Why this matters

Picture the week before Meridian AI signs its second customer.

Three separate problems are about to land in your lap at once, and they
look like one problem: *"who is allowed to see what, and for how long?"*

**Problem 1 — the blast radius.** Meridian AI's Gemini key, the Postgres
password and the Keycloak client secret all live in one OpenBao. The
customer's own API key needs to live there too. If everything is in the
root namespace, then every policy, every token and every operator with
`sudo` on `sys/` can reach every customer's data. When the customer asks
"what is your tenant isolation story?" — which they *will* ask before
signing, and which a security reviewer *will* ask — "we used paths and
policies" is not an answer. It is an intention.

**Problem 2 — the identity sprawl.** `aisha.rahman` will authenticate
through OIDC tomorrow. The CI pipeline authenticates with AppRole. The
break-glass script uses a userpass account. If each of those creates its
own disconnected identity, then "revoke Dev Kapoor's access" means
hunting down three unrelated records, and the audit log tells you who
holds a token but not *which human* it belonged to.

**Problem 3 — the credentials that never die.** A token with a 24-hour TTL
that nobody revokes is a permanent credential wearing a costume. In
February you will discover a leaked `secret_id` in a CI log, and you need
one command that kills every credential for that one service — not a
script that greps a log file.

Namespaces, entities/groups and leases are the three answers. They are
also the three answers in the order you should learn them, because each
one builds on the last.

---

## 2. Namespaces — the multi-tenancy layer

### 2.1 The concept in one plain sentence

A namespace is a **second OpenBao, living inside the first one**, with
its own secret paths, its own policies, and its own identity store.

### 2.2 Why it exists

Because paths and policies alone cannot give you a *hard* boundary.
A path is a string. A policy is a set of rules. Both are enforced by the
same engine, in the same process, with the same root token able to reach
everything. A namespace is enforced at the *routing* layer: the request
carries a namespace, the namespace selects a different set of mounts and
policies, and the path `ai/platform/llm/gemini` in namespace A is
genuinely not the path `ai/platform/llm/gemini` in namespace B.

### 2.3 What a namespace actually isolates

This is the table worth memorising, because people assume namespaces
isolate *secrets* and miss everything else.

| Thing | Isolated per namespace? | Evidence below |
|---|---|---|
| Secret engine mounts | ✅ yes — each namespace mounts its own | `bao secrets list` differs |
| ACL policies | ✅ yes | `bao policy list` shows only `default` inside |
| Auth methods | ✅ yes | root has `userpass/`, the namespace does not |
| Tokens | ✅ yes | token IDs are namespace-scoped |
| Identity store (entities, groups, aliases) | ✅ yes | `ns_identity` mount |
| Cubbyhole (per-token private storage) | ✅ yes | `ns_cubbyhole` mount |
| `sys/` endpoints (leases, policies, mounts) | ✅ yes | `ns_system` mount |
| The physical data (storage backend) | ❌ no — one database, one set of files | |
| The seal state of the server | ❌ no — sealing the server seals every namespace | |
| The cluster / HA topology | ❌ no | |
| The **root** namespace's own secrets | ❌ no — a root-namespace token cannot see *into* a child namespace by default, but a child namespace cannot see *out* either | |

> **Production:** *In OpenBao, a namespace is a routing and policy
> boundary, not a cryptographic one. The data for all namespaces lives
> behind the same barrier and is unsealed by the same Shamir quorum. If
> your threat model is "we must be able to prove we cannot read tenant
> data even with root", a namespace is not enough — you need a separate
> OpenBao cluster, or a separate seal for that namespace (see 2.8).*

### 2.4 Do it — create a namespace

```bash
$ bao namespace create tenant-atlas
Key                Value
---                -----
custom_metadata    map[]
id                 aNxERD
locked             false
path               tenant-atlas/
tainted            false
uuid               6597a595-f43a-c28f-b150-06b2c2854739
```

Read the output field by field, because three of these matter later:

- `path` — the namespace's path in the tree. It is always shown with a
  trailing `/`. This is the string you pass to `-namespace=`.
- `id` — a short, human-typeable namespace ID (`aNxERD`). This is *not*
  the UUID; it is the ID used in policy stanzas.
- `uuid` — the stable internal identifier. This is the one that appears in
  audit logs and in the identity store (`namespace_id`).
- `tainted` — set when the namespace's data has been restored from a
  backup taken while it was sealed. A tainted namespace refuses to serve
  secrets until it is re-sealed. You have not seen this happen; know that
  it exists.
- `locked` — see 2.7.

List what you have:

```bash
$ bao namespace list
Keys
----
tenant-alpha/
tenant-atlas/
tenant-secure/
```

> `bao namespace scan` does the same thing *recursively* — it lists
> namespaces nested inside namespaces. Use it when you have a hierarchy
> and you have lost track of it.

### 2.5 Do it — mount an engine *inside* the namespace

```bash
$ bao secrets enable -namespace=tenant-atlas -path=ai/platform kv-v2
Success! Enabled the kv-v2 secrets engine at: ai/platform/
```

Notice what is *not* in the output: the mount exists at
`tenant-atlas/ai/platform/`, and the root namespace has never heard of
it.

Now the two listings, side by side. This is the whole isolation story in
two commands:

```bash
$ bao secrets list -namespace=tenant-atlas
Path            Type            Accessor              Description
----            ----            --------              -----------
ai/platform/    kv              kv_74e05c8a           n/a
cubbyhole/    ns_cubbyhole    cubbyhole_1f4aa8c8    per-token private secret storage
identity/     ns_identity     identity_eab8e52c     identity store
sys/          ns_system       system_45f94812       system endpoints used for control, policy and debugging

$ bao secrets list
Path            Type         Accessor              Description
----            ----         --------              -----------
ai/pki/         pki          pki_637297c9          n/a
ai/platform/    kv           kv_ffc27177           n/a
ai/ssh/         ssh          ssh_59e57709          n/a
cubbyhole/      cubbyhole    cubbyhole_bb84b29c    per-token private secret storage
identity/       identity     identity_8dbe9cc1     identity store
sys/            system       system_28b1de5a       system endpoints used for control, policy and debugging
```

Read the difference carefully — it teaches three things at once:

1. `ai/platform/` exists in **both** listings. They are *different
   mounts* with *different accessors* (`kv_74e05c8a` vs `kv_ffc27177`).
   The accessor is the unique identity of a mount across the whole
   server; two namespaces can both have `ai/platform/` because they are
   different objects.
2. Every namespace gets its **own four** mounts automatically:
   `cubbyhole/`, `identity/`, `sys/` and the `token/` auth method. In a
   child namespace those show up with the `ns_` prefix (`ns_cubbyhole`,
   `ns_identity`, `ns_system`, `ns_token`) — that is OpenBao telling you
   "this is the namespace-scoped flavour of the built-in".
3. The root namespace's `ai/pki/` and `ai/ssh/` are simply **not in the
   namespace's list**, and the namespace's `ai/platform/` is not in the
   root's list. Neither side sees the other's mounts.

> The two listings above are a snapshot of the tree as it stood when
> this module was written. Later, in section 5.5, we mount a **second**
> `ai/pki/` engine *inside* `tenant-atlas` — and it will appear in that
> namespace's listing and still not in the root's. Two mounts, one
> path, two namespaces, one accessor each.

### 2.6 Proving isolation — same path, different secret

Write the Gemini key into the tenant's namespace:

```bash
$ bao kv put -namespace=tenant-atlas ai/platform/llm/gemini \
      api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" model="gemini-2.0-flash"
======= Secret Path =======
ai/platform/data/llm/gemini

======= Metadata =======
Key                Value
---                -----
created_time       2026-10-21T18:01:50.846648956Z
custom_metadata    <nil>
deletion_time      n/a
destroyed          false
version            1
```

Read it back **from inside the namespace**:

```bash
$ bao kv get -namespace=tenant-atlas ai/platform/llm/gemini
====== Secret Path ======
ai/platform/data/llm/gemini

======= Metadata =======
Key                Value
---                -----
created_time       2026-10-21T18:01:50.846648956Z
custom_metadata    <nil>
deletion_time      n/a
destroyed          false
version            1

===== Data =====
Key        Value
---        -----
api_key    AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr
model      gemini-2.0-flash
```

Now read the **same path** from the root namespace:

```bash
$ bao kv get ai/platform/llm/gemini
====== Secret Path ======
ai/platform/data/llm/gemini

======= Metadata =======
Key                Value
---                -----
created_time       2026-10-21T16:35:47.114015048Z
custom_metadata    <nil>
deletion_time      n/a
destroyed          false
version            1

===== Data =====
Key        Value
---        -----
api_key    AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr
model      gemini-2.5-flash
```

**This is the proof, and it is subtle.** The paths are identical. The
secret paths are identical. The *secret* is different: the root namespace
holds `gemini-2.5-flash`, the tenant namespace holds `gemini-2.0-flash`.
The tenant's key was never written to the root namespace and the root
namespace's key was never written to the tenant namespace. A namespace is
not a folder; it is a different tree with the same folder names in it.

And the reverse direction — a path that exists **only** in the root
namespace is invisible inside the tenant:

```bash
$ bao read -namespace=tenant-atlas ai/pki/issue
No value found at ai/pki/issue
```

`ai/pki/` was mounted in the root namespace only. Inside `tenant-atlas`
there is no `ai/pki/` mount at all, so there is nothing to read. The
error is `No value found` (exit code 2), not 403 — the path does not
exist in this tree, rather than existing and being forbidden.
(Section 5.5 later mounts a PKI engine *in* this namespace; the point
of this test is that the root namespace's mount was never visible here
in the first place.)

Now the case that trips people: ask for a path that exists in the
namespace but not in the root, **from the root**:

```bash
$ bao kv get ai/tenant/llm/gemini
Error making API request.

URL: GET http://127.0.0.1:9373/v1/sys/internal/ui/mounts/ai/tenant/llm/gemini
Code: 403. Errors:

* preflight capability check returned 403, please ensure client's policies
  grant access to path "ai/tenant/llm/gemini/"
```

`ai/tenant/` was mounted in the `tenant-alpha` namespace. From the root
namespace that path does not exist, and the KV CLI's preflight check
(used to discover the engine version) fails with a 403. **This 403 is
not a permissions problem and no policy will fix it.** It means "there is
no engine mounted at that path in this namespace". If you ever chase a
403 that a policy clearly grants, check the namespace first.

### 2.7 A namespace is NOT a path prefix

This is the single most common namespace bug, so it gets its own
section.

```bash
$ bao read tenant-atlas/ai/platform/llm/gemini
WARNING! The following warnings were returned from OpenBao:

  * Invalid path for a versioned K/V secrets engine. See the API docs for the
    appropriate API endpoints to use. If using the OpenBao CLI, use 'bao kv get'
    for this operation.
```

The command **succeeded** — and it read the *root* namespace's secret.
`tenant-atlas/ai/platform/llm/gemini` was interpreted as the path
`tenant-atlas/ai/platform/llm/gemini` inside the **root** namespace, and
because the root namespace has a KV v2 engine mounted at `ai/platform/`,
the CLI's path parsing landed on the root's mount and warned that you
forgot the `data/` segment.

**The rule:** a namespace is selected with `-namespace=` (or the
`BAO_NAMESPACE` environment variable), never by prefixing the path. Paths
are always relative to the namespace you are standing in.

```bash
# correct
$ bao kv get -namespace=tenant-atlas ai/platform/llm/gemini

# also correct
$ export BAO_NAMESPACE=tenant-atlas
$ bao kv get ai/platform/llm/gemini

# wrong: reads the root namespace, ignores the namespace
$ bao kv get tenant-atlas/ai/platform/llm/gemini
```

> **Production:** *Set `BAO_NAMESPACE` in the environment of every tool
> that talks to a tenant namespace, and treat "the namespace" as part of
> the connection string, not part of the resource path. The most
> dangerous version of this bug is the one that *works* — a read that
> silently returns the wrong tenant's secret is far worse than a 403.*

### 2.8 Nested namespaces

Namespaces nest. A child namespace is created relative to the namespace
you name with `-namespace=`, and **the name you pass is a single path
segment** — no slashes:

```bash
$ bao namespace create -namespace=tenant-atlas eu-west
Key                Value
---                -----
custom_metadata    map[]
id                 GwYgqR
locked             false
path               tenant-atlas/eu-west/
tainted            false
uuid               2ba256c9-11d3-5595-be9d-a7eb12a13a2d
```

The resulting path is `tenant-atlas/eu-west/` — the parent's path plus
your segment.

**This is the mistake to avoid.** Writing the full path yourself is the
instinct (the namespace's *path* has slashes, after all), and the server
rejects it. Here is that command running, and its exact error:

```bash
$ bao namespace create -namespace=tenant-atlas tenant-atlas/regions/eu-west
Error creating namespace: Error making API request.

Namespace: tenant-atlas/
URL: POST http://127.0.0.1:9373/v1/sys/namespaces/tenant-atlas/regions/eu-west
Code: 400. Errors:

* namespace name cannot contain /
```

(The error is `400 namespace name cannot contain /` when the parent
exists. If you also get `404 namespace not found`, the parent namespace
does not exist either — fix that first, then come back to the name.)

For a three-level tree, create it **one level at a time** — one call per
level, each one a single segment:

```bash
$ bao namespace create -namespace=tenant-atlas regions
$ bao namespace create -namespace=tenant-atlas/regions eu-west
```

The rule in one sentence: **the NAME argument is a single path segment,
and `-namespace=` says which existing namespace to create it inside.**

What is inherited and what is not is worth stating plainly:

Tokens carry their namespace with them. A token minted inside
`tenant-atlas` looks like this:

```bash
$ bao token create -namespace=tenant-atlas -policy=default -ttl=10m -format=json
  ... "client_token": "s.R6HcB0H9M9KAwXSf3eUM0uZ2.aNxERD" ...
```

Note the suffix: `.aNxERD` is the **namespace id** from section 2.4. The
server knows which namespace a token belongs to, without you having to
say so on every request — and the namespace of the *token* is what
decides which tree it can reach:

```bash
$ BAO_TOKEN="s.R6HcB0H9M9KAwXSf3eUM0uZ2.aNxERD" bao read ai/platform/llm/gemini
Error reading ai/platform/llm/gemini: Error making API request.

URL: GET http://127.0.0.1:9373/v1/ai/platform/llm/gemini
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

The namespace token cannot read the root namespace's secrets, and it
cannot read another tenant's either. Only the root token (the cluster
administrator) crosses namespaces freely.

- A child namespace starts with **only** the four built-ins
  (`cubbyhole/`, `identity/`, `sys/`, `token/`). It does **not** inherit
  the parent's mounts or policies.
- Its `sys/` is its own; `bao policy list -namespace=<child>` shows
  `default` and nothing else, no matter what the parent has.
- A parent-namespace token is **not** automatically a child-namespace
  token. If you need to operate across namespaces, you create a token
  *in* each namespace, or you use the root token and pass `-namespace=`
  explicitly (which the root token is allowed to do — it is the
  cluster administrator).

> **Trade-off:** *Deep namespace hierarchies make the tree look like an
> org chart, and org charts change. A namespace called
> `tenant-atlas/regions/eu-west` means that when the customer is acquired
> and re-organised, the hierarchy is wrong and the path of every policy
> that mentions it is wrong too. Two levels (root + tenant) is almost
> always enough.*

### 2.9 Per-namespace sealing (added in 2.6) — verified here

A normal namespace shares the server's seal. A **sealable** namespace
gets its *own* Shamir shares and its *own* seal state. You can seal one
tenant's namespace and leave the rest of the server running.

This is the "tenant-revocable access" property: a customer can be given
the ability to seal their own namespace, which makes their data
unreachable even to the platform operator, without taking the platform
down.

Create a namespace with its own key shares:

```bash
$ bao namespace create -key-shares=3 -key-threshold=2 tenant-sealable
Unseal Key 1: ba0af9c80f2d748257ed3e7a8b72e39e3195c051c4424a6bcddd4b595f7fb7336c
Unseal Key 2: 37b1b4e72c4534622f7805cc881f2f117a518c1efef9bc337c063e5051f3bc71d7
Unseal Key 3: 6bcfa2bf15d7fbc2c8e6fe6b5be30426d1cd2263bd87d43ede5d005f5b17d8d5a9

Namespace initialized with 3 key shares and a key threshold of 2. Please
securely distribute the key shares printed above. When the namespace is
re-sealed, you must supply at least 2 of these keys to unseal it.

Key                Value
---                -----
custom_metadata    map[]
id                 9b63SU
locked             false
path               tenant-sealable/
tainted            false
uuid               7871ddcf-549b-e25c-3036-0ad2dd64a4da
```

Note the wording: **"When the namespace is re-sealed"**. A sealable
namespace is created *sealed* — it starts sealed and you unseal it with
its own shares, separately from the server's shares.

```bash
$ bao namespace seal-status tenant-sealable
Key                Value
---                -----
Seal Type          shamir
Initialized        true
Sealed             true
Total Shares       3
Threshold          2
Unseal Progress    0/2
Unseal Nonce       n/a
```

`Sealed true` with `Unseal Progress 0/2` — the namespace has its own
quorum state, entirely separate from `bao status`.

Try to use it while it is sealed:

```bash
$ bao read -namespace=tenant-sealable sys/mounts
Error reading sys/mounts: Error making API request.

Namespace: tenant-sealable/
URL: GET http://127.0.0.1:9373/v1/sys/mounts
Code: 503. Errors:

* namespace is sealed
```

**503, not 403, not 404.** The server is up, the namespace exists, and
the data is locked. That distinction matters operationally: 503 means
"try again after someone unseals it", 403 means "you are not allowed",
404 means "not here".

Now unseal it with two of the three shares:

```bash
$ bao namespace unseal tenant-sealable ba0af9c80f2d748257ed3e7a8b72e39e3195c051c4424a6bcddd4b595f7fb7336c
Key                Value
---                -----
Seal Type          shamir
Initialized        true
Sealed             true
Total Shares       3
Threshold          2
Unseal Progress    1/2
Unseal Nonce       594138e2-b706-46ec-b4b8-568d6f9748b4

$ bao namespace unseal tenant-sealable 37b1b4e72c4534622f7805cc881f2f117a518c1efef9bc337c063e5051f3bc71d7
Key                Value
---                -----
Seal Type          shamir
Initialized        true
Sealed             false
Total Shares       3
Threshold          2
```

and it works again:

```bash
$ bao read -namespace=tenant-sealable sys/mounts
Key           Value
---           -----
cubbyhole/    map[accessor:cubbyhole_3be09343 config:map[default_lease_ttl:0 force_no_cache:false max_lease_ttl:0] ...]
identity/     map[accessor:identity_ec11b3d2 config:map[default_lease_ttl:0 force_no_cache:false max_lease_ttl:0] ...]
sys/          map[accessor:system_7e0058fd config:map[default_lease_ttl:0 force_no_cache:false max_lease_ttl:0] ...]
```

A **CLI gotcha** that will bite you the first time you script this:

```bash
$ bao namespace unseal tenant-sealable
Unseal Key (will be hidden):
An error occurred attempting to ask for an unseal key. The raw error message
is shown below, but usually this is because you attempted to pipe a value
into the unseal command or you are executing outside of a terminal (tty). You
should run the unseal command from a terminal for maximum security. If this
is not an option, the unseal key can be provided as the first argument to the
unseal command. The raw error was:  file descriptor 0 is not a terminal
```

The command tries to prompt interactively, and there is no TTY in a
script or a container. **Always pass the key as the first positional
argument** when automating — exactly as the error text says. (Note this
differs from `bao operator unseal`, where the key is also positional.
Both are fine; the interactive prompt is the trap.)

> **Production:** *Per-namespace sealing is the strongest isolation
> primitive OpenBao offers, and it is also the one you will use least
> often. It costs you an operational burden: two key ceremonies per
> tenant, per restore, per disaster recovery drill, forever. Use it when
> a contract or a regulator demands that the platform operator be
> technically unable to read customer data — not for ordinary tenant
> separation, where namespaces and policies are enough.*

### 2.10 Namespace vs paths + policies — the decision

This is the question a platform team actually has to answer, so here it
is as a table first and as judgement second.

| | **Paths + policies** | **Namespaces** |
|---|---|---|
| Isolation strength | Logical (ACL) | Logical **and** routing-level; optionally its own seal |
| Blast radius of a policy bug | A path in the same tree | Another tree; root token still has to name the namespace |
| Setup cost | Minutes | Hours (ceremony, per-tenant unmount/backup plans) |
| Onboarding a new team member | Write a policy | Write a policy **in that namespace** |
| Number of mounts you can see | All of them | Only that namespace's |
| Audit view | One log, filtered by path | One log, filtered by namespace |
| Backup / restore granularity | Per path | Per namespace (much easier) |
| Cost of undoing | None | **High** — see 2.11 |
| Per-tenant seal | ❌ | ✅ (2.9) |
| Good for | Teams inside one product line | Customers who must not see each other |

**The rule I would give a Meridian AI engineer:**

> **One customer = one namespace. One team = one path prefix + one
> policy.** If everyone inside Meridian AI is one company with one
> compliance boundary, namespaces mostly buy you operational overhead.
> The moment a *different company* stores data in your OpenBao, that
> company gets a namespace.

**Trade-off:** *The moment you reach for namespaces, you have also opted
into per-namespace backup/restore, per-namespace seal ceremonies, and
per-namespace policy management. A "just use paths" design that later
needs to become "just use namespaces" is a migration. A "just use
namespaces" design that later needs to become "one namespace per team"
is 20 namespaces you have to delete.*

### 2.11 The cost of undoing a namespace

This is the part people forget, so it gets a warning box.

- A namespace cannot be "merged" into another. There is no
  `namespace move`. You export the secrets (walk them with
  `bao kv list` / `bao read`), write them into the destination
  namespace, and then delete the source.
- Deleting a namespace is destructive and **irreversible**. There is
  `bao namespace delete` and, for a sealed one, `bao namespace
  delete-sealed`.
- Every policy, token and entity that referenced the namespace's paths
  has to be rewritten.
- A namespace's `uuid` appears in audit logs and in the identity store.
  After deletion, historical audit records still refer to a namespace
  that no longer exists. That is fine for auditing, but it means your
  tooling must tolerate "namespace not found" for historical records.

> **Production:** *Before you create a namespace, write down its
> `uuid` and its `id` in your runbook, alongside "what is inside it" and
> "who can unseal it". When a namespace disappears, that runbook entry is
> the only thing that tells you what was lost.*

---

## 3. Entities — the canonical identity

### 3.1 The concept in one plain sentence

An **entity** is the permanent record of *who somebody is*, independent
of how they proved it today.

### 3.2 Why it exists

Authentication methods answer "is this request allowed?" They do not
answer "is this the same person as last Tuesday?". Without entities:

- `aisha.rahman` logging in via OIDC and `aisha.rahman` logging in via
  the break-glass userpass account are two unrelated records.
- Revoking her access means finding every record she has touched.
- The audit log says "token `s.xxxx`" and you cannot answer "which
  human was that?".

An entity is the join key. Every auth method that logs the same person
in creates an **alias** that points at the same entity. Group membership
and audit history then follow the entity, not the login method.

### 3.3 The path — and the trap that catches everybody

```bash
$ bao write identity/entity name=ai-harness-service
Success! Data written to: identity/entity
```

The path is **`identity/entity`**. Not `auth/token/identities/entity`.
Not `auth/token/entity`. Not `identity/entities`.

The trap, in full:

```bash
$ bao list auth/token/identities/entity
No value found at auth/token/identities/entity
$ echo $?
2
```

And at the HTTP layer, which is where the "404" comes from:

```bash
$ curl -s -o /dev/null -w "%{http_code}\n" -H "X-Vault-Token: $BAO_TOKEN" \
      "$BAO_ADDR/v1/auth/token/identities/entity"
404
```

```
{"errors":["1 error occurred:\n\t* unsupported path\n\n"]}
```

**404, "unsupported path".** The route does not exist. It never has.
`auth/token/` is the *token auth method* — it issues tokens; it has
nothing to do with identities. The identity store is its own mount
(`identity/`, of type `ns_identity` inside a namespace), and that is
where entities live.

> **If you find a tutorial saying `auth/token/identities/entity`:** *it is
> describing a path that never worked the way the reader assumes, or an
> internal Vault API from a very old version. OpenBao 2.7 has exactly
> one identity store and it is at `identity/`.*

A second trap in the same area — **listing the parent does not work**:

```bash
$ bao list identity/entity
No value found at identity/entity
```

The CLI strips the trailing slash, so `identity/entity/` becomes
`identity/entity`, which is a *write* endpoint (POST), not a *list*
endpoint. To list entities you must list the **leaf** path:

```bash
$ bao list identity/entity/name
Keys
----
ai-harness-service
aisha.rahman
data-pipeline-service
```

`identity/entity/name/` is a LIST endpoint; `identity/entity/` is not.

### 3.4 What an entity record looks like

```bash
$ bao read identity/entity/name/ai-harness-service
Key                    Value
---                    -----
aliases                []
creation_time          2026-10-21T16:35:11.068938808Z
direct_group_ids       []
disabled               false
group_ids              []
id                     9cf62d70-c49a-6030-8ad9-ffde55575b08
inherited_group_ids    []
last_update_time       2026-10-21T16:35:11.068938808Z
merged_entity_ids      <nil>
metadata               <nil>
name                   ai-harness-service
namespace_id           root
policies               []
```

Fields worth understanding:

- `id` — the entity's UUID. This is the identity that never changes.
- `name` — a human label, and **not unique**. Two entities can be called
  `ai-harness-service`; the identity store will happily create a second
  one. Never use `name` as a join key — use `id`.
- `aliases` — the auth methods pointing at this entity. Empty here
  because nobody has logged in as this entity yet.
- `group_ids` / `direct_group_ids` / `inherited_group_ids` — the three
  ways a group can reach an entity. `direct` = added explicitly;
  `inherited` = reached through a parent group.
- `namespace_id` — `root` here. **Entities are namespace-scoped.** The
  same human in two namespaces has two entities unless you deliberately
  merge them.
- `metadata` — your own key/value notes. This is where you record
  "this entity is the CI pipeline, rotated 2026-10-01".

The group fields are empty here because nobody has been put in a group
yet — section 4.4 fills them in. `metadata` is empty for the same reason:
it is yours to write, and you write it after the fact:

```bash
$ bao write identity/entity/id/9cf62d70-c49a-6030-8ad9-ffde55575b08 \
      metadata="platform_owner=platform-team"
Success! Data written to: identity/entity/id/9cf62d70-c49a-6030-8ad9-ffde55575b08
```

Read the entity again and `metadata` now reads
`map[platform_owner:platform-team]`. Note the shape of that write:
`metadata` is a **map**, and the CLI's `key=value` form is how you put one
entry in it.

### 3.5 Aliases — how an auth method claims an entity

An alias is the pointer from a login method to an entity.

```bash
$ bao write identity/entity-alias name=ai-harness-service \
      mount_accessor="$(bao read -field=accessor sys/internal/ui/mounts/auth/token)"
Key             Value
---             -----
canonical_id    383e4960-3ccb-80ab-e8a7-85fdd0d68f4e
id              7e08a543-b007-a170-11e9-41f60c80c75e
```

Read it back by its own id:

```bash
$ bao read identity/entity-alias/id/7e08a543-b007-a170-11e9-41f60c80c75e
Key                    Value
---                    -----
canonical_id           383e4960-3ccb-80ab-e8a7-85fdd0d68f4e
creation_time          2026-10-21T18:03:55.107893634Z
custom_metadata        map[]
id                     7e08a543-b007-a170-11e9-41f60c80c75e
last_update_time       2026-10-21T18:03:55.107893634Z
local                  false
merged_from_canonical_ids    <nil>
metadata               <nil>
mount_accessor         auth_token_16acc7c8
mount_path             auth/token/
mount_type             token
name                   ai-harness-service
namespace_id           root
```

Read the `mount_accessor` field: `auth_token_16acc7c8` is the accessor
of the **token auth method** in the root namespace. `mount_path` is
`auth/token/`. The alias says: "when someone authenticates through this
auth method under the name `ai-harness-service`, they are entity
`383e4960-...`".

**A trap that matters:** notice the `canonical_id` here is
`383e4960-3ccb-80ab-e8a7-85fdd0d68f4e` — **not** the id of the
`ai-harness-service` entity we created earlier
(`9cf62d70-c49a-6030-8ad9-ffde55575b08`). Writing an alias with a
`name` that does not already have an alias **creates a second entity**,
because the identity store resolves "name" through the alias index, not
the entity-name index:

```bash
$ bao read identity/entity/id/383e4960-3ccb-80ab-e8a7-85fdd0d68f4e
Key                    Value
---                    -----
aliases                [map[canonical_id:383e4960-3ccb-80ab-e8a7-85fdd0d68f4e creation_time:2026-10-21T18:03:55.107893634Z ...]]
creation_time          2026-10-21T18:03:55.107890024Z
direct_group_ids       []
disabled               false
group_ids              []
id                     383e4960-3ccb-80ab-e8a7-85fdd0d68f4e
...
```

Two entities named `ai-harness-service` now exist. The name index shows
only one, because the index maps a name to the most recent one:

```bash
$ bao list identity/entity/name
Keys
----
ai-harness-service
aisha.rahman
data-pipeline-service
entity_6aa9956e.root
```

**The correct way** to attach an alias to an *existing* entity is to pass
the entity's `id` as `canonical_id`:

```bash
$ bao write identity/entity-alias name=ai-harness-service \
      mount_accessor="$(bao read -field=accessor sys/internal/ui/mounts/auth/token)" \
      canonical_id=9cf62d70-c49a-6030-8ad9-ffde55575b08
```

> **Production:** *Never rely on names to join identity records. Resolve
> the entity id first (`bao read identity/entity/name/<name>`), then
> write the alias with `canonical_id=<id>`. In practice, let the auth
> method create the alias for you — when a user logs in through OIDC or
> AppRole, OpenBao creates the entity and the alias in one step, and the
> `entity_id` appears in the token. Manual alias creation is for the
> case where you are back-filling identity after the fact.*

### 3.6 Entities outlive tokens — the whole point

Watch what happened to the token from Module 05's AppRole login. The
token's `auth.entity_id` field is where the join happens:

```json
"entity_id": ""
```

An empty `entity_id` means the token was issued by the **token auth
method** directly (a `bao token create`), not by a login method, so
there is no human behind it. When the same command is issued by AppRole,
OIDC, userpass or cert, the field carries the entity UUID and your audit
log can answer "which person was this token for?".

> **Production:** *In your audit log, record the token accessor and the
> entity id together, on every write. When you need to answer "what did
> this human do", the entity id is your join key across every auth
> method, and it survives the token's expiry. The token is gone; the
> entity is not.*

---

## 4. Groups — the unit of authorization

### 4.1 The concept in one plain sentence

A **group** is a named set of entities that carries policies.

### 4.2 Why it exists

Because "Dev Kapoor left the company" should be **one** change, not
twelve.

Attach policies to groups, put people in groups, and offboarding is
`bao write identity/group name=platform-operators member_entity_ids=...`
with one fewer id. Attach policies to people and offboarding is a
surgical removal from a dozen token roles, and you will miss one.

Meridian AI's model:

| Group | Members | Policies |
|---|---|---|
| `platform-operators` | aisha.rahman, dev.kapoor | `platform-operator` |
| `platform-admins` | aisha.rahman | `platform-admin` |
| `ai-services` | the `ai-harness` entity | `ai-harness-service` |

### 4.3 Do it

Create a group with a policy:

```bash
$ bao write identity/group name=platform-operators policies="platform-operator"
Success! Data written to: identity/group
```

Read it:

```bash
$ bao read identity/group/name/platform-operators
Key                  Value
---                  -----
alias                map[]
creation_time        2026-10-21T18:02:13.415253284Z
id                   e16a4aac-3c54-efaa-73e9-f63f02f48b55
last_update_time     2026-10-21T18:02:13.415253284Z
member_entity_ids    <nil>
member_group_ids     <nil>
metadata             <nil>
modify_index         1
name                 platform-operators
namespace_id         root
parent_group_ids     <nil>
policies             [platform-operator]
type                 internal
```

- `policies` — the ACL policies every member gets. This is the
  authorisation payload of the group.
- `member_entity_ids` — the humans and services directly in the group.
- `member_group_ids` — other groups nested inside this one.
- `parent_group_ids` — the inverse. Groups nest, so
  `platform-operators` can be a member of `engineering`, and everyone in
  `platform-operators` inherits `engineering`'s policies too.
- `type` — `internal` for a group you manage by hand. (`external` is for
  groups synchronised from an external directory, e.g. LDAP or OIDC
  groups — Module 05.)

List the groups:

```bash
$ bao list identity/group/name
Keys
----
ai-platform-operators
platform-operators
```

### 4.4 Add a member

```bash
$ bao write identity/group name=platform-operators \
      member_entity_ids="9cf62d70-c49a-6030-8ad9-ffde55575b08"
Success! Data written to: identity/group
```

The group now owns the member:

```bash
$ bao read identity/group/name/platform-operators
...
member_entity_ids    [9cf62d70-c49a-6030-8ad9-ffde55575b08]
...
```

and the entity now owns the membership:

```bash
$ bao read identity/entity/name/ai-harness-service
Key                    Value
---                    -----
aliases                []
creation_time          2026-10-21T16:35:11.068938808Z
direct_group_ids       [e16a4aac-3c54-efaa-73e9-f63f02f48b55]
disabled               false
group_ids              [e16a4aac-3c54-efaa-73e9-f63f02f48b55]
id                     9cf62d70-c49a-6030-8ad9-ffde55575b08
inherited_group_ids    []
...
```

Both sides of the relationship update. That is the tell that you are
looking at a real graph and not two disconnected lists.

### 4.5 The whole authorization chain, in one picture

```
  entity  ──member of──▶  group  ──carries──▶  policy  ──grants──▶  capability
 (a person                  (platform-          (platform-          (read on
  or a service)              operators)          operator)           ai/platform/...)
        │                        │                   │
        └──▶ auth/token/login ───┘                   │
              (the token that carries the            │
               entity's group policies)              ▼
                                          sys/capabilities-self
```

When `aisha.rahman` logs in through OIDC, OpenBao:

1. resolves the login to an **alias** → **entity**;
2. reads the entity's **group** memberships (direct + inherited);
3. collects the **policies** on those groups, plus any policies attached
   directly to the entity;
4. mints a **token** carrying that policy list;
5. evaluates **capabilities** for that token on every request.

Step 5 is the one that actually enforces. Steps 1–4 only *arrange* the
permissions. This is why "I am in the group" is not the same as "I can
read the secret" — the group's policies still have to grant the
capability on that path.

You can watch the whole chain in one command:

```bash
$ bao token capabilities ai/platform/llm/gemini
```

with a token issued for that entity, in Module 07.

> **Production:** *Give groups *no* policies of their own in the general
> case. Prefer "entity → group → policy" so that a policy change for
> the whole platform team is one `bao write identity/group`. Use a
> directly-attached entity policy only for the rare one-off (a person
> who needs exactly one extra read for one week).*

---

## 5. Leases — the lifecycle of a credential

### 5.1 The concept in one plain sentence

A **lease** is OpenBao's record of a credential that must be given back:
an id, how long it is valid, and how long it may be extended.

### 5.2 Why it exists

Because a secret store that hands out permanent credentials is a secret
store that will eventually hand out a credential to someone who should
not have it. A lease turns "we should revoke this eventually" into
"the server revokes it automatically, on time, without anyone remembering".

### 5.3 The lifecycle

```
                     ┌───────────────────────────────────────────┐
                     │                                           │
   request ─────────▶  created ──▶ active ──▶ renewed ──▶ active   │
                     │              │            (TTL reset,        │
                     │              │             max_ttl checked)  │
                     │              │                               │
                     │              ▼                               │
                     │         expired  ◀── TTL reaches 0           │
                     │      (auto-revoked)                          │
                     │                                               │
                     └──────────▶ revoked ◀── explicit revoke ─────┘
                                   (manual, immediate)
```

Read the diagram as three questions:

1. **How long until it dies on its own?** → `ttl`
2. **How long can it be kept alive?** → `max_ttl`
3. **Can I kill it right now?** → `sys/leases/revoke`

### 5.4 A token is not a lease (verified)

This is the part that trips up everybody, and OpenBao 2.7 shows it
beautifully. Create a token with a TTL and a renewal flag:

```bash
$ bao token create -renewable=true -ttl=30m -policy=platform-operator \
      -display-name=ai-harness-renewal-demo -format=json
{
  "request_id": "374d95eb-5683-6205-e005-bb56612b210c",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": null,
  "warnings": null,
  "auth": {
    "client_token": "s.hKpV709aD10LEUUpDHu95KRf",
    "accessor": "xbyDee1YCdkF7wzaEipYbVTp",
    "policies": ["default", "platform-operator"],
    "token_policies": ["default", "platform-operator"],
    "identity_policies": null,
    "metadata": null,
    "orphan": false,
    "entity_id": "",
    "lease_duration": 1800,
    "renewable": true,
    "mfa_requirement": null
  }
}
```

> **Where the token's type actually lives.** The `auth` object above has
> **11** keys, and `token_type` is not one of them — neither a token
> minted by `bao token create` nor the `auth` object of an AppRole login
> carries that key. The token's type is `service`, and you read it as
> **`"type": "service"`** in the `bao token lookup` output below. The
> spelling **`"token_type": "service"`** belongs to a third envelope: the
> `auth` object of a token issued by a login that *completed* a second
> factor, which carries 12 keys including `token_type` and `num_uses`
> (see [Module 05 §7.6](../05-auth-mfa-oidc/README.md)). Same value, three
> different envelopes — do not assume the key travels with it.

Look at the two TTLs in one response:

| Field | Value | What it means |
|---|---|---|
| `auth.lease_duration` | `1800` | **This token's TTL.** 1800 seconds = 30 minutes. |
| `auth.renewable` | `true` | This token may be renewed. |
| top-level `lease_id` | `""` | **Empty.** This token is not a lease. |
| top-level `lease_duration` | `0` | No lease. |
| top-level `renewable` | `false` | No lease. |

**A token has a TTL but is not a lease.** The token's lifetime is
tracked in the *token store*, and it is managed with the token auth
method's own endpoints:

```bash
$ bao token lookup -format=json
{
  "request_id": "57af07b3-1c3a-49e6-b0f1-b2742dc2a039",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": {
    "accessor": "xbyDee1YCdkF7wzaEipYbVTp",
    "creation_time": 1792605751,
    "creation_ttl": 1800,
    "display_name": "token-ai-harness-renewal-demo",
    "entity_id": "",
    "expire_time": "2026-10-21T18:32:31.670556526Z",
    "explicit_max_ttl": 0,
    "id": "s.hKpV709aD10LEUUpDHu95KRf",
    "meta": null,
    "num_uses": 0,
    "orphan": false,
    "path": "auth/token/create",
    "policies": ["default", "platform-operator"],
    "renewable": true,
    "ttl": 1721,
    "type": "service"
  },
  "warnings": null
}
```

- `creation_ttl: 1800` — the TTL the token was minted with.
- `ttl: 1721` — the TTL it has *left*. It is already counting down.
- `expire_time` — the wall-clock moment it dies.
- `explicit_max_ttl: 0` — no per-token override; the mount's
  `token_max_ttl` applies.

And the lease API refuses to know about it:

```bash
$ bao write sys/leases/lookup lease_id="s.hKpV709aD10LEUUpDHu95KRf"
Error writing data to sys/leases/lookup: Error making API request.

URL: PUT http://127.0.0.1:9373/v1/sys/leases/lookup
Code: 400. Errors:

* invalid lease
```

The token is not in the expiration manager. `sys/leases/*` is for
**dynamic secrets** — the credentials OpenBao *generates* for you: a
Postgres user with a random password, a PKI certificate, an SSH key.
(Whether a given dynamic secret comes back with a *lease* is a
per-engine setting — see 5.5, where it bites.)

### 5.5 A dynamic secret is a lease — when the engine says so

**The concept in one plain sentence:** a dynamic secret becomes a
*lease* only when the engine that issued it is configured to hand one
back.

This is where a very common assumption breaks. "A PKI certificate is a
leased secret" is **not** true by default in OpenBao 2.7.1. A
certificate has a *cryptographic* expiry baked into its X.509 `notAfter`
field, and the CA enforces that. OpenBao's lease manager is a second,
optional tracking system layered on top — and the switch lives on the
PKI **role**, as `generate_lease`, which defaults to **false**.

Here is the whole thing, end to end, in a fresh namespace.

**Step 1 — mount the engine inside the tenant namespace.** We do this
inside `tenant-atlas` on purpose: a tenant with its own CA is a real
Meridian AI shape, and it keeps this module's demo off the mount paths
that Module 08 claims for the platform.

```bash
$ bao secrets enable -namespace=tenant-atlas -path=ai/pki pki
Success! Enabled the pki secrets engine at: ai/pki/
```

**Step 2 — give it a CA to sign with.**

```bash
$ bao write -namespace=tenant-atlas ai/pki/root/generate/internal \
      common_name="Meridian AI Tenant Root CA" ttl=8760h
WARNING! The following warnings were returned from OpenBao:

  * TTL "8760h0m0s" is longer than permitted maxTTL "768h0m0s", so maxTTL is
    being used

  * This mount hasn't configured any authority information access (AIA)
    fields; this may make it harder for systems to find missing certificates
    in the chain or to validate revocation status of certificates. Consider
    updating /config/urls or the newly generated issuer with this information.
```

**Step 3 — tell the mount where its CA is published.**

```bash
$ bao write -namespace=tenant-atlas ai/pki/config/urls \
      issuing_certificates="$BAO_ADDR/v1/tenant-atlas/ai/pki/ca"
Key                              Value
---                              -----
crl_distribution_points          []
delta_crl_distribution_points    []
enable_templating                false
issuing_certificates             [http://127.0.0.1:9373/v1/tenant-atlas/ai/pki/ca]
ocsp_servers                     []
```

**Step 4 — create the role. This is where `generate_lease` lives.**

```bash
$ bao write -namespace=tenant-atlas ai/pki/roles/meridian-ai-harness \
      allowed_domains="meridian-ai.internal" allow_subdomains=true \
      generate_lease=true ttl=24h max_ttl=72h
WARNING! The following warnings were returned from OpenBao:

  * it is encouraged to disable generate_lease and rely on PKI's native
    capabilities when possible; this option can cause instance-wide issues with
    large numbers of issued certificates
```

Read that warning carefully. OpenBao is telling you that lease tracking
for certificates is **off by default and discouraged at scale**. Turn it
on when you want revocation events and a lease trail. Do not turn it on
because you assumed a certificate was a lease.

**Step 5 — issue a certificate and look at the top-level fields.**

```bash
$ bao write -format=json -namespace=tenant-atlas ai/pki/issue/meridian-ai-harness \
      common_name=data-pipeline.meridian-ai.internal ttl=24h
{
  "request_id": "53c19415-fdfb-368d-2fa5-29200657e808",
  "lease_id": "ai/pki/issue/meridian-ai-harness/Pl6CReA5ayCpMMjQc8bgz0Gc.aNxERD",
  "lease_duration": 86399,
  "renewable": false,
  "data": {
    ...
  },
  "warnings": null
}
```

Note the flag order: `-format=json` comes **before** the path, never after
the data fields. Put it at the end and the CLI hands `-format` to the
*endpoint* as a data field, the server answers
`Endpoint ignored these unrecognized parameters: [-format]`, and the
response you get back is not the JSON you asked for. §6.6 shows the same
rule and the same failure mode.

And the A/B, measured on the same mount with a second role that leaves
`generate_lease` at its default:

| Role setting | top-level `lease_id` | top-level `lease_duration` |
|---|---|---|
| `generate_lease=false` (the default) | `""` | `0` |
| `generate_lease=true` | `ai/pki/issue/meridian-ai-harness/<random>.aNxERD` | `86399` or `86400` |

(`lease_duration` is `86399` on most runs and `86400` on some — the lease
clock starts a fraction of a second before the response is serialised, so
the last second is sometimes still on the clock. Treat it as "24 hours".)

Two things to notice in the lease id:

1. `ai/pki/issue/meridian-ai-harness/` — the **path that created it**.
   That prefix is what makes prefix-based revocation possible (6.4).
2. `.aNxERD` — the **namespace id** of `tenant-atlas`, appended to the
   id. A lease id is namespace-qualified: it names both the path and
   the namespace it belongs to, so it can never be confused with an
   identically-named lease in another namespace. That is the whole
   point of the 2.7 lease changes (6.1).

Now look the lease up, **from inside the namespace**:

```bash
$ bao write -format=json -namespace=tenant-atlas sys/leases/lookup \
      lease_id="ai/pki/issue/meridian-ai-harness/Pl6CReA5ayCpMMjQc8bgz0Gc.aNxERD"
{
  "request_id": "a2cf89c4-eb11-50ef-69b0-2b036a4c7fad",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": {
    "expire_time": "2026-10-22T18:29:11.002938262Z",
    "id": "ai/pki/issue/meridian-ai-harness/Pl6CReA5ayCpMMjQc8bgz0Gc.aNxERD",
    "issue_time": "2026-10-21T18:29:11.509365381Z",
    "last_renewal": null,
    "namespace_path": "tenant-atlas/",
    "path": "ai/pki/issue/meridian-ai-harness",
    "renewable": false,
    "ttl": 86399
  },
  "warnings": null
}
```

- `path` — the endpoint that issued it. The revocation machinery uses
  this to call the engine's revoke hook.
- `namespace_path` — the namespace that owns the lease.
- `issue_time` / `expire_time` — the window.
- `last_renewal: null` — never renewed.
- `ttl` — seconds left.

Drop the namespace suffix and the lookup fails, because the id without
it does not name a lease that exists:

```bash
$ bao write -namespace=tenant-atlas sys/leases/lookup \
      lease_id="ai/pki/issue/meridian-ai-harness/Pl6CReA5ayCpMMjQc8bgz0Gc"
Namespace: tenant-atlas/
URL: PUT http://127.0.0.1:9373/v1/sys/leases/lookup
Code: 400. Errors:

* invalid lease
```

> **If you find a tutorial saying "a PKI certificate is a leased
> secret":** *it is describing a role configuration, not the engine
> default. With a default role, OpenBao 2.7.1 returns `lease_id: ""`
> and `lease_duration: 0` for an issued certificate — and the
> certificate is still perfectly valid, with a perfectly valid
> `notAfter`. The certificate's lifetime never depended on the lease
> manager.*

[Module 08 — Other Engines](../08-other-engines/README.md) builds out
the PKI engine in full (intermediate CAs, `issuer_ref`, the full role
reference) and documents the same `generate_lease` default from the
engine's side. Read the two modules together: this one owns the *lease*
half of the story, Module 08 owns the *certificate* half.

### 5.6 Renewal, and the `max_ttl` ceiling

Renew a **token** (the token store's own endpoint — not `sys/leases/renew`):

```bash
$ bao token renew -increment=1h
Key                  Value
---                  -----
token                s.hKpV709aD10LEUUpDHu95KRf
token_accessor       xbyDee1YCdkF7wzaEipYbVTp
token_duration       1h
token_renewable      true
token_policies       ["default" "platform-operator"]
identity_policies    []
policies             ["default" "platform-operator"]
```

And the record afterwards:

```bash
$ bao token lookup -format=json
{
  ...
  "data": {
    "accessor": "xbyDee1YCdkF7wzaEipYbVTp",
    "creation_ttl": 1800,
    "expire_time": "2026-10-21T19:03:49.970430972Z",
    "explicit_max_ttl": 0,
    "last_renewal": "2026-10-21T18:03:49.970431073Z",
    "last_renewal_time": 1792605829,
    ...
    "ttl": 3599
  }
}
```

`ttl` went from `1721` to `3599` and `last_renewal` appeared. The
`expire_time` moved forward by exactly the increment.

**The `max_ttl` rule:** a credential can be renewed as many times as you
like, but its *total* lifetime from creation can never exceed
`max_ttl`. When you hit the ceiling, the renewal returns the remaining
time instead of the requested increment — the clock stops. In OpenBao
2.7.1 the token auth method's default `token_max_ttl` is **32 days**,
and `token_ttl` is **32 days** too by default (the mount's
`default_lease_ttl` for the token mount is 768h = 32 days). You will
overwrite both in Module 05 when you configure AppRole.

```bash
$ bao secrets tune -default-lease-ttl=1h -max-lease-ttl=24h auth/token
```

> **Trade-off:** *A long `max_ttl` means a leaked token is dangerous for
> longer but your services renew less often. A short `max_ttl` means
> safe-by-default but forces renewal traffic and, if your app cannot
> renew, an outage. Meridian AI's recommendation: `token_ttl` of 15–60
> minutes for workloads, `token_max_ttl` of 24 hours, and the app
> re-authenticating at 80% of the TTL (Module 07).*

### 5.7 Expiry — the automatic revocation

Nothing has to happen at `expire_time`. The expiration manager tidies
expired leases on a timer and revokes the credential: the database
user is dropped, the certificate is de-listed, the token is deleted.
The client that was holding it gets a 403 on its next call and knows to
re-authenticate.

This is the property that makes short TTLs safe. The failure mode of a
short TTL is a *re-login*, not an outage — provided the client can
re-login, which is exactly why Module 07's client re-authenticates at
80% of the TTL instead of waiting for a 403.

### 5.8 Revocation — the manual kill switch

Three levels of force, from narrowest to widest:

| Level | Command | Kills |
|---|---|---|
| One lease | `bao write sys/leases/revoke lease_id="..."` | that one credential |
| One path | `bao write sys/leases/revoke-prefix/<prefix>` | every lease under that path |
| One path, ignoring errors | `bao write sys/leases/revoke-force/<prefix>` | same, but does not stop on backend errors |

The `force` variant exists because revocation calls out to the backend
(rotate the Postgres password, drop the DB user) and a backend that is
down would otherwise abort the whole revocation. The OpenBao source is
blunt about the danger:

> *"Unlike `/sys/leases/revoke-prefix`, this path ignores backend errors
> encountered during revocation. This is potentially very dangerous and
> should only be used in specific emergency situations where errors in
> the backend or the connected backend service prevent normal
> revocation."*

**Use `revoke-force` when you are revoking a leaked credential and the
backend is broken. Nothing else.**

> **Production:** *A revoke that leaves the backend in a half-revoked
> state is worse than one that fails loudly, because your incident
> timeline will claim "revoked" while the credential still works. Always
> read the exit code and the response, and always confirm with a second
> lookup (see 6.6).*

---

## 6. The 2.7 lease endpoint matrix — the part you will get wrong

### 6.1 What changed and why

In OpenBao 2.7.0, a set of lease endpoints was **removed**, as part of the
fix for **CVE-2026-45808** (cross-namespace lease revocation). The old
top-level `sys/renew` and `sys/revoke*` endpoints operated on lease ids
that were not namespaced, which made it possible to revoke a lease
belonging to a *different* namespace than the one the caller was
operating in. The remediation moved all lease management under
`sys/leases/`, where the namespace is part of the path.

> ⚠️ **Changed in 2.7:** *If you are following a Vault-era tutorial that
> says `vault renew <lease_id>` or `vault revoke <lease_id>`, it is
> describing HashiCorp Vault. OpenBao 2.7 answers `404 unsupported
> path`.*

### 6.2 The full matrix, as observed on a live 2.7.1 server

Every row below was executed against a running OpenBao v2.7.1 with a
root token. The status code is the real HTTP status.

| Endpoint | Method | Observed | Body | Verdict |
|---|---|---|---|---|
| `sys/renew` | POST | **404** | `unsupported path` | ❌ removed |
| `sys/revoke` | POST | **404** | `unsupported path` | ❌ removed |
| `sys/revoke-prefix` | POST | **404** | `unsupported path` | ❌ removed |
| `sys/revoke-force` | POST | **404** | `unsupported path` | ❌ removed |
| `sys/renew/<prefix>` | POST | **404** | `unsupported path` | ❌ removed |
| `sys/revoke/<prefix>` | POST | **404** | `unsupported path` | ❌ removed |
| `sys/revoke-prefix/<prefix>` | POST | **404** | `unsupported path` | ❌ removed |
| `sys/revoke-force/<prefix>` | POST | **404** | `unsupported path` | ❌ removed |
| `sys/leases/renew-force` | POST | **404** | `unsupported path` | ❌ removed |
| `sys/leases/renew` | POST | **400** | `lease_id must be specified` | ✅ exists |
| `sys/leases/revoke` | POST | **400** | `lease_id must be specified` | ✅ exists |
| `sys/leases/lookup` | POST | **400** | `lease_id must be specified` | ✅ exists |
| `sys/leases/lookup` (bogus id) | POST | **400** | `invalid lease` | ✅ exists |
| `sys/leases/revoke-prefix/<prefix>` | POST | **204** | *(empty)* | ✅ exists |
| `sys/leases/revoke-force/<prefix>` | POST | **204** | *(empty)* | ✅ exists |
| `sys/leases/lookup/<prefix>` | LIST | **200** | `["issue/"]` | ✅ exists |
| `sys/leases/count` | GET | **404** | `{"errors":[]}` | ⚠️ see 6.5 |

### 6.3 The raw evidence

Removed endpoints — all four return the identical 404 body:

```
sys/renew                    POST 404
    errors: ['1 error occurred:\n\t* unsupported path\n\n']
sys/revoke                   POST 404
    errors: ['1 error occurred:\n\t* unsupported path\n\n']
sys/revoke-prefix            POST 404
    errors: ['1 error occurred:\n\t* unsupported path\n\n']
sys/revoke-force             POST 404
    errors: ['1 error occurred:\n\t* unsupported path\n\n']
sys/leases/renew-force       POST 404
    errors: ['1 error occurred:\n\t* unsupported path\n\n']
```

Surviving endpoints — note that a **400 with a specific message** means
"the route exists and it wants more from you". A 404 with
`unsupported path` means "the route does not exist". That distinction is
the entire diagnostic:

```
sys/leases/renew             POST 400
    errors: ['lease_id must be specified']
sys/leases/revoke            POST 400
    errors: ['lease_id must be specified']
sys/leases/lookup            POST 400
    errors: ['lease_id must be specified']
```

And here is the same distinction seen from the CLI, where a 400 is
rendered with the full error context:

```bash
$ bao write -namespace=tenant-atlas sys/leases/renew \
      lease_id="ai/pki/issue/meridian-ai-harness/Pl6CReA5ayCpMMjQc8bgz0Gc.aNxERD" increment=1h
Namespace: tenant-atlas/
URL: PUT http://127.0.0.1:9373/v1/sys/leases/renew
Code: 400. Errors:

* lease is not renewable
```

**Read that error carefully: it is a success for the purpose of this
test.** `lease is not renewable` means the request reached the renew
handler, found the lease, and found that *this particular lease* cannot
be renewed. If the endpoint had been removed you would have seen
`404 / unsupported path` instead. The two responses are as different as
"the cashier says no" and "there is no cashier".

### 6.4 The prefix goes in the PATH, not the body

This is the second trap, and it is the one that will cost you an
incident.

**Wrong** (prefix in the request body):

```bash
$ bao write sys/leases/revoke-prefix prefix=ai/pki
Error writing data to sys/leases/revoke-prefix: Error making API request.

URL: PUT http://127.0.0.1:9373/v1/sys/leases/revoke-prefix
Code: 404. Errors:

* 1 error occurred:
	* unsupported path
```

**Right** (prefix in the URL path — and the namespace in the header,
because that is where the namespace lives for a raw HTTP call):

```bash
$ curl -s -o /dev/null -w "http=%{http_code}\n" -X POST \
      -H "X-Vault-Token: $BAO_TOKEN" \
      -H "X-Vault-Namespace: tenant-atlas" \
      "$BAO_ADDR/v1/sys/leases/revoke-prefix/ai/pki" -d '{}'
http=204
```

**204 No Content** — the revocation succeeded and there is nothing to
say. Here is the whole sequence with the lease visible before and after:

```bash
$ bao list -format=json -namespace=tenant-atlas sys/leases/lookup/ai/pki
[
  "issue/"
]

$ curl -s -o /dev/null -w "http=%{http_code}\n" -X POST \
      -H "X-Vault-Token: $BAO_TOKEN" \
      -H "X-Vault-Namespace: tenant-atlas" \
      "$BAO_ADDR/v1/sys/leases/revoke-prefix/ai/pki" -d '{}'
http=204

$ bao list -format=json -namespace=tenant-atlas sys/leases/lookup/ai/pki
{}

$ bao write -namespace=tenant-atlas sys/leases/lookup \
      lease_id="ai/pki/issue/meridian-ai-harness/Pl6CReA5ayCpMMjQc8bgz0Gc.aNxERD"
Code: 400. Errors:

* invalid lease
```

Before: one lease under `ai/pki`. After: **zero** leases, and the lease
id is gone (`invalid lease`). That is a revoked lease, verified twice by
two different endpoints.

> **Production:** *Write your revocation runbook with the path form:
> `sys/leases/revoke-prefix/<path>`. Bookmark the API docs for
> `sys/leases/revoke-prefix` and `sys/leases/revoke-force` — the body
> form is a Vault-era habit and it 404s on 2.7.*

### 6.5 `sys/leases/count` — a discrepancy you should know about

This endpoint is documented as a way to count live leases, and it is
the kind of thing an incident responder reaches for. On this
**OpenBao v2.7.1** build it did not answer:

```bash
$ curl -s -X GET -H "X-Vault-Token: $BAO_TOKEN" "$BAO_ADDR/v1/sys/leases/count" -w "\nhttp=%{http_code}\n"
{"errors":[]}

http=404
```

```bash
$ curl -s -X POST -H "X-Vault-Token: $BAO_TOKEN" "$BAO_ADDR/v1/sys/leases/count" -d '{}' -w "\nhttp=%{http_code}\n"
{"errors":["1 error occurred:\n\t* unsupported operation\n\n"]}

http=405
```

```bash
$ bao list -format=json sys/leases/count
{}
```

**What I can tell you with confidence:** the `leases/count` path exists
in the OpenBao 2.7.1 binary (it is present in the framework's internal
path list), but the HTTP route did not respond to GET, POST, or a LIST
request on this build, while its siblings `sys/leases/lookup`,
`sys/leases/renew` and `sys/leases/revoke` all behaved normally.

**What I cannot tell you:** whether this is a build-specific
regression, a namespace-scoping change, or an endpoint that moved.
**Do not build your incident runbook on `sys/leases/count` without
testing it on your own build first.**

**What to use instead** — count the leases yourself:

```bash
$ bao list -format=json -namespace=tenant-atlas sys/leases/lookup/ai/pki
[
  "issue/"
]
```

That is a LIST of the lease ids under a prefix. The count is the number
of entries. It works, it is namespace-scoped, and it cannot be faked by
a stale count.

### 6.6 The incident-response playbook

When a credential leaks at Meridian AI, this is the order of operations.
Every command here is verified above.

```bash
# 1. What is out there?  (LIST the leases under the prefix)
$ bao list -format=json -namespace=tenant-atlas sys/leases/lookup/ai/pki
[
  "issue/"
]

# 2. Inspect one before you kill it
$ bao write -namespace=tenant-atlas sys/leases/lookup \
      lease_id="ai/pki/issue/meridian-ai-harness/Pl6CReA5ayCpMMjQc8bgz0Gc.aNxERD"

# 3. Kill everything under that path
$ curl -s -o /dev/null -w "http=%{http_code}\n" -X POST \
      -H "X-Vault-Token: $BAO_TOKEN" \
      -H "X-Vault-Namespace: tenant-atlas" \
      "$BAO_ADDR/v1/sys/leases/revoke-prefix/ai/pki" -d '{}'
http=204

# 4. Prove it is gone
$ bao list -format=json -namespace=tenant-atlas sys/leases/lookup/ai/pki
{}
```

Step 4 is not optional. A revocation that returns 204 has told you the
*request* was accepted; only a second lookup tells you the *credential*
is dead.

**For tokens specifically**, use the token API, not the lease API — they
are different subsystems:

```bash
# kill one token by accessor (the safe form: the secret never appears).
# NOTE: -accessor is a BOOLEAN flag - the accessor id is the positional
# argument. "-accessor=<id>" fails with:
#   invalid boolean value "xbyDee..." for -accessor: strconv.ParseBool:
#   parsing "xbyDee...": invalid syntax
$ bao token revoke -accessor xbyDee1YCdkF7wzaEipYbVTp
Success! Revoked token (if it existed)
```

There is **no `-role` flag** on `bao token revoke` in 2.7.1 — it answers
`flag provided but not defined: -role` — and the token API has no
"revoke every token of a role" endpoint either. The `-role` shape is
tempting precisely because "kill everything belonging to one service in
a single command" is exactly what an incident responder wants, and it is
the shape that older Vault-era runbooks and other secret managers
advertise. OpenBao 2.7.1 simply does not have it, so here is the real
mechanism, in three steps.

**Step 1 — list the accessors.** There is exactly one accessor index in
2.7.1, and it covers every token:

```bash
$ bao list -format=json auth/token/accessors
[
  "O67dhW6btreOwJ9YGvdK2w0O",
  "a5iRtRhqBfTRQdr9n5OVxPc4",
  "2vxXTgcWpMwLlKOiCvohmMki",
  ...
]
```

**Step 2 — ask each accessor which role minted it.** The lookup tells
you the token's `path` and `display_name`, which is how you recognise
"this one belongs to the AI harness":

```bash
$ bao write -format=json auth/token/lookup-accessor accessor=Y43XjL5ysmwkVtVfFybVOZmF
{
  "request_id": "0ce4bb6e-2d97-978b-8b3d-bd25b64eca91",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": {
    "accessor": "Y43XjL5ysmwkVtVfFybVOZmF",
    "bound_cidrs": [
      "127.0.0.1"
    ],
    "creation_time": 1792609222,
    "creation_ttl": 900,
    "display_name": "approle",
    "entity_id": "bb23ffdf-c445-ec34-d6c9-b47c9a3f0811",
    "expire_time": "2026-10-21T19:15:22.78805121Z",
    "explicit_max_ttl": 0,
    "id": "",
    "issue_time": "2026-10-21T19:00:22.788061989Z",
    "meta": {
      "role_name": "ai-harness-service"
    },
    "num_uses": 0,
    "orphan": true,
    "path": "auth/approle/login",
    "policies": [
      "ai-harness-service"
    ],
    "renewable": true,
    "ttl": 630,
    "type": "service"
  },
  "warnings": null
}
```

Note that it returns an **empty `id`** — the accessor lookup deliberately
never hands back the token secret, which is exactly why the accessor is
the right handle to keep in your incident tooling.

Two details in that output are worth reading twice. `path` is
`auth/approle/login`, not `auth/token/create` — that is how you know
which *auth method* minted the token. And `meta.role_name` is
`ai-harness-service`, which is how you recognise "this one belongs to the
AI harness" without reading any policy.

> **CLI gotcha:** put `-format=json` **before** the path, not after the
> data fields. `bao write auth/token/lookup-accessor accessor=... -format=json`
> sends `-format` to the *endpoint* as a data field and the server answers
> with `Endpoint ignored these unrecognized parameters: [-format]`.

**Step 3 — revoke the ones that belong to the service.**

```bash
$ bao token revoke -accessor 9793c9b3-e04a-46f3-e7b8-748d7da248da
Success! Revoked token (if it existed)
```

> ⚠️ **A plausible-looking command that does not exist:** *it is very
> tempting to reach for a role-scoped accessor list, something like
> `bao list auth/approle/role/ai-harness-service/token/accessors`. On
> OpenBao 2.7.1 that path does not exist — verified on a live server
> with a live AppRole token in hand, it answers `No value found at
> auth/approle/role/ai-harness-service/token/accessors` (exit 2), and
> the 2.7.1 binary contains only the single global accessor path
> `auth/token/accessors`. Use the three steps above, not a path you
> wish existed.*

**And for dynamic secrets** (the leased side of the world), the sweep is
the prefix revoke from 6.4 — with the prefix in the **URL path**:

```bash
$ bao write -force sys/leases/revoke-prefix/<path>
Success! Data written to: sys/leases/revoke-prefix/ai/platform
```

Two things about that command line, both learned the hard way:

- **`-force` is required.** The endpoint takes its argument from the URL
  path and has no body, so `bao write` refuses to send an empty one:

  ```console
  $ bao write sys/leases/revoke-prefix/ai/platform
  Must supply data or use -force
  ```

- **Do not use the body form.** `bao write sys/leases/revoke-prefix
  prefix=<path>` is a Vault-era habit and answers `404 unsupported path`
  on 2.7.1. The prefix belongs in the URL.

The raw HTTP equivalent, if you are scripting it, takes no body at all:

```bash
$ curl -s -o /dev/null -w '%{http_code}\n' -X POST \
    -H "X-Vault-Token: $BAO_TOKEN" \
    "$BAO_ADDR/v1/sys/leases/revoke-prefix/ai/platform"
204
```

> **Production:** *Prefer `-accessor` over the token value in every
> revocation command. The accessor is a non-secret handle; the token
> value is the secret, and putting it on a command line writes it into
> your shell history and possibly into a process listing on another
> machine.*

---

## 7. The GUI for this module

Open <http://127.0.0.1:8200/ui> and log in with the root token.

The labels below are the literal strings in the OpenBao 2.7.1 UI bundle
(verified by extracting them from the served JavaScript, not guessed).

### Namespaces

The sidebar contains a **Namespaces** entry (route
`vault.cluster.access.namespaces`), and the UI tracks your **Current
namespace** in the top bar. Switching namespace in the UI changes the
namespace the whole UI operates in — the equivalent of the
`BAO_NAMESPACE` environment variable.

| GUI | CLI equivalent |
|---|---|
| Sidebar → **Namespaces** | `bao namespace list` |
| Namespaces page → create form | `bao namespace create <name>` |
| Namespace switcher (top bar) | `BAO_NAMESPACE=<ns>` or `-namespace=<ns>` |
| Namespace seal status | `bao namespace seal-status <ns>` — **CLI only** |

> The GUI does **not** expose per-namespace sealing. `bao namespace
> seal` / `bao namespace unseal` are CLI-only in 2.7.1, because they
> involve key ceremonies that the UI deliberately does not attempt.
> That is the pattern to learn: **the UI is for the daily path, the CLI
> is for the dangerous one.**

### Identity

The **Identity** pages carry **Entities**, **Groups** and **Aliases** as
the three things you manage there. (In the 2.7.1 UI they live under the
top-level **Access** section, at the route
`vault.cluster.access.identity` — there is no "Identity" item in the
sidebar itself, so look for **Entities** and **Groups** under **Access**.)

The UI surfaces the same fields the CLI does — **Entity ID**, **Group
ID**, **Disable entity**, **Entities to merge from**, **Entity to merge
to** (the merge flow for combining two entities after a duplicate is
discovered), and **Group ID**.

| GUI | CLI equivalent |
|---|---|
| Identity → **Entities** → create | `bao write identity/entity name=<n>` |
| Identity → **Entities** → list | `bao list identity/entity/name` |
| Identity → **Groups** → create, add members | `bao write identity/group name=<n> member_entity_ids=<ids>` |
| Identity → **Aliases** | `bao write identity/entity-alias ...` |
| Disable an entity | `bao write identity/entity/id/<id> disabled=true` |

### Leases

The UI's **Leases** page (with **Lease ID**, **Lease Duration**, **Lease
will expire after**, **Filter leases**, **Default Lease TTL** and
**Disable lease after**) shows the leases the current token can see and
lets you revoke them.

| GUI | CLI equivalent |
|---|---|
| Leases page | `bao list sys/leases/lookup/<prefix>` |
| Revoke a lease | `bao write sys/leases/revoke lease_id=<id>` |
| Lease duration on a mount | `bao secrets tune -default-lease-ttl=... <mount>` |

What the GUI does **not** do: revoke by *prefix* in one shot
(`sys/leases/revoke-prefix/<prefix>`), or force-revoke. Those are CLI
only — which is fine, because the prefix revoke is exactly the thing
you want to run from a script during an incident, not by clicking.

---

## 8. What you learned

- [ ] A namespace is an isolated subtree with its own mounts, policies,
      auth methods, tokens and identity store — and a namespace is
      selected with `-namespace=`, **never** by prefixing a path.
- [ ] The same secret path in two namespaces holds two different
      secrets, and each namespace gets its own `cubbyhole/`, `identity/`,
      `sys/` and `token/`.
- [ ] A child namespace does not inherit its parent's mounts or
      policies, and a root-namespace token does not automatically reach
      into a child namespace.
- [ ] A **sealable** namespace has its own Shamir shares and its own
      seal state; sealing it returns 503 `namespace is sealed` while the
      rest of the server keeps running.
- [ ] `bao namespace unseal <ns> <key>` needs the key as a positional
      argument when automating — the interactive prompt fails with
      `file descriptor 0 is not a terminal`.
- [ ] One customer = one namespace; one team = one path prefix + one
      policy. Deleting a namespace is destructive and irreversible.
- [ ] The identity store is at **`identity/entity`**.
      `auth/token/identities/entity` returns **404 `unsupported path`**.
- [ ] `bao list identity/entity` does not work; list the leaf
      `identity/entity/name`.
- [ ] An entity is a UUID that outlives every token. Names are labels,
      not keys, and they are not unique.
- [ ] An alias connects an auth method to an entity. To attach to an
      existing entity, pass `canonical_id=<entity id>` — a name-only
      alias write silently creates a *second* entity.
- [ ] Groups carry policies; members are entities. Changing one group
      membership is the whole offboarding story.
- [ ] A token has a TTL but **is not a lease**: its TTL is in
      `auth.lease_duration` and it is managed with `bao token
      lookup` / `bao token renew`.
- [ ] A dynamic secret becomes a lease **only if the engine is
      configured to emit one** — a PKI role must set
      `generate_lease=true` (default `false`). When it does, the lease
      id is in the top-level `lease_id` and the lease is managed with
      `sys/leases/*`.
- [ ] A lease has a `ttl` (time left) and a `max_ttl` (ceiling on total
      lifetime). Renewal resets the TTL; the ceiling does not move.
- [ ] In 2.7, `sys/renew`, `sys/revoke`, `sys/revoke-prefix`,
      `sys/revoke-force` and `sys/leases/renew-force` are **404**. Use
      `sys/leases/renew`, `sys/leases/revoke`, `sys/leases/lookup`,
      `sys/leases/revoke-prefix/<prefix>` and
      `sys/leases/revoke-force/<prefix>`. The reason is
      **CVE-2026-45808** (cross-namespace lease revocation).
- [ ] The prefix for `revoke-prefix` / `revoke-force` goes in the
      **URL path**, not the request body.
- [ ] `lease is not renewable` (400) proves the renew endpoint exists;
      `unsupported path` (404) proves it does not.

---

## 9. What's next

You came from [Module 03 — Policies](../03-policies/README.md), where you
learned what a token may do. This module gave it three more dimensions:
**where** (namespaces), **who** (entities and groups) and **for how
long** (leases).

Next is [Module 05 — Auth Methods, MFA & OIDC](../05-auth-mfa-oidc/README.md),
which turns the identity and group model into an actual login:
**AppRole for machines** (the `ai-harness` service), **OIDC with
Keycloak for humans** (`aisha.rahman`), and **MFA** so that a human
login is worth more than a machine one. That module also fixes the
token TTLs you saw in this one, and it is where the entity id from
`auth/entity_id` finally appears in a real token.

After that, [Module 06 — Crypto Tooling](../06-crypto-tooling/README.md)
gives you the crypto toolbox (wrap, random, hash, Transit) and
[Module 07 — App Integration](../07-app-integration/README.md) finally
wires a FastAPI service to OpenBao.

---

## 10. Homework

1. **Build the tenant boundary, properly.** Create a namespace
   `tenant-northwind` with its own key shares
   (`-key-shares=3 -key-threshold=2`), mount a KV v2 engine at
   `ai/platform` inside it, write the Postgres password
   `Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK` at
   `ai/platform/db/postgres`, and seal the namespace. Then prove, with
   captured output, that (a) the root namespace cannot read it, (b) the
   namespace returns 503 `namespace is sealed` while sealed, and (c) it
   works again after you unseal it with two of its three shares. Write
   down exactly which two commands prove each claim.

2. **Do the isolation matrix yourself.** In a fresh namespace, enable
   `kv-v2` at `ai/platform` and in the root namespace enable `kv-v2` at
   `ai/platform` too. Put a *different* value at the *same* path in
   each. Then produce the full table of what each side can see:
   mounts, policies, auth methods, and the secret. Your table should
   match section 2.3. If any cell surprises you, investigate it and
   write down why.

3. **Fix the alias mistake on purpose.** Create an entity
   `secret-rotation-bot`, then create an alias for it **by name only**
   and observe that a second entity appears. Then create the alias
   properly with `canonical_id` and show that the entity now lists the
   alias. Put the two entity ids side by side and explain in three
   sentences why the first approach is dangerous in production.

4. **Complete the lease endpoint matrix yourself, from scratch.** On a
   clean server, run **every** endpoint in the 6.2 table and record the
   status code and body — including `sys/leases/count`, and including
   `sys/leases/revoke-prefix` with the prefix in the body *and* in the
   path. Then build a lease you can actually revoke: create a namespace,
   mount `pki` inside it, give it a CA, create a role **with
   `generate_lease=true`**, and issue a certificate. Write a short
   runbook page titled "Revoke everything under `ai/pki`" containing the
   exact command, and prove it works by listing the leases under the
   prefix before and after the revocation.

5. **Prove the `max_ttl` ceiling.** Create a token with a short TTL and
   a low `token_max_ttl` (tune `auth/token` in a scratch mount or use
   `-explicit-max-ttl` on the token), renew it repeatedly past the
   ceiling, and capture the moment the renewal stops extending the
   token. Explain in one paragraph why "renewable = unlimited" is a
   dangerous phrase to put in a design document.

---

> **Production:** *A secret store is not safe because the data is
> encrypted. It is safe because the *boundaries* are real: a namespace
> you cannot accidentally read across, an entity that survives every
> token, a group you can change in one write, and a lease that dies on
> its own. This module gave you all four — and showed you exactly which
> of them OpenBao 2.7 will let you get wrong.*
