# Module 03 — Policies & ACLs: Least Privilege

> **Where we are.** Modules 01 and 02 gave us a running OpenBao with the Gemini
> key safely inside it. But right now, *every* token we mint can read
> *everything* — because the only token we have is the root token. That is a
> store where one leaked credential equals full company compromise. This module
> is where Meridian AI stops being a single-admin secret store and starts
> being a platform that five different services can share without any of them
> being able to read each other's secrets.

**Status:** complete and verified against a live OpenBao **2.7.1** server. Every
command output in this module was executed; the enforcement matrix in §12 is
observed, not invented.

---

## 0. The 60-second version

| Concept | One line |
|---|---|
| **Policy** | An HCL document that maps paths → allowed operations. |
| **Token** | A bearer credential that carries a *set* of policies. |
| **Capability** | One operation: `read`, `list`, `create`, `update`, `delete`, `sudo`, `deny`, `patch`, `scan`. |
| **Allow-list** | You write what *is* allowed. Everything not written is denied. |
| **Union** | A token's effective permissions are the union of all its policies. |
| **`default` policy** | Auto-attached to every token; 16 self-service paths and nothing else. |
| **`root` policy** | A sentinel, not a document. All operations, everywhere. |
| **`sudo`** | The "you may administer the vault itself" bit: seal, policy authoring, mount creation, break-glass. |
| **Read/write separation** | Give the app `read` and the job `write`. A compromised reader cannot corrupt. |
| **Control Group** | New in 2.7. A policy can require a *second person's* approval before a sensitive read is released. |
| **`deny`** | An explicit hole punched in a grant. Overrides every other policy on the same token. |
| **Wildcard `*`** | Matches **any characters including `/`**. Not "one folder level". |
| **`bao token capabilities`** | The policy simulator. Ask a token what it can do at a path. |

---

## 1. Why this matters

The engineer who left before you put every secret in one `.env` file and
committed it. Ask the six questions that any competent security reviewer asks,
and every answer is "no":

| Question | `.env` in Git | OpenBao with policies |
|---|---|---|
| Who can read it? | Everyone with repo access | One service, one path |
| Is it in Git history? | Yes, forever | No, never |
| Can you rotate it? | Edit a file, redeploy | Write a new version, consumers re-read |
| Can you audit it? | No | Every read is an audit-log line |
| Can you scope it? | All-or-nothing | Per path, per operation |
| Does it reach the app at runtime? | No — it's a build artifact | Yes, at process start |

The last row is the one people miss. A secret store that only *stores* secrets
is a database with extra steps. The point of OpenBao is the **token**: a
short-lived, scoped, auditable credential that a workload presents at runtime
and that grants it exactly what it needs.

Today, everything we have is the root token. Root can do everything. If that
token leaks from a CI log, an attacker has the Gemini key, the Postgres
password, the Redis password, the Keycloak client secret, the policies, and
the ability to rewrite the policies so you never notice.

**What breaks if you skip policies:** you will end up back at `.env`, but worse
— this time with a central store that makes the blast radius *look* small
because it's one URL and one password.

> **Production:** *Every identity in Meridian AI gets its own policy, and every
> policy is written as if the identity is hostile.* If a policy is hard to
> justify in a code review ("why does the AI harness need `list` on
> `ai/platform/metadata/db`?"), the answer is delete it.

---

## 2. The authorization model

### 2.1 The three inputs

Every single request OpenBao serves is decided by the same three things:

1. **The path** — which secret is being touched, e.g. `ai/platform/data/llm/gemini`.
2. **The token** — who is asking. The token carries a list of policy names.
3. **The policies** — the HCL documents named by that token.

If any policy attached to the token grants the operation for that path, the
request is allowed.

### 2.2 Absence is deny

This is the single most important mental model, and almost every OpenBao
tutorial gets it wrong by implication.

> **What this means:** you do not write rules for what is forbidden. You write
> rules for what is permitted. A request that matches no rule is refused.
>
> *Why it exists:* a deny-list has to enumerate every possible bad path, and
> the enumeration is always incomplete. An allow-list only has to enumerate the
> good paths, and a missing good path fails *closed*.
>
> *What if you got it backwards:* one forgotten rule in a deny-list and the
> secret is world-readable. One forgotten rule in an allow-list and the app
> fails to boot with a 403 — loud, immediate, and obvious.

### 2.3 The capability verbs

| Capability | What it lets the token do | KV v2 example |
|---|---|---|
| `read` | Read the value at the path | `bao kv get ai/platform/llm/gemini` |
| `list` | List the **child** names of a path | `bao kv list ai/platform/llm` |
| `create` | Create a new key (write where none exists) | First `bao kv put` of a secret |
| `update` | Overwrite an existing key | Rotating the Gemini key |
| `delete` | Delete (in KV v2, a *soft* delete) | `bao kv delete` |
| `patch` | Partially update a key | Patch one field of a secret |
| `scan` | Recursively list a subtree | `bao scan` |
| `sudo` | Perform privileged *vault* operations | Seal, write policies, enable mounts |
| `deny` | Explicitly refuse, overriding every other grant | Emergency containment |

Two of these deserve special attention right now.

**`list` is not a superset of `read`.** `read` on `a/b/c` does **not** give you
`list` on `a/b`. We prove this in §12.

**`sudo` is not "more permissions on the same path".** It is a different axis:
"are you allowed to change the *system* rather than the *data*". We prove this
in §7.

> **If you find a tutorial saying X:** *it is describing HashiCorp Vault.*
> OpenBao 2.7.1 has the same verbs, but it has **Control Groups**
> (§9), `scan`/`patch` capabilities, and a `default` policy that is larger
> than Vault's.

### 2.4 The three policies that always exist

#### `default`

Every token gets this attached automatically, unless you explicitly opt out
with `-no-default-policy` / `token_no_default_policy=true`. Here is the whole
thing, read straight off the live server with `bao policy read default`:

```hcl
# Allow tokens to look up their own properties
path "auth/token/lookup-self" {
    capabilities = ["read"]
}

# Allow tokens to renew themselves
path "auth/token/renew-self" {
    capabilities = ["update"]
}

# Allow tokens to revoke themselves
path "auth/token/revoke-self" {
    capabilities = ["update"]
}

# Allow a token to look up its own capabilities on a path
path "sys/capabilities-self" {
    capabilities = ["update"]
}

# Allow a token to look up its own entity by id or name
path "identity/entity/id/{{identity.entity.id}}" {
  capabilities = ["read"]
}
path "identity/entity/name/{{identity.entity.name}}" {
  capabilities = ["read"]
}


# Allow a token to look up its resultant ACL from all policies. This is useful
# for UIs. It is an internal path because the format may change at any time
# based on how the internal ACL features and capabilities change.
path "sys/internal/ui/resultant-acl" {
    capabilities = ["read"]
}

# Allow a token to renew a lease via lease_id in the request body; old path for
# old clients, new path for newer
path "sys/leases/renew" {
    capabilities = ["update"]
}

# Allow looking up lease properties. This requires knowing the lease ID ahead
# of time and does not divulge any sensitive information.
path "sys/leases/lookup" {
    capabilities = ["update"]
}

# Allow a token to manage its own cubbyhole
path "cubbyhole/*" {
    capabilities = ["create", "read", "update", "delete", "list"]
}

# Allow a token to wrap arbitrary values in a response-wrapping token
path "sys/wrapping/wrap" {
    capabilities = ["update"]
}

# Allow a token to look up the creation time and TTL of a given
# response-wrapping token
path "sys/wrapping/lookup" {
    capabilities = ["update"]
}

# Allow a token to unwrap a response-wrapping token. This is a convenience to
# avoid client token swapping since this is also part of the response wrapping
# policy.
path "sys/wrapping/unwrap" {
    capabilities = ["update"]
}

# Allow general purpose tools
path "sys/tools/hash" {
    capabilities = ["update"]
}
path "sys/tools/hash/*" {
    capabilities = ["update"]
}

# Allow a token to make requests to the Authorization Endpoint for OIDC providers.
path "identity/oidc/provider/+/authorize" {
    capabilities = ["read", "update"]
}
```

Read that list as a contract: *a token may manage itself, and nothing else.*

- It can look up its own properties, renew itself, revoke itself.
- It can ask "what am I allowed to do here?" (`sys/capabilities-self`).
- It can read its own identity record.
- It has a private `cubbyhole` of its own.
- It can use response wrapping (needed by Control Groups, §9).
- It can hash a value (webhook signature verification).
- It can start an OIDC flow against a provider.

**Notably absent:** anything under `ai/`, anything under `sys/mounts`,
`sys/policy`, `sys/audit`, `sys/seal`. The default policy cannot read a single
one of your secrets.

> **Production:** *Keep `default`.* It is what lets a token find out its own
> TTL so it can re-authenticate at 80% of it (Module 07 does exactly that).
> Removing it breaks self-service and, as §11 shows, breaks Control Groups
> entirely — unwrap lives in `default`.

> **Trade-off:** *Some teams strip `default` from machine tokens
> (`token_no_default_policy=true`) so that a policy mistake fails loudly
> instead of silently granting a standard path. That is defensible for
> short-lived, single-purpose jobs. It is not defensible for anything that
> needs to renew itself, use wrapping, or use a cubbyhole.* We measure exactly
> what you lose in §11.

#### `root`

The `root` policy is **not a document you can read**. It is a sentinel name.
Here is what the server says:

```
$ bao policy read root
No policy named: root
```

Exit code `2`. But the name *is* in the policy list:

```
$ bao policy list
ai-harness-service
break-glass
cg-approver
...
platform-admin
platform-operator
secret-rotation-bot
root
```

And the API will happily tell you it exists — with an empty body:

```
$ bao read sys/policy/root
Key                                      Value
---                                      -----
allow_slashes_in_identity_templates      false
allow_wildcards_in_identity_templates    false
cas_required                             false
name                                     root
rules                                    n/a
version                                  0
```

`rules: n/a` is the tell. The root policy is implemented as a short-circuit
in the ACL engine: if a token carries `root`, every path matches every
operation, and the policy engine never even looks at the other policies.

> **Production:** *`root` belongs to exactly one thing: the initial token
> printed by `bao operator init`, and to break-glass tokens you create
> deliberately, hold for minutes, and throw away.* A root token in a long-lived
> service account is the same failure as the committed `.env`, only faster.

### 2.5 Union, and the one exception

The effective capability set of a token is the **union** of its policies. A
token with `platform-operator` and `ai-harness-service` can do what either
can do.

There is exactly one exception, and it is a big one: **`deny` wins over
everything**, even over a grant in a *different* policy on the *same* token.
We prove that in §10.

---

## 3. Set up the lab you will use for the rest of this module

You need a mount, some secrets, and three machine identities. All of this is
real, and all of it is in the course's `lab/` folder.

> **A note on ports:** every transcript in this module was captured against a
> private OpenBao instance on `http://127.0.0.1:9167`. Your own lab will use a
> different port, so the URL inside every error message will read differently
> for you. The **shape** of the output is the part that matters.

### 3.1 The mount and the secrets

```bash
$ bao secrets enable -path=ai/platform kv-v2
Success! Enabled the kv-v2 secrets engine at: ai/platform/

$ bao secrets enable -path=ai/transit transit
Success! Enabled the transit secrets engine at: ai/transit/
```

```bash
$ bao kv put ai/platform/llm/gemini \
    api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" \
    model="gemini-2.5-flash" \
    owner="platform-team"

$ bao kv put ai/platform/db/postgres \
    username="meridian_app" \
    password="Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK" \
    database="meridian_ai"

$ bao kv put ai/platform/cache/redis \
    password="Yb3mQ8vT1xW6rK4pL9zD2nF7gH5jA0sC4eU" \
    endpoint="redis://redis:6379"

$ bao kv put ai/platform/oidc/keycloak \
    client_id="ai-harness" \
    client_secret="meridian-ai-harness-client-secret-rotate-me" \
    realm="meridian-ai"
```

### 3.2 The three machine identities (AppRole)

AppRole is the right mechanism for a workload: a **role_id** that is not
secret (it can be baked into the image) and a **secret_id** that is (it is
handed over at deploy time). Module 05 does AppRole in depth; here we only
need three roles.

```bash
$ bao auth enable approle
Success! Enabled approle auth method at: approle/

$ bao write auth/approle/role/ai-harness \
    token_policies="ai-harness-service" \
    token_ttl="15m" token_max_ttl="1h" \
    secret_id_ttl="1h" secret_id_num_uses=40

$ bao write auth/approle/role/data-pipeline \
    token_policies="data-pipeline-service" \
    token_ttl="10m" token_max_ttl="30m" \
    secret_id_ttl="30m" secret_id_num_uses=20

$ bao write auth/approle/role/secret-rotation-bot \
    token_policies="secret-rotation-bot" \
    token_ttl="5m" token_max_ttl="30m" \
    secret_id_ttl="15m" secret_id_num_uses=1
```

And the login round trip:

```bash
$ bao read -field=role_id auth/approle/role/ai-harness/role-id
d909c68f-9d33-55a8-746c-2bf97e513a8c

$ bao write -field=secret_id -f auth/approle/role/ai-harness/secret-id
c2937db7-ce0e-e975-09b1-f0e58856dc86

$ bao write -format=json auth/approle/login \
    role_id="d909c68f-9d33-55a8-746c-2bf97e513a8c" \
    secret_id="c2937db7-ce0e-e975-09b1-f0e58856dc86"
```

Look at what the token actually carries:

```json
{
    "request_id": "0b43d3f5-3366-eee6-ffbc-c69c44eac0a9",
    "lease_id": "",
    "lease_duration": 0,
    "renewable": false,
    "data": null,
    "warnings": null,
    "auth": {
        "client_token": "s.yIqYhfD2JTc9l2M21pPKjkln",
        "accessor": "OOZCxSCbPek8H9HprI5naJ0U",
        "policies": [
            "ai-harness-service",
            "default"
        ],
        "token_policies": [
            "ai-harness-service",
            "default"
        ],
        "identity_policies": null,
        "metadata": {
            "role_name": "ai-harness"
        },
        "orphan": true,
        "entity_id": "4a092d88-09f4-9623-4745-b009608d64ba",
        "lease_duration": 900,
        "renewable": true,
        "mfa_requirement": null
    }
}
```

The `policies` array is the whole authorization story for this credential. Ask
the server for it on its own and you get a plain YAML list:

```
$ bao write -field=policies -format=yaml auth/token/lookup token="s.yIqYhfD2JTc9l2M21pPKjkln"
- ai-harness-service
- default
```

Note that `default` was added automatically. `lease_duration: 900` is the 15
minutes the AppRole role asked for, and `renewable: true` means the token can
extend itself up to `token_max_ttl`.

> **CLI gotcha:** `bao write -field=secret_id -f auth/approle/role/.../secret-id`
> — the flag must come **before** the path. Put it after and the flag is
> silently dropped:
>
> ```
> $ bao write auth/approle/role/ai-harness/secret-id -field=secret_id
> Command flags must be provided before positional arguments. The following arguments will not be parsed as flags: [-field=secret_id]
> WARNING! The following warnings were returned from OpenBao:
>
>   * Endpoint ignored these unrecognized parameters: [-field]
>
> Key                   Value
> ---                   -----
> secret_id             8c7df5c0-93e7-7127-f98f-804c4a250c8f
> secret_id_accessor    82009f8b-bc56-57ea-c8c3-18ed317ab232
> secret_id_num_uses    40
> secret_id_ttl         1h
> ```
>
> Note what did **not** happen: the command exited **0** and still printed the
> secret. The flag was not "undefined" — it was ignored, and the server
> answered with a warning. If you pipe this into a script that expects one
> line, you get a full secret-id table instead, and no error to tell you why.
> This is the nastier of the two argument-order bugs: the first one fails
> loudly, this one fails quietly.

> **CLI gotcha:** `bao write auth/approle/role/ai-harness-nodefault ...` — a
> hyphen in a *positional* is fine, but a second bare word is not. Writing
> `bao write auth/approle/role/ai-harness nodefault ...` gives you
> `Failed to parse K=V data: invalid key/value pair "nodefault": format must be key=value`.

---

## 4. The five Meridian AI policies

They live in `lab/policies/*.hcl` in the course repo. Apply them all with:

```bash
$ for p in ai-harness-service data-pipeline-service secret-rotation-bot \
           platform-operator platform-admin; do
    bao policy write "$p" - < "lab/policies/$p.hcl"
  done
Success! Uploaded policy: ai-harness-service
Success! Uploaded policy: data-pipeline-service
Success! Uploaded policy: secret-rotation-bot
Success! Uploaded policy: platform-operator
Success! Uploaded policy: platform-admin
```

### 4.1 `ai-harness-service` — the FastAPI app

```hcl
path "ai/platform/data/llm/gemini" {
  capabilities = ["read"]
}

path "ai/platform/metadata/llm/gemini" {
  capabilities = ["read"]
}
```

Two paths, one capability each. The app knows the exact address of the one
secret it needs; it never has to go looking.

Notice what is **not** here:

- no `list` — the app cannot discover what else exists on the platform;
- no `create`/`update`/`delete` — the app cannot corrupt a secret;
- no `ai/platform/data/db/*` — the app cannot read the database password;
- no `sys/*` — the app cannot even see which mounts exist.

The `metadata/` line is not redundant. KV v2 splits every secret into a data
layer and a metadata layer, and they are **two different API paths**. Grant
only `data/` and your app can read the secret but not its version history.
Grant only `metadata/` and your app sees version numbers with no secret
values.

> **Production:** *The app should not need `metadata/` either. If it does, that
> usually means the app is caching and needs to know whether the value
> changed. OpenBao tokens expire in 15 minutes; a 15-minute cache is fine.*

### 4.2 `data-pipeline-service` — the ETL job

```hcl
path "ai/platform/data/db/postgres" {
  capabilities = ["read"]
}

path "ai/platform/data/cache/redis" {
  capabilities = ["read"]
}

path "ai/platform/metadata/db/postgres" {
  capabilities = ["read"]
}
```

Same shape: read-only, two secrets, no discovery, no writes.

### 4.3 `secret-rotation-bot` — the only writer

```hcl
path "ai/platform/data/llm/*" {
  capabilities = ["create", "update", "read", "delete"]
}

path "ai/platform/metadata/llm/*" {
  capabilities = ["read", "update"]
}

path "ai/platform/data/db/*" {
  capabilities = ["create", "update", "read", "delete"]
}

path "ai/platform/metadata/db/*" {
  capabilities = ["read", "update"]
}
```

This is the only identity in Meridian AI permitted to write a secret. And
there is a gap hiding in plain sight, which the enforcement matrix in §12
finds for us: **the Redis password is not in this policy.** The bot can rotate
the Gemini key and the Postgres password, but not `ai/platform/data/cache/redis`.
Either that is deliberate (a human rotates Redis by hand) or it is a bug. A
matrix that only checks what you expect it to check will never tell you which.

### 4.4 `platform-operator` — the human who looks

```hcl
path "ai/platform/data/*" {
  capabilities = ["read", "list"]
}

path "ai/platform/metadata/*" {
  capabilities = ["read", "list"]
}

path "sys/audit" {
  capabilities = ["read"]
}

path "sys/policy" {
  capabilities = ["read", "list"]
}
```

Humans get `list` so they can browse. They do **not** get write. Rotation
stays with the bot and the security team. In Module 05 this policy rides on an
OIDC login from Keycloak.

### 4.5 `platform-admin` — the human who administers

```hcl
path "ai/platform/data/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "ai/platform/metadata/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "ai/transit/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "sys/audit" {
  capabilities = ["read", "list"]
}

path "sys/mounts" {
  capabilities = ["read", "list"]
}

path "sys/auth" {
  capabilities = ["read", "list"]
}

path "sys/policy" {
  capabilities = ["read", "list"]
}

path "sys/capabilities-self" {
  capabilities = ["update"]
}
```

Read this policy as the answer to "what can an admin do that an operator
cannot?" — write secrets, use Transit, look at the audit devices, see the
mounts and auth methods, and read the policy list.

And read it as the answer to "what can an admin **not** do?" — **seal the
vault, generate a root token, author a policy, or mount an engine.** Those
need `sudo`, and this policy deliberately omits it. §7 is entirely about that
decision.

---

## 5. The read/write separation pattern

This is, in my opinion, the most important pattern in the whole module, and
it is worth stating plainly:

> **The application reads. The job writes. A human breaks glass.**

Look at what that buys you:

| Threat | Without separation | With separation |
|---|---|---|
| AI harness is compromised | Attacker reads Gemini key **and** can overwrite it — the app now serves an attacker's key or a dead one | Attacker reads the Gemini key. They cannot corrupt it, and you can rotate it out from under them |
| Rotation bot is compromised | Same problem, plus it can write *every* secret | Bot can only rotate what it rotates; `destroy` is unreachable (§12.4) |
| Operator laptop is stolen | Attacker can silently replace the Postgres password and exfiltrate everything | Attacker can read. Every write they attempt is an audit-log line, and the password itself is unchanged until you rotate it |

The asymmetry is the point: **exfiltration is loud and detectable;
corruption is silent.** A read-only compromise is a ticket. A write-capable
compromise is an incident. You want the compromise to be a ticket.

> **Production:** *Ask, for every policy line, "could this identity corrupt
> data or only observe it?" If the answer is "corrupt", make sure there is a
> reason that is stronger than "it was convenient".*

---

## 6. Path patterns, wildcards, and the escalation vector

### 6.1 Exact paths

```hcl
path "ai/platform/data/llm/gemini" {
  capabilities = ["read"]
}
```

An exact path matches **only** that path. It does not match anything below it.

### 6.2 The `*` wildcard is bigger than you think

This is the single most common mistake in hand-written OpenBao policies, so
we measured it rather than guessing. Here is a test policy:

```hcl
path "ai/platform/data/llm/*" {
  capabilities = ["read"]
}
path "ai/platform/data/db/postgres" {
  capabilities = ["read"]
}
path "ai/platform/data/llm/gemini*" {
  capabilities = ["read"]
}
```

And here is what each path actually matches, checked with
`bao token capabilities` against a token carrying that policy:

```
ai/platform/data/llm/gemini                   read
ai/platform/data/llm/gemini-backup-2024       read
ai/platform/data/llm                          deny
ai/platform/data/llm/gemini/sub               read
ai/platform/data/llm/sub/gemini               read
ai/platform/data/db/postgres                  read
ai/platform/data/db/postgres/password         deny
```

Read those seven lines three times. They teach you:

1. **`ai/platform/data/llm/*` matches `ai/platform/data/llm/gemini/sub` and
   `ai/platform/data/llm/sub/gemini`.** The `*` matches **any characters,
   including `/`**. It is *not* "one folder level". People write
   `path "ai/platform/data/*"` expecting it to mean "everything directly under
   data" — it actually means "everything under data, recursively, forever".
2. **`ai/platform/data/llm/*` does not match `ai/platform/data/llm` itself.**
   The trailing `*` needs something after the slash.
3. **`ai/platform/data/llm/gemini*` matches `gemini-backup-2024`.** This is
   the privilege-escalation vector.
4. **An exact path does not cover its children.**
   `ai/platform/data/db/postgres` does not grant
   `ai/platform/data/db/postgres/password`.

Point 3 deserves its own paragraph, because it is the one that will actually
bite you.

> **Wildcards are a privilege-escalation vector.** A policy that grants
> `ai/platform/data/llm/*` grants read on `llm/gemini` — and on
> `llm/gemini-backup-2024` if *someone* creates one. If the answer to
> "is there a path under this prefix that a human might not want this
> identity to read?" is even slightly unclear, use exact paths.

Point 3's cousin: **`*` at the end of a name is a glob, and globs are
prefixes.** `path "ai/platform/data/llm/gemini*"` looks like it targets one
secret and actually targets every secret whose name starts with `gemini`. If
you want exactly one secret, write exactly one secret.

### 6.3 KV v2's two-layer trap

A policy that grants `ai/platform/data/llm/gemini` does **not** grant
`ai/platform/metadata/llm/gemini`. They are different API paths and they need
different lines. Forgetting the metadata line is the most common KV v2 policy
bug, and the symptom is confusing: the secret reads fine, but the app cannot
see the version number.

---

## 7. `sudo` — the break-glass switch

### 7.1 What `sudo` actually gates

`sudo` is a separate capability from `read`/`write`. It means "you may
administer the vault itself, not just the data in it".

I tested this properly: I took the `platform-admin` policy, and separately
built a lab-only `break-glass` policy that is *identical* except that it adds
`sudo` to the `sys/` paths. Then I ran the same operations under both.

**Without `sudo` — `platform-admin` token:**

```
$ bao operator seal
Error sealing: Error making API request.

URL: PUT http://127.0.0.1:9167/v1/sys/seal
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

```
$ bao policy write probe-policy - <<'EOF'
path "ai/platform/data/*" { capabilities = ["read"] }
EOF
Error uploading policy: Error making API request.

URL: PUT http://127.0.0.1:9167/v1/sys/policies/acl/probe-policy
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

```
$ bao secrets enable -path=ai/probe kv-v2
Error enabling: Error making API request.

URL: POST http://127.0.0.1:9167/v1/sys/mounts/ai/probe
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

```
$ bao auth enable userpass
Error enabling userpass auth: Error making API request.

URL: POST http://127.0.0.1:9167/v1/sys/auth/userpass
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

```
$ bao audit enable file file_path=/tmp/audit.log
Error enabling audit device: Error making API request.

URL: PUT http://127.0.0.1:9167/v1/sys/audit/file
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

```
$ bao operator generate-root -init -otp="ABCDEFGHIJKLMNOPQRSTUVWXYZ"
Error initializing root generation: Error making API request.

URL: PUT http://127.0.0.1:9167/v1/sys/generate-root-token/attempt
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

```
$ bao write sys/tools/random bytes=16
Error writing data to sys/tools/random: Error making API request.

URL: PUT http://127.0.0.1:9167/v1/sys/tools/random
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

**With `sudo` — the break-glass token:**

```
$ bao write sys/tools/random bytes=16
Key             Value
---             -----
random_bytes    NQekuf33ZIvJR0ypTo7eLQ==
```

```
$ bao policy write probe-policy - <<'EOF'
path "ai/platform/data/*" { capabilities = ["read"] }
EOF
Success! Uploaded policy: probe-policy
```

```
$ bao secrets enable -path=ai/probe kv-v2
Success! Enabled the kv-v2 secrets engine at: ai/probe/
```

```
$ bao auth enable userpass
Success! Enabled userpass auth method at: userpass/
```

```
$ bao operator generate-root -init -otp="ABCDEFGHIJKLMNOPQRSTUVWXYZ"
Nonce         16977639-2e3e-1f92-4ae2-7ec8d9cbd4f4
Started       true
Progress      0/2
Complete      false
OTP Length    26
```

**Same operations. Same paths. Same policy apart from one word.** That is the
definition of "the `sudo` capability is the gate".

Here is the summary table, built from those two runs:

| Operation | Endpoint | Needs `sudo`? | Without `sudo` |
|---|---|---|---|
| Seal the vault | `PUT sys/seal` | ✅ | 403 |
| Unseal the vault | `PUT sys/unseal` | ❌ — it needs an unseal **share**, not `sudo` | n/a — special unauthenticated path (§7.3) |
| Write a policy | `PUT sys/policies/acl/<name>` | ✅ | 403 |
| Delete a policy | `DELETE sys/policies/acl/<name>` | ✅ | 403 |
| Enable a secrets engine | `POST sys/mounts/<path>` | ✅ | 403 |
| Enable an auth method | `POST sys/auth/<type>` | ✅ | 403 |
| Enable an audit device | `PUT sys/audit/<type>` | ✅ | 403 (400 in 2.7 — see below) |
| Generate a root token | `PUT sys/generate-root-token/attempt` | ✅ | 403 |
| Generate random bytes | `PUT sys/tools/random` | ✅ | 403 |
| Inspect another token's capabilities | `POST sys/capabilities` | ✅ | 403 |
| Read secrets | `GET ai/platform/data/...` | ❌ | depends on your policy |
| List secrets | `GET .../metadata/...?list=true` | ❌ | depends on your policy |

> **One row in that table is not about `sudo` at all.** `sys/unseal` is a
> special path: it is not governed by the ACL system, and a request carrying
> **no token at all** is accepted as long as it carries a valid Shamir share.
> Verified on the live server — the same `platform-admin` token with no `sudo`
> submitted an unseal key, the server answered `progress 1`, and it *counted
> the share*:
>
> ```
> $ bao write sys/unseal key=<share>
> Key              Value
> ---              -----
> commit_date      2026-10-01T15:32:54Z
> initialized      true
> migration        false
> n                3
> nonce            4bce2c95-4ebf-1ffd-5821-3f0339cc6cdb
> progress         1
> recovery_seal    false
> sealed           true
> storage_type     pebbledb
> t                2
> type             shamir
> version          2.7.1
> ```
>
> So: **sealing is gated by `sudo`; unsealing is gated by the unseal quorum,
> not by a capability.** A token with `sudo` on `sys/seal` can lock the
> company out of its own secrets, and no token — root or not — can undo that
> without two of three Shamir shares. §7.3 shows the whole cycle.

> **⚠️ Changed in 2.7:** *Audit devices can no longer be enabled through the
> API at all.* With `sudo` granted, the request now fails one layer deeper:
>
> ```
> $ bao audit enable file file_path=/tmp/audit.log
> Error enabling audit device: Error making API request.
>
> URL: PUT http://127.0.0.1:9167/v1/sys/audit/file
> Code: 400. Errors:
>
> * cannot enable audit device via API; use declarative, config-based audit device management instead
> ```
>
> A 400 instead of a 403 is the proof that `sudo` let the request through and
> the *2.7 policy change* stopped it. Audit devices are now declared in the
> server config file. Module 09 covers that.

### 7.2 The path trap: `sys/policy` vs `sys/policies/acl`

This one cost me real time during this module, so you get it in full.

`sys/policy` and `sys/policies/acl` are **two different paths** that do
overlapping things:

| Path | What it does | Who calls it |
|---|---|---|
| `sys/policy` | List policy names | `bao list sys/policy` |
| `sys/policy/<name>` | Read one policy's rules | `bao read sys/policy/<name>` |
| `sys/policies/acl` | List policy names | `bao policy list` |
| `sys/policies/acl/<name>` | Read / write / delete one ACL policy | `bao policy read <name>`, `bao policy write <name>` |

The CLI uses `sys/policies/acl`. The `platform-admin` policy grants
`sys/policy` — so the admin can list the policy *names* and cannot read or
write a single policy *body*:

```
$ bao list sys/policy
Keys
----
ai-harness-service
break-glass
...
secret-rotation-bot
wildcard-lab
wrapping-lab
```

```
$ bao read sys/policy/ai-harness-service
Error reading sys/policy/ai-harness-service: Error making API request.

URL: GET http://127.0.0.1:9167/v1/sys/policy/ai-harness-service
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

```
$ bao policy read ai-harness-service
Error reading policy named ai-harness-service: Error making API request.

URL: GET http://127.0.0.1:9167/v1/sys/policies/acl/ai-harness-service
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

The capability simulator tells you the whole story at once:

```
sys/policy                                 list, read
sys/policy/ai-harness-service              deny
sys/policies/acl                           deny
sys/policies/acl/ai-harness-service        deny
sys/policy/*                               deny
```

**This is a real gap in the course's `platform-admin` policy**, found by the
matrix, and I am leaving the lab file untouched so the finding stays visible.
The fix is three lines:

```hcl
path "sys/policy/*" {
  capabilities = ["read"]
}

path "sys/policies/acl/*" {
  capabilities = ["read", "list", "sudo"]
}
```

> **Production:** *Always check the path in the error message, not the path in
> your policy.* The 403 always tells you the exact URL the request went to.
> Half an hour of guessing is usually thirty seconds of reading the error.

### 7.3 Sealing the vault with `sudo` — the real thing

`sudo` on `sys/seal` lets a non-root token seal the cluster. Here is the whole
cycle on the live server:

```
$ bao operator seal
Success! Vault is sealed.
```

```
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

Unsealing needs **no token at all** — only the unseal shares:

```
$ bao operator unseal "$(cat unseal-key-1)"
Key                Value
---                -----
Seal Type          shamir
Initialized        true
Sealed             true
Total Shares       3
Threshold          2
Unseal Progress    1/2
Unseal Nonce       c376e89b-5f25-5c94-549e-51d33d67e4e2
Version            2.7.1
Commit Date        2026-10-01T15:32:54Z
Storage Type       pebbledb
HA Enabled         false
```

```
$ bao operator unseal "$(cat unseal-key-2)"
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
Cluster Name    vault-cluster-f44c9bfd
Cluster ID      0478c132-902b-5e1b-562f-75a53f680c16
HA Enabled      false
```

One detail worth noticing, because people get it wrong: **the tokens kept
working across the seal/unseal cycle.** Sealing destroys the in-memory barrier
key; unsealing restores the *same* barrier key from the stored, encrypted root
key. So a seal is not a session kill switch. (Revoking a token is — and
`sys/revoke*` is gone in 2.7; see Module 04 for what replaced it.)

### 7.4 The security property you get

Put §7.1 and §7.3 together and you get this:

> **No single human session can unilaterally lock the company out of its own
> secrets.**

- A token with `sudo` on `sys/seal` can seal the vault. But unsealing needs
  **two of three Shamir shares**, which are physically split between people
  and stored offline. Nobody has all of them.
- A token with `sudo` can generate a root token — but `generate-root` also
  needs the unseal quorum to finish. (Module 01 has the full four-step flow.)
- A token *without* `sudo` cannot do any of it, no matter how many secrets it
  can read.

That is the whole point of `sudo`. It is not "more permissions". It is a
**deliberate, separate, auditable act**.

> **Production:** *Keep `sudo` off every long-lived credential, including
> human ones. When a human genuinely needs to break glass, mint a
> `sudo`-capable token with a 15-minute TTL, use it, and let it expire. Do not
> make the emergency path a permanent capability.*

---

## 8. `deny` — and why you almost never need it

`deny` is a capability like any other, and it **overrides every other grant on
the same token**, including grants in a different policy. Verified:

```hcl
# deny-lab
path "ai/platform/data/*" {
  capabilities = ["read", "list"]
}

path "ai/platform/data/db/postgres" {
  capabilities = ["deny"]
}
```

```
$ bao token capabilities ai/platform/data/llm/gemini
list, read
$ bao token capabilities ai/platform/data/db/postgres
deny
$ bao token capabilities ai/platform/data/cache/redis
list, read
```

```
$ bao kv get ai/platform/db/postgres
Error reading ai/platform/data/db/postgres: Error making API request.

URL: GET http://127.0.0.1:9167/v1/ai/platform/data/db/postgres
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

Now the interesting part. Put a *second* policy on the same token that grants
`read` on the very path the first one denies:

```hcl
# grant-db
path "ai/platform/data/db/postgres" {
  capabilities = ["read"]
}
```

```
$ bao token capabilities ai/platform/data/db/postgres
deny
```

```
$ bao kv get ai/platform/db/postgres
Error reading ai/platform/data/db/postgres: Error making API request.

URL: GET http://127.0.0.1:9167/v1/ai/platform/data/db/postgres
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

`deny` beat `read` across policy boundaries. That is stronger than "the union
of grants" and it is the one place where union is not the rule.

> **When to use `deny`:**
> - A path that must never be read, even by an identity with a broad grant.
> - Emergency containment: "disable access to the production key right now"
>   without editing every policy that touches it.
> - A deliberate carve-out inside a policy that is mostly a broad grant.
>
> **When not to use it:** *as a substitute for not granting the thing in the
> first place.* A `deny` is a patch over an over-broad grant. It is also a
> trap: the next person adds another broad policy, forgets the `deny`, and
> now you have two policies fighting. `deny` also has a cost — it can silently
> break a legitimate path that another policy needed.

---

## 9. Control Groups — two-person approval (new in 2.7)

### 9.1 What the feature is

> **A Control Group lets a policy say: "this read is allowed, but not until a
> second person approves it."**

*Why it exists:* the weakest point of least-privilege is the moment a
legitimate identity reads a legitimate secret. A compromised admin session
reading the root of your PKI is *allowed* by every policy you wrote. Control
Groups move that decision out of one session and into two.

*What it is not:* it is not a role assignment, and it is not a second factor.
It is a **runtime gate on a specific request**.

### 9.2 The stanza

OpenBao 2.7.1 accepts a `control_group` block inside a `path` block. The
syntax is not documented anywhere I could find, so I recovered it by probing
the live server's parser until the errors stopped. Here is the working policy:

```hcl
path "ai/platform/data/db/postgres" {
  capabilities = ["read"]
  control_group {
    ttl       = "5m"
    self_auth_allowed = false
    factor "db-approver" {
      controlled_capabilities = ["read"]
      identity {
        group_names = ["platform-admin"]
        approvals   = 1
      }
    }
  }
}
```

If you want to see how this was recovered, the parser tells you its own
vocabulary. These are the real error messages, in the order I hit them:

```
* failed to parse policy: path "ai/platform/data/db/postgres": error handling control_group: 1 error occurred:
	* invalid key "required_approvals" on line 4
```

```
* failed to parse policy: path "ai/platform/data/db/postgres": error handling control_group: 1 error occurred:
	* requires at least one factor but had none
```

```
* failed to parse policy: path "ai/platform/data/db/postgres": error handling control_group: 1 error occurred:
	* error handling control_group factor: 1 error occurred:
	* path control_group factor: require name key
```

```
* failed to parse policy: path "ai/platform/data/db/postgres": error handling control_group: 1 error occurred:
	* factor 0: missing controlled capabilities
```

```
* failed to parse policy: path "ai/platform/data/db/postgres": error handling control_group: 1 error occurred:
	* factor 0: missing required approvals
```

```
* failed to parse policy: path "ai/platform/data/db/postgres": error handling control_group: 1 error occurred:
	* factor 0: missing approving groups
```

So the shape of the stanza is:

| Key | Where | Meaning |
|---|---|---|
| `ttl` | `control_group` | How long an approval stays valid. Also becomes the wrapping-token TTL. |
| `self_auth_allowed` | `control_group` | May the requester approve their own request? Default `false`. |
| `factor "<name>"` | `control_group` | One approval requirement. May be repeated. |
| `controlled_capabilities` | `factor` | Which operations are gated. Empty = all of them. |
| `identity { group_names = [...] }` | `factor` | Which identity groups may approve. |
| `approvals` | `identity` | How many approvals from that group are needed. |

### 9.3 The full flow, verified end to end

First, the identity plumbing. The approver must be a member of a group whose
*name* matches `group_names`:

```bash
$ bao write identity/group name=platform-admin policies="cg-approver"
Key     Value
---     -----
id      b3495330-4f13-a633-07de-f9f3564cc707
name    platform-admin
```

```bash
$ bao write identity/entity name=aisha.rahman
Key        Value
---        -----
aliases    <nil>
id         c2a6e12a-d42f-8dba-8cc9-eb0af2419d3c
name       aisha.rahman
```

```bash
$ bao write identity/entity-alias name=aisha.rahman \
    canonical_id=c2a6e12a-d42f-8dba-8cc9-eb0af2419d3c \
    mount_accessor=auth_token_1fe1dd5c
Key             Value
---             -----
canonical_id    c2a6e12a-d42f-8dba-8cc9-eb0af2419d3c
id              34f6400e-c0df-8219-2cbd-377ceb56fecf
```

```bash
$ bao write identity/group/id/b3495330-4f13-a633-07de-f9f3564cc707 \
    member_entity_ids=c2a6e12a-d42f-8dba-8cc9-eb0af2419d3c
Success! Data written to: identity/group/id/b3495330-4f13-a633-07de-f9f3564cc707
```

The approver's policy is tiny — it only needs the two control-group endpoints:

```hcl
# cg-approver
path "sys/control-group/request" {
  capabilities = ["update"]
}

path "sys/control-group/authorize" {
  capabilities = ["update"]
}
```

Now the requester. `db-custodian` is an AppRole whose policy is the
Control-Group-governed path from §9.2.

**Step 1 — the requester asks for the secret. They do not get it.**

```
$ bao kv get -format=json ai/platform/db/postgres
{
  "request_id": "",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": null,
  "warnings": null,
  "wrap_info": {
    "token": "s.Ma90wVHAFJrvrXk2X9cDty9e",
    "accessor": "TeadCOYNLtTWc1Hf2ibmR0R8",
    "ttl": 300,
    "creation_time": "2026-10-21T16:39:40.418612803Z",
    "creation_path": "ai/platform/data/db/postgres",
    "wrapped_accessor": ""
  }
}
```

`"data": null` — **the secret was not returned.** Instead the server handed
back a *wrapping token* with a 300-second (5 minute) TTL, which is exactly
the `ttl = "5m"` from the policy. The human-readable form is clearer:

```
$ bao kv get ai/platform/db/postgres
Key                              Value
---                              -----
wrapping_token:                  s.nwouupu4wep41C6h6RP2zqaC
wrapping_accessor:               AQoNxjiZun7G7VgUG6BoO4uQ
wrapping_token_ttl:              5m
wrapping_token_creation_time:    2026-10-21 16:39:40.537404466 +0000 UTC
wrapping_token_creation_path:    ai/platform/data/db/postgres
```

**Step 2 — the approver inspects the pending request.**

```
$ bao write -format=json sys/control-group/request accessor=AQoNxjiZun7G7VgUG6BoO4uQ
{
  "request_id": "401574e6-49e2-0de1-07d1-c1d874b013b4",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": {
    "approved": false,
    "authorizations": [],
    "request_data": null,
    "request_entity": {
      "ID": "904c2804-2c29-8d34-776c-736c588c4f5d",
      "aliases": [
        {
          "ID": "00c7d0d3-8c68-1b69-f393-bc6daeacfd46",
          "metadata": {
            "role_name": "db-custodian"
          },
          "mount_accessor": "auth_approle_42c6214c",
          "mount_type": "approle",
          "name": "f59480ec-555c-de37-d0b1-1a8136846f7f",
          "namespace_id": "root"
        }
      ],
      "name": "entity_697a9d9f.root",
      "namespace_id": "root"
    },
    "request_operation": "read",
    "request_path": "ai/platform/data/db/postgres"
  },
  "warnings": null
}
```

The approver can see **what** is being requested, by **whom**, and on **which
path** — without seeing the secret. That is a property worth having: the
approver approves an *action*, not a *value*.

**Step 3 — the approver approves.**

```
$ bao write sys/control-group/authorize accessor=AQoNxjiZun7G7VgUG6BoO4uQ
Key         Value
---         -----
approved    true
```

```
$ bao write -format=json sys/control-group/request accessor=AQoNxjiZun7G7VgUG6BoO4uQ
{
  "request_id": "890e95ca-0dbc-0dc8-f0e5-07c93318cb8a",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": {
    "approved": true,
    "authorizations": [
      {
        "entity_id": "c2a6e12a-d42f-8dba-8cc9-eb0af2419d3c",
        "entity_name": "token"
      }
    ],
    "request_data": null,
    "request_entity": {
      "ID": "904c2804-2c29-8d34-776c-736c588c4f5d",
      "aliases": [
        {
          "ID": "00c7d0d3-8c68-1b69-f393-bc6daeacfd46",
          "metadata": {
            "role_name": "db-custodian"
          },
          "mount_accessor": "auth_approle_42c6214c",
          "mount_type": "approle",
          "name": "f59480ec-555c-de37-d0b1-1a8136846f7f",
          "namespace_id": "root"
        }
      ],
      "name": "entity_697a9d9f.root",
      "namespace_id": "root"
    },
    "request_operation": "read",
    "request_path": "ai/platform/data/db/postgres"
  },
  "warnings": null
}
```

**Step 4 — the requester unwraps, and now they get the secret.**

```
$ bao unwrap -format=json s.Ma90wVHAFJrvrXk2X9cDty9e
{
  "request_id": "3f9ab993-b5ef-7262-60d8-ed9c188948a5",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": {
    "data": {
      "database": "meridian_ai",
      "password": "Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK",
      "username": "meridian_app"
    },
    "metadata": {
      "created_time": "2026-10-21T16:35:00.847213742Z",
      "custom_metadata": null,
      "deletion_time": "",
      "destroyed": false,
      "version": 2
    }
  },
  "warnings": null
}
```

**And if the requester tries to unwrap before approval:**

```
$ bao unwrap s.VC5b1vtU0aSKFqcpguwcALqR
Error unwrapping: Error making API request.

URL: PUT http://127.0.0.1:9167/v1/sys/wrapping/unwrap
Code: 400. Errors:

* wrapping token is not valid or does not exist
```

### 9.4 The three rules, all verified

**Rule 1 — the requester cannot approve their own request** (with
`self_auth_allowed = false`, the default):

```
$ bao write sys/control-group/authorize accessor=...
Error writing data to sys/control-group/authorize: Error making API request.

URL: PUT http://127.0.0.1:9167/v1/sys/control-group/authorize
Code: 500. Errors:

* 1 error occurred:
	* token owner cannot be approver
```

**Rule 2 — one person cannot approve twice:**

```
$ bao write sys/control-group/authorize accessor=...
Key         Value
---         -----
approved    true

$ bao write sys/control-group/authorize accessor=...
Error writing data to sys/control-group/authorize: Error making API request.

URL: PUT http://127.0.0.1:9167/v1/sys/control-group/authorize
Code: 500. Errors:

* 1 error occurred:
	* approver has already authorized
```

**Rule 3 — an approver who is not in the named group simply does not
count.** I put a second engineer (`dev.kapoor`) in a *different* group,
`meridian-engineering`, with the same approve policy but not the group named
in the factor:

```
$ bao write sys/control-group/authorize accessor=...
Key         Value
---         -----
approved    false
```

```
$ bao write -format=json sys/control-group/request accessor=...
{
  "request_id": "94d98bc3-692c-3ce0-54c1-63b2cb3307f3",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": {
    "approved": false,
    "authorizations": [],
    "request_data": null,
    "request_entity": {
      "ID": "904c2804-2c29-8d34-776c-736c588c4f5d",
      "aliases": [
        {
          "ID": "00c7d0d3-8c68-1b69-f393-bc6daeacfd46",
          "metadata": {
            "role_name": "db-custodian"
          },
          "mount_accessor": "auth_approle_42c6214c",
          "mount_type": "approle",
          "name": "f59480ec-555c-de37-d0b1-1a8136846f7f",
          "namespace_id": "root"
        }
      ],
      "name": "entity_697a9d9f.root",
      "namespace_id": "root"
    },
    "request_operation": "read",
    "request_path": "ai/platform/data/db/postgres"
  },
  "warnings": null
}
```

```
$ bao unwrap s.VC5b1vtU0aSKFqcpguwcALqR
Error unwrapping: Error making API request.

URL: PUT http://127.0.0.1:9167/v1/sys/wrapping/unwrap
Code: 400. Errors:

* wrapping token is not valid or does not exist
```

Note the difference in failure style: an unauthorised approver gets a
**successful** API call that simply does not approve. That is deliberate — it
does not tell an attacker whether their group membership is right.

### 9.5 What I could not verify

Being straight with you about the edges of this feature:

- **I could not find any documentation for the `control_group` stanza.** I
  recovered the syntax by reading the server's error messages. The behaviour
  above is verified on OpenBao 2.7.1; it may differ in a later release.
- **I did not verify multi-factor control groups** (two *different* groups each
  requiring one approval). The stanza accepts repeated `factor` blocks, but I
  only exercised a single factor.
- **I did not verify behaviour in a high-availability cluster.** A wrapped
  request is state; whether it survives a failover to another node is
  something you must test in your own HA deployment before you rely on it.
- **The GUI does not expose Control Groups.** There is no screen for "pending
  approvals" in the OpenBao 2.7.1 web UI. The flow is CLI/API only, which
  means a UI-based approval workflow needs something you build.
- **I did not verify how `identity` policies interact with `control_group`
  beyond the approver's group membership.** Module 04 covers groups in depth.

> **Production:** *Use Control Groups on the handful of paths where a single
> session should not be enough: the Transit key that encrypts customer PII,
> the PKI intermediate, the database superuser credential. Do not put it on
> the API key your service reads every 15 minutes — you will get paged every
> 15 minutes, and then you will turn it off, and then it is gone forever.*

---

## 10. Testing policies: `bao token capabilities`

### 10.1 The command

```bash
$ bao token capabilities -help
Usage: bao token capabilities [options] [TOKEN] PATH

  Fetches the capabilities of a token for a given path. If a TOKEN is provided
  as an argument, the "/sys/capabilities" endpoint and permission is used. If
  no TOKEN is provided, the "/sys/capabilities-self" endpoint and permission
  is used with the locally authenticated token.
```

Two forms:

- `bao token capabilities <path>` — asks about **the token you are using**.
  Uses `sys/capabilities-self`. Every token has this via the `default`
  policy.
- `bao token capabilities <token> <path>` — asks about **another token**.
  Uses `sys/capabilities`, which requires `sudo`.

The output is a single line: the capability list, or the word `deny`.

### 10.2 The sweep

Here is the same question asked of five different identities. Every line is
real output.

**`ai-harness-service`** (the FastAPI app):

```
ai/platform/data/llm/gemini              read
ai/platform/metadata/llm/gemini          read
ai/platform/metadata/llm                 deny
ai/platform/data/db/postgres             deny
ai/platform/data/cache/redis             deny
sys/mounts                               deny
```

**`data-pipeline-service`** (the ETL job):

```
ai/platform/data/db/postgres             read
ai/platform/data/cache/redis             read
ai/platform/data/llm/gemini              deny
ai/platform/metadata/db                  deny
```

**`secret-rotation-bot`** (the writer):

```
ai/platform/data/llm/gemini              create, delete, read, update
ai/platform/data/cache/redis             deny
ai/platform/destroy/llm/gemini           deny
ai/platform/undelete/llm/gemini          deny
ai/platform/metadata/llm/gemini          read, update
```

**`platform-operator`** (the human who looks):

```
ai/platform/data/llm/gemini              list, read
ai/platform/metadata/llm                 list, read
ai/platform/metadata/db/postgres         list, read
sys/mounts                               deny
sys/audit                                read
```

**`platform-admin`** (the human who administers):

```
ai/platform/data/llm/gemini              create, delete, list, read, update
ai/platform/metadata/llm                 create, delete, list, read, update
sys/seal                                 deny
sys/generate-root                        deny
sys/policy                               list, read
sys/policies/acl/ai-harness-service      deny
sys/audit                                list, read
sys/mounts                               list, read
sys/capabilities                         deny
sys/capabilities-self                    update
```

JSON form, if you want to script against it:

```
$ bao token capabilities -format=json ai/platform/data/llm/gemini
[
  "read"
]
```

### 10.3 The simulator is not the whole truth

One caveat, and it bit me: **the simulator only knows about policies.** Some
paths are handled by the router outside the ACL system.

```
$ bao read sys/internal/ui/mounts/ai/platform/llm/gemini
Key                        Value
---                        -----
accessor                   kv_88258895
config                     map[default_lease_ttl:0 force_no_cache:false max_lease_ttl:0]
deprecation_status         supported
description                n/a
external_entropy_access    false
local                      false
options                    map[version:2]
path                       ai/platform/
plugin_version             n/a
running_plugin_version     v2.7.1+builtin.bao
running_sha256             n/a
seal_wrap                  false
type                       kv
uuid                       da13a28f-014a-1bdf-5329-0e4c6fc063d5
```

Any authenticated token can read that, even though no policy grants it. Ask
the simulator about the same path with a non-root token (here the
`ai-harness-service` token) and it says:

```
$ bao token capabilities sys/internal/ui/mounts/ai/platform/llm/gemini
deny
```

The UI needs it to know which engine is mounted where. So when the simulator
says `deny` and the real call succeeds, the path is special-cased — not a
hole in your policy. (And the reverse: the simulator says `read` and the call
returns 403, because the *engine* rejected it on business grounds, not the
ACL.)

---

## 11. Stripping `default` — and what it costs

You can turn off the default policy for a machine identity:

```bash
$ bao write auth/approle/role/ai-harness-nodefault \
    token_policies="ai-harness-service" \
    token_no_default_policy=true \
    token_ttl="15m" secret_id_ttl="1h"
```

The service still works perfectly:

```
$ bao kv get -format=json ai/platform/llm/gemini
{
  "request_id": "7bf1a547-dd26-c5bf-20da-1c5a9c486f2a",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": {
    "data": {
      "api_key": "AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr",
      "model": "gemini-2.5-flash",
      "owner": "platform-team"
    },
    "metadata": {
      "created_time": "2026-10-21T16:44:25.594010302Z",
      "custom_metadata": null,
      "deletion_time": "",
      "destroyed": false,
      "version": 1
    }
  },
  "warnings": null
}
```

But here is exactly what you lost. The same two tokens, one with `default`
and one without, asked about the same paths:

| Path | With `default` | Without `default` |
|---|---|---|
| `auth/token/lookup-self` | read | deny |
| `auth/token/renew-self` | update | deny |
| `auth/token/revoke-self` | update | deny |
| `sys/capabilities-self` | update | deny |
| `cubbyhole/x` | create, delete, list, read, update | deny |
| `sys/wrapping/lookup` | update | deny |
| `sys/wrapping/unwrap` | update | deny |
| `sys/tools/hash` | update | deny |
| `sys/internal/ui/resultant-acl` | read | deny |
| `sys/leases/lookup` | update | deny |
| `ai/platform/data/llm/gemini` | read | read |

Look at row 7. `sys/wrapping/unwrap` is `deny` without `default` — which means
**a Control-Group-governed token could never unwrap its own approved
request.** Control Groups are built on response wrapping, and response
wrapping lives in `default`.

> **Production:** *If you use Control Groups, `default` is mandatory on the
> requester's token. If you use a cubbyhole, it is mandatory too. Decide
> per-identity, and write down why.*

---

## 12. The enforcement matrix

This is the lab exercise. It is not a table I wrote by hand — it is the
output of a script that runs a real command for every cell and records
whether the command exited 0 (ALLOW) or not (DENY).

### 12.1 The script

Save this as `matrix.sh` next to your policies and run it with `bash matrix.sh`.
It mints one token per identity through AppRole (the roles from §3.2), runs
one real command per cell, and fails the run if any cell disagrees with the
expected outcome.

```bash
#!/usr/bin/env bash
# Enforcement matrix for Module 03.
#
# Every cell below is the observed result of a real command run against a
# live OpenBao 2.7.1 server.
#
# Needs:
#   - BAO_ADDR pointing at your OpenBao (the course lab uses 127.0.0.1:8200)
#   - BAO_TOKEN set to a root token (only used to mint the three service
#     tokens below; the matrix itself runs as each service identity)
#   - the three AppRole roles from section 3.2 of the module
#       ai-harness, data-pipeline, secret-rotation-bot
#
# Run it:   ./matrix.sh              -> one summary line per cell
#           VERBOSE=1 ./matrix.sh    -> also the command and its real output
set -uo pipefail

BAO="${BAO_BIN:-bao}"

# --- mint one token per identity ------------------------------------------
# The role_id is not secret; the secret_id is handed over at deploy time and
# is single-use / short-lived (section 3.2 of the module).
login() {
  local role="$1" rid sid
  rid="$("$BAO" read -field=role_id "auth/approle/role/${role}/role-id")"
  sid="$("$BAO" write -field=secret_id -f "auth/approle/role/${role}/secret-id")"
  "$BAO" write -format=json auth/approle/login role_id="$rid" secret_id="$sid" \
    | jq -r .auth.client_token
}

declare -A TOKENS
TOKENS[ai-harness-service]="$(login ai-harness)"
TOKENS[data-pipeline-service]="$(login data-pipeline)"
TOKENS[secret-rotation-bot]="$(login secret-rotation-bot)"

PASS=0
FAIL=0

# run_case <policy> <expected> <label> <cmd...>
run_case() {
  local pol="$1" expected="$2" label="$3"; shift 3
  local out rc
  # NOTE: the `|| rc=$?` form is required. Under `set -e` a bare
  # `out=$(cmd)` aborts the whole script the first time a cell is DENIED,
  # so the remaining cells would never run.
  out=$("$@" 2>&1) || rc=$?
  rc="${rc:-0}"
  local actual="DENY"
  [ "$rc" -eq 0 ] && actual="ALLOW"
  local status="PASS"
  if [ "$actual" != "$expected" ]; then status="FAIL"; FAIL=$((FAIL+1)); else PASS=$((PASS+1)); fi
  printf '[%s] %-22s %-42s expected=%-5s actual=%-5s rc=%s\n' \
     "$status" "$pol" "$label" "$expected" "$actual" "$rc"
  if [ "${VERBOSE:-0}" = "1" ]; then
    printf '        $ %s\n' "$*"
    printf '%s\n' "$out" | sed 's/^/        | /'
  fi
}

echo
echo "================================================================"
echo " ENFORCEMENT MATRIX  (observed against live OpenBao 2.7.1)"
echo "================================================================"

echo
echo "---- ai-harness-service ----"
run_case ai-harness-service ALLOW "read ai/platform/llm/gemini" \
  env BAO_TOKEN="${TOKENS[ai-harness-service]}" "$BAO" kv get -format=json ai/platform/llm/gemini
run_case ai-harness-service DENY  "read ai/platform/db/postgres" \
  env BAO_TOKEN="${TOKENS[ai-harness-service]}" "$BAO" kv get -format=json ai/platform/db/postgres
run_case ai-harness-service DENY  "read ai/platform/cache/redis" \
  env BAO_TOKEN="${TOKENS[ai-harness-service]}" "$BAO" kv get -format=json ai/platform/cache/redis
run_case ai-harness-service DENY  "read ai/platform/oidc/keycloak" \
  env BAO_TOKEN="${TOKENS[ai-harness-service]}" "$BAO" kv get -format=json ai/platform/oidc/keycloak
run_case ai-harness-service DENY  "write ai/platform/llm/gemini" \
  env BAO_TOKEN="${TOKENS[ai-harness-service]}" "$BAO" kv put ai/platform/llm/gemini api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr"
run_case ai-harness-service DENY  "list ai/platform/llm" \
  env BAO_TOKEN="${TOKENS[ai-harness-service]}" "$BAO" kv list ai/platform/llm
run_case ai-harness-service DENY  "list ai/platform/metadata/llm" \
  env BAO_TOKEN="${TOKENS[ai-harness-service]}" "$BAO" kv list ai/platform/metadata/llm
run_case ai-harness-service DENY  "read sys/mounts" \
  env BAO_TOKEN="${TOKENS[ai-harness-service]}" "$BAO" read sys/mounts

echo
echo "---- data-pipeline-service ----"
run_case data-pipeline-service ALLOW "read ai/platform/db/postgres" \
  env BAO_TOKEN="${TOKENS[data-pipeline-service]}" "$BAO" kv get -format=json ai/platform/db/postgres
run_case data-pipeline-service ALLOW "read ai/platform/cache/redis" \
  env BAO_TOKEN="${TOKENS[data-pipeline-service]}" "$BAO" kv get -format=json ai/platform/cache/redis
run_case data-pipeline-service DENY  "read ai/platform/llm/gemini" \
  env BAO_TOKEN="${TOKENS[data-pipeline-service]}" "$BAO" kv get -format=json ai/platform/llm/gemini
run_case data-pipeline-service DENY  "read ai/platform/oidc/keycloak" \
  env BAO_TOKEN="${TOKENS[data-pipeline-service]}" "$BAO" kv get -format=json ai/platform/oidc/keycloak
run_case data-pipeline-service DENY  "write ai/platform/db/postgres" \
  env BAO_TOKEN="${TOKENS[data-pipeline-service]}" "$BAO" kv put ai/platform/db/postgres password="Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK"
run_case data-pipeline-service DENY  "list ai/platform/db" \
  env BAO_TOKEN="${TOKENS[data-pipeline-service]}" "$BAO" kv list ai/platform/db

echo
echo "---- secret-rotation-bot ----"
run_case secret-rotation-bot ALLOW "read ai/platform/llm/gemini" \
  env BAO_TOKEN="${TOKENS[secret-rotation-bot]}" "$BAO" kv get -format=json ai/platform/llm/gemini
run_case secret-rotation-bot ALLOW "write ai/platform/llm/gemini (rotate)" \
  env BAO_TOKEN="${TOKENS[secret-rotation-bot]}" "$BAO" kv put ai/platform/llm/gemini api_key="AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr" model="gemini-2.5-flash" owner="platform-team"
run_case secret-rotation-bot ALLOW "write ai/platform/db/postgres (rotate)" \
  env BAO_TOKEN="${TOKENS[secret-rotation-bot]}" "$BAO" kv put ai/platform/db/postgres username="meridian_app" password="Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK" database="meridian_ai"
run_case secret-rotation-bot DENY  "write ai/platform/cache/redis" \
  env BAO_TOKEN="${TOKENS[secret-rotation-bot]}" "$BAO" kv put ai/platform/cache/redis password="Yb3mQ8vT1xW6rK4pL9zD2nF7gH5jA0sC4eU"
run_case secret-rotation-bot DENY  "read ai/platform/oidc/keycloak" \
  env BAO_TOKEN="${TOKENS[secret-rotation-bot]}" "$BAO" kv get -format=json ai/platform/oidc/keycloak
run_case secret-rotation-bot DENY  "list ai/platform/llm" \
  env BAO_TOKEN="${TOKENS[secret-rotation-bot]}" "$BAO" kv list ai/platform/llm

echo
echo "================================================================"
printf " TOTAL: %d PASS, %d FAIL\n" "$PASS" "$FAIL"
echo "================================================================"

[ "$FAIL" -eq 0 ]
```

Three things in that script are worth understanding, because each one is a bug
I wrote first and then had to fix:

1. **`out=$("$@" 2>&1) || rc=$?`** — not `out=$("$@" 2>&1); rc=$?`. Under
   `set -e` (which the lab helper sets), a bare assignment that fails aborts
   the whole script. The first DENY cell would kill the run and every later
   cell would never be tested. The `||` makes the command a *list*, so
   errexit does not fire, and `rc` still gets the real exit status.
2. **The token has to be switched per cell.** `env BAO_TOKEN=... "$BAO" ...`
   inside the cell is what makes the matrix meaningful. A `run_case` that
   forgets this runs every cell as the same identity, and the whole matrix
   silently passes.
3. **The tokens are minted, not read from a file.** A script that expects
   `identities/*.token` files only works on the machine that made them. The
   AppRole login above is the same three-step dance §3.2 teaches, and it
   works anywhere the lab does.

### 12.2 The observed results

```
================================================================
 ENFORCEMENT MATRIX  (observed against live OpenBao 2.7.1)
================================================================

---- ai-harness-service ----
[PASS] ai-harness-service     read ai/platform/llm/gemini                expected=ALLOW actual=ALLOW rc=0
[PASS] ai-harness-service     read ai/platform/db/postgres               expected=DENY  actual=DENY  rc=2
[PASS] ai-harness-service     read ai/platform/cache/redis               expected=DENY  actual=DENY  rc=2
[PASS] ai-harness-service     read ai/platform/oidc/keycloak             expected=DENY  actual=DENY  rc=2
[PASS] ai-harness-service     write ai/platform/llm/gemini               expected=DENY  actual=DENY  rc=2
[PASS] ai-harness-service     list ai/platform/llm                       expected=DENY  actual=DENY  rc=2
[PASS] ai-harness-service     list ai/platform/metadata/llm              expected=DENY  actual=DENY  rc=2
[PASS] ai-harness-service     read sys/mounts                            expected=DENY  actual=DENY  rc=2

---- data-pipeline-service ----
[PASS] data-pipeline-service  read ai/platform/db/postgres               expected=ALLOW actual=ALLOW rc=0
[PASS] data-pipeline-service  read ai/platform/cache/redis               expected=ALLOW actual=ALLOW rc=0
[PASS] data-pipeline-service  read ai/platform/llm/gemini                expected=DENY  actual=DENY  rc=2
[PASS] data-pipeline-service  read ai/platform/oidc/keycloak             expected=DENY  actual=DENY  rc=2
[PASS] data-pipeline-service  write ai/platform/db/postgres              expected=DENY  actual=DENY  rc=2
[PASS] data-pipeline-service  list ai/platform/db                        expected=DENY  actual=DENY  rc=2

---- secret-rotation-bot ----
[PASS] secret-rotation-bot    read ai/platform/llm/gemini                expected=ALLOW actual=ALLOW rc=0
[PASS] secret-rotation-bot    write ai/platform/llm/gemini (rotate)      expected=ALLOW actual=ALLOW rc=0
[PASS] secret-rotation-bot    write ai/platform/db/postgres (rotate)     expected=ALLOW actual=ALLOW rc=0
[PASS] secret-rotation-bot    write ai/platform/cache/redis              expected=DENY  actual=DENY  rc=2
[PASS] secret-rotation-bot    read ai/platform/oidc/keycloak             expected=DENY  actual=DENY  rc=2
[PASS] secret-rotation-bot    list ai/platform/llm                       expected=DENY  actual=DENY  rc=2

================================================================
 TOTAL: 20 PASS, 0 FAIL
================================================================
```

### 12.3 Reading the matrix

**The AI harness can read the Gemini key and nothing else.** Not the database
password. Not the Redis password. Not even the *names* of other secrets.

Here is one DENY cell in full, because the error text is what you will
actually see at 3am:

```
        $ bao kv get -format=json ai/platform/db/postgres
        | Error reading ai/platform/data/db/postgres: Error making API request.
        |
        | URL: GET http://127.0.0.1:9167/v1/ai/platform/data/db/postgres
        | Code: 403. Errors:
        |
        | * 1 error occurred:
        | 	* permission denied
```

And one ALLOW cell in full:

```
        $ bao kv get -format=json ai/platform/llm/gemini
        | {
        |   "request_id": "3165cb52-8fa0-4943-4e58-fd0aff1af540",
        |   "lease_id": "",
        |   "lease_duration": 0,
        |   "renewable": false,
        |   "data": {
        |     "data": {
        |       "api_key": "AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr",
        |       "model": "gemini-2.5-flash",
        |       "owner": "platform-team"
        |     },
        |     "metadata": {
        |       "created_time": "2026-10-21T16:34:15.996198424Z",
        |       "custom_metadata": null,
        |       "deletion_time": "",
        |       "destroyed": false,
        |       "version": 1
        |     }
        |   },
        |   "warnings": null
        | }
```

### 12.4 The three things the matrix found that I did not expect

**Finding 1 — the rotation bot cannot rotate the Redis password.**
`write ai/platform/cache/redis` is DENY. The policy covers
`ai/platform/data/llm/*` and `ai/platform/data/db/*`, and Redis lives at
`ai/platform/data/cache/redis`. Either that is deliberate or it is a gap. The
matrix cannot tell you which — only that it is *not* covered.

**Finding 2 — `destroy` and `undelete` are on different API paths.** The
rotation bot *does* have the `delete` capability. So can it hard-delete a
secret? No — and the reason is a genuinely useful surprise:

```
$ bao kv destroy -versions=1 ai/platform/llm/rotator-probe
Error writing data to ai/platform/destroy/llm/rotator-probe: Error making API request.

URL: PUT http://127.0.0.1:9167/v1/ai/platform/destroy/llm/rotator-probe
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

```
$ bao kv undelete -versions=1 ai/platform/llm/rotator-probe
Error writing data to ai/platform/undelete/llm/rotator-probe: Error making API request.

URL: PUT http://127.0.0.1:9167/v1/ai/platform/undelete/llm/rotator-probe
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

KV v2 keeps hard-delete and undelete on their own mount sub-paths:
`<mount>/destroy/<key>` and `<mount>/undelete/<key>`. The soft delete on
`<mount>/data/<key>` is what the `delete` capability covers, and that one
works:

```
$ bao kv delete ai/platform/llm/rotator-probe
Success! Data deleted (if it existed) at: ai/platform/data/llm/rotator-probe
```

```
$ bao kv metadata get ai/platform/llm/rotator-probe
============ Metadata Path ============
ai/platform/metadata/llm/rotator-probe

============ Metadata =============
Key                         Value
---                         -----
cas_required                false
created_time                2026-10-21T17:04:43.63255448Z
current_metadata_version    0
current_version             1
custom_metadata             <nil>
delete_version_after        0s
max_versions                0
metadata_cas_required       false
oldest_version              0
updated_time                2026-10-21T17:04:43.63255448Z

====== Version 1 ======
Key              Value
---              -----
created_time     2026-10-21T17:04:43.63255448Z
deletion_time    2026-10-21T17:04:43.741086832Z
destroyed        false
```

`destroyed: false` — soft-deleted, recoverable, and the bot cannot make it
permanent. Exactly what the policy comment claimed, for a reason the comment
did not explain.

> **The lesson:** *the capability you grant is not the operation the CLI
> performs.* Always look at the URL in the 403. `bao kv destroy` is not
> "delete with extra steps" — it is a request to a completely different path.

> **CLI gotcha:** *OpenBao 2.7 uses `-versions=` (plural), not `-version=`.*
> `bao kv destroy -version=1` gives
> `flag provided but not defined: -version`.

**Finding 3 — the `platform-admin` policy cannot actually read policies.**
Covered in §7.2.

---

## 13. Policies as code

A policy file is HCL. It belongs in Git next to your application code, and it
should be applied by CI, not by a human remembering to paste it into a
terminal.

### 13.1 `bao policy fmt` — a linter that needs no server

OpenBao ships a formatter *and* a validator for policy files:

```
$ bao policy fmt -help
Usage: bao policy fmt [options] PATH

  Formats a local policy file to the policy specification. This command will
  overwrite the file at the given PATH with the properly-formatted policy
  file contents.
```

It rewrites the file in canonical form:

```
$ bao policy fmt lab/policies/ai-harness-service.hcl
Success! Formatted policy: lab/policies/ai-harness-service.hcl
```

(The path in that line is echoed back exactly as you typed it — relative in,
relative out.)

And it **rejects invalid policies** — with the same error messages the server
would give. Here are the four files, so you can reproduce each one exactly:

```hcl
# broken.hcl — the closing brace is missing
path "ai/platform/data/llm/gemini" {
  capabilities = ["read"]
```

```hcl
# bad-capability.hcl — "reed" is not a capability
path "ai/platform/data/llm/gemini" {
  capabilities = ["reed"]
}
```

```hcl
# bad-key.hcl — "bogus_key" is not a key of a path block
path "ai/platform/data/llm/gemini" {
  capabilities = ["read"]
  bogus_key = "x"
}
```

```hcl
# bad-control-group.hcl — "bogus" is not a key of a factor block
path "ai/platform/data/db/postgres" {
  capabilities = ["read"]
  control_group {
    ttl = "5m"
    factor "db-approver" {
      bogus = "x"
      controlled_capabilities = ["read"]
      identity {
        group_names = ["platform-admin"]
        approvals = 1
      }
    }
  }
}
```

```
$ bao policy fmt broken.hcl
failed to parse policy: At 3:2: object expected closing RBRACE got: EOF
```

```
$ bao policy fmt bad-capability.hcl
failed to parse policy: path "ai/platform/data/llm/gemini": path "ai/platform/data/llm/gemini": invalid capability "reed"
```

```
$ bao policy fmt bad-key.hcl
failed to parse policy: path "ai/platform/data/llm/gemini": 1 error occurred:
	* invalid key "bogus_key" on line 3
```

```
$ bao policy fmt bad-control-group.hcl
failed to parse policy: path "ai/platform/data/db/postgres": error handling control_group: 1 error occurred:
	* error handling control_group factor: 1 error occurred:
	* path control_group factor: invalid key "bogus" on line 6
```

And the best part — it is **entirely client-side**. Point it at an unreachable
server and it still validates:

```
$ BAO_ADDR="http://127.0.0.1:1" bao policy fmt bad-capability.hcl
failed to parse policy: path "ai/platform/data/llm/gemini": path "ai/platform/data/llm/gemini": invalid capability "reed"
```

```
$ BAO_ADDR="http://127.0.0.1:1" bao policy fmt lab/policies/ai-harness-service.hcl
Success! Formatted policy: lab/policies/ai-harness-service.hcl
```

That means your CI job needs no OpenBao instance to lint your policies.

### 13.2 The CI shape

```yaml
# .github/workflows/policies.yml
name: policy-lint
on: [push, pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install the OpenBao CLI (pinned)
        run: |
          curl -fsSL -o bao.zip \
            https://github.com/openbao/openbao/releases/download/v2.7.1/bao_2.7.1_linux_amd64.zip
          unzip -q bao.zip && sudo install -m 0755 bao /usr/local/bin/bao
      - name: Lint and format-check every policy
        run: |
          set -euo pipefail
          for f in policies/*.hcl; do
            bao policy fmt "$f"
            git diff --exit-code "$f"     # fails if fmt would change it
          done
```

> **Production:** *Pin the CLI version in CI exactly as you pin the server
> version.* A linter that changes its mind between 2.7.1 and 2.8 will fail
> your build for reasons that have nothing to do with your policy.

### 13.3 Applying policies from CI, safely

To apply a policy from CI you need a token with `sudo` on
`sys/policies/acl/*`. Do **not** give your CI job the root token. Instead:

- Give the CI job a short-lived token from an AppRole whose policy is exactly
  `sys/policies/acl/*` with `sudo` — nothing else.
- Mint it in the pipeline with a `secret_id` that is single-use and short-lived.
- Have the pipeline *print* the applied policy and diff it against Git.

### 13.4 Drift detection

The point of keeping policies in Git is that you can always tell what the
server *should* have versus what it *does* have. A nightly job:

```bash
# For every policy in Git, compare the server's copy to the file.
for f in policies/*.hcl; do
  name="$(basename "$f" .hcl)"
  remote="$(bao read -field=policy "sys/policies/acl/$name")"
  # `printf '%s\n'` — the trailing newline matters. `$( )` strips it from
  # "$remote", and `printf '%s'` does not put it back, so a byte-identical
  # policy still diffs ("\ No newline at end of file") and the job cries
  # DRIFT on every policy. A drift alarm that always fires is an alarm you
  # switch off.
  if ! diff -q <(printf '%s\n' "$remote") "$f" > /dev/null; then
    echo "DRIFT: policy '$name' differs from policies/$name.hcl"
  fi
done
```

Check it before you trust it: `diff -u policies/platform-operator.hcl <(bao read
-field=policy sys/policies/acl/platform-operator)` must print nothing and exit
0 for a policy that has not changed.

Note the endpoint: `sys/policies/acl/<name>`, **not** `sys/policy/<name>`
(§7.2). And note that `bao read -field=policy` returns the policy body
verbatim:

```
$ bao read -format=json sys/policies/acl/ai-harness-service
{
  "request_id": "b4635051-30a8-a213-f2e4-9cba51284231",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": {
    "allow_slashes_in_identity_templates": false,
    "allow_wildcards_in_identity_templates": false,
    "cas_required": false,
    "modified": "2026-10-21T16:34:17.792321793Z",
    "name": "ai-harness-service",
    "policy": "# Meridian AI - the FastAPI/LangChain AI harness service\n#\n...",
    "version": 1
  },
  "warnings": null
}
```

The `version` and `modified` fields are your receipts: a policy that changed
at 03:00 that nobody in Git explains is a question you want answered.

---

## 14. The GUI for this module

Open <http://127.0.0.1:8200/ui> and log in with a root token for the first
time (you can revoke the root token afterwards — Module 09 covers that).

| What you want | GUI path | CLI equivalent |
|---|---|---|
| See the policies that exist | **Policies → ACL Policies** | `bao policy list` |
| Read one policy's rules | **Policies → ACL Policies → (name)** | `bao policy read <name>` |
| Edit a policy | **Policies → ACL Policies → (name) → Edit policy** | `bao policy write <name> -` |
| Author a new policy | **Policies → ACL Policies → Create policy** | `bao policy write <name> -` |
| Browse the secrets a policy covers | **Secrets engines → ai/platform → llm → gemini** | `bao kv list ai/platform` |
| See the auth methods | **Access → Authentication methods** | `bao auth list` |
| See the identities and groups | **Access → Entities** / **Access → Groups** | `bao list identity/entity/name` |
| See the leases you own | **Access → Leases** | `bao list sys/leases/lookup` |

Two paths in that table do not exist in the OpenBao 2.7.1 web UI, and that is
worth knowing before you go looking for them:

- **There is no "Tokens" page.** The UI has no token list, no token detail
  view, and no "show capabilities" button. The only token UI is the user menu
  in the top-right corner (avatar): **Copy token**, **Renew token**,
  **Revoke …**, **Log out**. Everything else is CLI: `bao token list`,
  `bao token lookup`, `bao token capabilities`.
- **There is no Control Group screen.** No "pending approvals" list, no
  approve button. The whole two-person flow in §9 is CLI/API only.

The GUI's policy editor is a plain code box — CodeMirror, with no HCL syntax
highlighting, no "Format" button, and no preview of the resulting
path/capability table. It does have an **Upload file** switch, which is
genuinely handy for pushing a `.hcl` from your repo into the editor, and it
does surface the server's parse error in the error banner when you hit Save
with a bad policy. But it is still **not the place you author policy**, for
three reasons:

1. It cannot be reviewed. A policy edited in a browser has no diff, no author,
   and no commit. It is a change made in a tab.
2. It cannot be tested. The GUI has no equivalent of
   `bao token capabilities` against an *arbitrary* token.
3. It cannot express the things that matter most here. A `control_group`
   block, a `deny` override, or a `required_parameters` stanza all need raw
   HCL that the editor gives you no help with.

> **Production:** *Author in text files, review in Git, apply from CI. Use the
> GUI to *look* — it is a good inspection tool, and a bad authoring tool.*

One more GUI detail worth knowing: the permission tree the UI draws for you
is backed by `sys/internal/ui/resultant-acl`, which the `default` policy
grants to every token. That is why the UI can show you your own permission
tree without asking the server for a `sudo` answer.

```
$ bao read -format=json sys/internal/ui/resultant-acl
{
  "request_id": "b91bcb1b-8713-ad77-c98a-b2b2a2061ccd",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": {
    "exact_paths": {
      "ai/platform/data/llm/gemini": {
        "capabilities": [
          "read"
        ]
      },
      "ai/platform/metadata/llm/gemini": {
        "capabilities": [
          "read"
        ]
      },
      "auth/token/lookup-self": {
        "capabilities": [
          "read"
        ]
      },
      ...
```

This is the machine-readable form of "what can this token do" — and it is
exactly what a drift-detection tool should be comparing against.

---

## 15. Production checklist

**Token hygiene**
- [ ] No long-lived token carries `root`.
- [ ] Every token has a TTL, and the TTL is short enough to matter.
- [ ] `secret_id`s are single-use or tightly counted, and short-lived.
- [ ] The root token from `bao operator init` is not in a shell history file,
      a CI secret, or a password manager nobody reads.

**Policy hygiene**
- [ ] Every identity has its own policy, and every policy maps to one job.
- [ ] No policy grants `list` on a broad path to a machine identity.
- [ ] Write access exists on exactly one path per domain, and that path is
      owned by a scheduled job, not a service.
- [ ] `destroy` (irreversible) requires human authority.
- [ ] `deny` rules are exceptional, and each one has a comment saying why.
- [ ] `sudo` is granted to as few identities as possible, and to none of them
      long-term.
- [ ] Wildcards are replaced by explicit paths wherever the set is small and
      knowable.
- [ ] KV v2 policies cover **both** `data/` and `metadata/`.

**Operational hygiene**
- [ ] Every policy is version-controlled and applied by CI.
- [ ] Every policy is tested with `bao token capabilities` against every path
      it touches — and the matrix is in CI too.
- [ ] There is a nightly drift check between Git and the running server.
- [ ] There is a policy to *revoke* a policy: if a policy is wrong, you can
      change it without waiting for a token to expire.

**Break-glass hygiene**
- [ ] A documented, rehearsed procedure to mint a `sudo` token.
- [ ] A documented procedure to seal and unseal, with the unseal share custody
      written down.
- [ ] The break-glass path does not depend on a single person's laptop.

---

## 16. What you learned

- [ ] The authorization model: path + token + policies, with **absence of a
      grant being the deny**.
- [ ] The capability verbs: `read`, `list`, `create`, `update`, `delete`,
      `patch`, `scan`, `sudo`, `deny`.
- [ ] `read` on a path does **not** give you `list` on its parent — and I
      showed you the 403.
- [ ] What `default` actually contains in 2.7.1 (16 self-service paths and
      nothing else), and what it costs to remove it.
- [ ] That `root` is a sentinel, not a document — `bao policy read root`
      returns `No policy named: root`.
- [ ] How to write the five Meridian AI policies and how to apply them.
- [ ] The read/write separation pattern, and why it is the most important
      pattern in the module.
- [ ] That `sudo` gates seal, policy authoring, mount creation, auth
      enabling, audit enabling, root generation, `sys/tools/random` and
      cross-token capability inspection — and how to prove it.
- [ ] The `sys/policy` vs `sys/policies/acl` path trap, and that the
      `platform-admin` policy has a real gap because of it.
- [ ] That Control Groups exist in 2.7, what the `control_group` stanza
      looks like, and how the whole two-person approval flow works.
- [ ] That `deny` overrides grants from other policies on the same token.
- [ ] That `*` matches across `/`, and that `gemini*` is a prefix glob that
      will eventually match something you did not want.
- [ ] That `bao kv destroy` hits `<mount>/destroy/<key>`, not
      `<mount>/data/<key>`.
- [ ] How to test a policy with `bao token capabilities`, and the one case
      where the simulator lies (`sys/internal/ui/mounts`).
- [ ] How to lint policies in CI with `bao policy fmt`, with no server
      required.

---

## 17. What's next

You now have five identities, five policies, and a store where the AI harness
genuinely cannot read the database password. But every identity here is a
handful of HCL files and a token, and two questions are still open: *who is
this identity?* and *how long does it live?*

[Module 04 — Namespaces, Entities, Groups & Leases](../04-namespaces-entities/README.md)
answers both: namespaces give you multi-tenancy, entities give you a stable
identity that outlives its tokens, groups turn a pile of policies into
something you can assign to a person, and leases give you the lifecycle —
create, renew, expire, revoke — that turns a leaked credential from a
permanent problem into a 15-minute one.

---

## 18. Homework

1. **Write the missing policy.** The enforcement matrix found that the
   rotation bot cannot rotate the Redis password at
   `ai/platform/data/cache/redis`. Add a policy (or extend the existing one)
   that closes the gap, apply it, and prove it with `bao token capabilities`.
   Then decide: should the bot be able to rotate Redis, and if so, why?

2. **Fix `platform-admin`.** The policy in `lab/policies/platform-admin.hcl`
   grants `sys/policy` but the CLI uses `sys/policies/acl`. Write the three
   lines that make `bao policy list` and `bao policy read <name>` work for
   that identity — **without** granting `sudo` on the write path. Verify with
   `bao token capabilities sys/policies/acl/ai-harness-service`.

3. **Build your own matrix.** Write a script like the one in §12.1 but for
   `platform-operator` and `platform-admin`: for every path any policy
   mentions, assert the expected capability and fail the build on a mismatch.
   Now find a case where the operator's `list` on `ai/platform/metadata/*`
   leaks something you did not intend. (Hint: it leaks *names*.)

4. **Prove the read/write separation under attack.** Mint a token for the
   `ai-harness-service` policy. Try — with the real CLI, not `capabilities` —
   to: overwrite the Gemini key, delete it, list the platform, read the
   database password, and destroy a version. Write down the exact error for
   each. Then swap in the `secret-rotation-bot` policy and show which of those
   now succeed, and which still do not.

5. **Build a Control Group for the real thing.** Put a `control_group` on the
   Postgres credential with two factors: one requiring an approval from a
   `platform-admin` group, one from a `security-team` group. Get it working
   with two different people, and verify that one person approving both
   factors does **not** satisfy it.

6. **Write the CI job.** Add `bao policy fmt` to a GitHub Actions workflow
   that also runs the capability matrix against a throwaway OpenBao
   container, and fails the build if any assertion breaks. Pin the CLI
   version to `2.7.1`.

---

> **Production:** *A secret store is not secure because the secrets are
> encrypted. It is secure because the paths you can reach are small, the
> operations you can perform are few, and the people who can widen either set
> are named, few, and watched. Policies are how you make that true — and
> `bao token capabilities` is how you prove it stayed true.*
