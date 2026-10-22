# Module 05 — Auth Methods, MFA & OIDC with Keycloak

> **Where we are.** Modules 01–04 gave Meridian AI a running OpenBao 2.7.1, a
> KV v2 mount at `ai/platform/`, five least-privilege policies, namespaces,
> entities and groups. Everything in there is currently protected by **one
> root token** living in a file on a laptop. That is the `.env` problem all
> over again, and it is the last thing standing between a compromised
> developer laptop and every secret the company owns.
>
> This module replaces the root token with **two** mechanisms, one for each
> kind of caller: **OIDC against Keycloak** for humans (Aisha, Dev, the
> on-call engineer) and **AppRole** for machines (the `ai-harness` container,
> the `data-pipeline`, the `secret-rotation-bot`). It then adds **MFA** on top
> of the human path, because a password-only login to a secret store is a
> single-phish away from total compromise.
>
> The hardest part of this module is not the commands. It is the question
> *"how does a `secret_id` physically get into a container without becoming
> the new `.env` file?"* We answer that with three concrete patterns and
> honest trade-offs.

**Status:** Full lesson. Every output block in this module was captured from
a live OpenBao 2.7.1 server. Sections that could **not** be executed here
(Keycloak itself) are labelled **NOT VERIFIED HERE** and listed in
[§6.9](#69-verified--not-verified-here--the-honesty-table).

---

## 0. The 60-second version

| Concept | One line |
|---|---|
| **Auth method** | A mounted plugin that turns *some credential* into an OpenBao token. |
| **Auth mount** | Where a method lives, e.g. `approle/`, `oidc/`. Each gets an `accessor`. |
| **Two audiences** | Humans prove identity with **OIDC**; machines prove *possession* with **AppRole**. |
| **`role_id`** | The **non-secret** half of an AppRole identity. Safe to bake into an image. |
| **`secret_id`** | The **secret** half. Proves the caller is allowed to become that role. |
| **`secret_id_ttl`** | How long a generated `secret_id` stays usable (default: role lifetime, effectively unbounded). |
| **`secret_id_num_uses`** | How many times a `secret_id` may be redeemed. `1` = strictly one-shot. |
| **`secret_id_bound_cidrs`** | Source-IP allowlist checked **at login**. |
| **`token_bound_cidrs`** | Source-IP allowlist checked **at login AND on every request**. |
| **`token_ttl` / `token_max_ttl`** | How long the issued token lives / the ceiling it can be renewed to. |
| **`token_policies`** | The ACL policies the issued token carries. |
| **`token_no_default_policy`** | Drops the built-in `default` policy. Least privilege, but see §4.6. |
| **AppRole login** | `PUT auth/approle/login` with `role_id` + `secret_id` → a token. |
| **OIDC** | Delegate authentication to Keycloak; OpenBao only issues the token. |
| **Discovery URL** | The **issuer** URL. OpenBao appends `/.well-known/openid-configuration` itself. |
| **`bound_claims`** | "Only trust an ID token whose `groups` claim equals X." |
| **`claim_prefix`** | Namespaces a claim value into an OpenBao group name. |
| **MFA** | A second factor. TOTP via `identity/mfa/method/totp`. |
| **`mfa_require`** | **Vault-era. Silently ignored by OpenBao 2.7.1.** Use `identity/mfa/login-enforcement`. |
| **`sys/mfa/validate`** | Completes an MFA-gated login: `mfa_request_id` + `mfa_payload`. |
| **The `.env` death** | A secret in an env var is visible in `docker inspect`, `/proc/*/environ`, and every image layer. |

---

## 1. Why this matters: a secret store with one shared key

### 1.1 The six questions from Module 01, asked again

In Module 01 you wrote down six questions about the `.env` file that the
previous engineer left in Git. OpenBao only fixes them if the thing *holding*
the token is itself an authentication decision. Let's re-ask them about the
root token:

| Question | With a root token in a file | With OIDC + AppRole |
|---|---|---|
| Who can read it? | Anyone with the file | A human with a Keycloak session + MFA; a workload with a `secret_id` |
| Is it in Git history? | Yes, if you commit it | Never — tokens are minted at runtime |
| Can you rotate it? | Only by hand | `bao write auth/approle/role/…/secret-id` mints a new one in one command |
| Can you audit it? | No — file access isn't in the audit log | Every login is an audit entry with `auth.accessor`, `auth.policies`, `auth.metadata` |
| Can you scope it? | No — root is root | `token_policies=ai-harness-service` means one secret and nothing else |
| Does it reach the app at runtime? | Copied into the image | Minted at container start, held in memory only |

### 1.2 What "authenticate" means here

OpenBao has one job: **turn a credential into a token with policies
attached.** Everything else in this course is downstream of that sentence.

```
credential  --(auth method)-->  token  --(policies)-->  permissions on paths
```

- The **auth method** decides *how* the credential is presented and *what
  proves* it.
- The **token** is the bearer credential. It carries policies, a TTL, and an
  accessor for auditing.
- The **policies** (Module 03) decide what the token can do.

> **Production:** *An auth method that can only ever produce one kind of
> credential is the wrong abstraction. You want "a workload proves it is
> allowed to become role X", not "a workload knows a shared password".*

---

## 2. Two audiences, two mechanisms

### 2.1 The table that decides the whole module

|  | **Human** | **Machine** |
|---|---|---|
| Meridian AI example | Aisha Rahman, platform engineer | The `ai-harness` FastAPI container |
| Nature of the caller | Interacts, gets confused, gets phished, leaves, joins | Starts, asks for a secret, exits |
| Proof needed | Something only *they* know + something they *have* | Proof that *this deployment* is allowed to be that role |
| Credential | A Keycloak session + a TOTP code | `role_id` + `secret_id` |
| Auth method | **OIDC** (Keycloak) | **AppRole** |
| MFA | **Yes** — TOTP | No (there is nobody to hold a phone) |
| Token TTL | 1 hour, renewed while the session is alive | 15 minutes, re-minted automatically |
| Audit trail | `auth.display_name = aisha.rahman` | `auth.metadata.role_name = ai-harness-service` |
| Offboarding | Remove the Keycloak user — done | Destroy the `secret_id` accessor — done |
| Revocation | Log out of Keycloak / revoke the token | `bao write auth/token/revoke-accessor` |

### 2.2 Why using one mechanism for both is a design error

**OIDC for a service** means the service needs a Keycloak *service account*,
which means a password stored somewhere — that is the `.env` file again, now
with an OAuth token exchange bolted on. You gain nothing.

**AppRole for a human** means a human holds a `role_id` and a `secret_id`.
There is no second factor, no per-user identity, and no way to tell Aisha
apart from Dev in the audit log. Worse, a `secret_id` is designed to be
handed to a machine — a human will write it down.

> **Trade-off:** *One method for everything is simpler to operate. It is also
> how you end up with a service account that has a 90-day password and an
> admin who logs in with the same shared credential the CI job uses. The
> extra 30 minutes of setup in this module buys you a company where
> "who did this?" is always answerable.*

---

## 3. The built-in auth inventory in OpenBao 2.7.1

### 3.1 What ships in the box

Verified on the live server with `bao plugin list`:

```console
$ bao plugin list | awk 'NR<=2 || /auth/'
Name                            Type        Version
----                            ----        -------
approle                         auth        v2.7.1+builtin.bao
cert                            auth        v2.7.1+builtin.bao
jwt                             auth        v2.7.1+builtin.bao
kubernetes                      auth        v2.7.1+builtin.bao
oidc                            auth        v2.7.1+builtin.bao
userpass                        auth        v2.7.1+builtin.bao
```

Six auth methods, all built in. Meridian AI will use **two** of them:
`approle` and `oidc`.

### 3.2 What is NOT built in

Per `VERIFIED-FACTS.md` §6, these moved to the `openbao-plugins` external
plugin catalogue and are **not** available out of the box:

- `ldap` and `kerberos` **auth** methods
- `aws`, `gcp`, `azure`, `ad`, `consul`, `nomad` **secret** engines
- all KMS **seals** (`awskms`, `gcpckms`, `azurekeyvault`, `alicloudkms`,
  `ocikms`, `pkcs11`) — except `transit`, which *is* built in

> **If you find a tutorial saying "just enable LDAP auth":** *it is
> describing HashiCorp Vault, where `ldap` was built in. In OpenBao 2.7 you
> install it as an external plugin first.*

### 3.3 The first gotcha: `totp` is a *secret* engine, not an auth method

You will see `totp` in the plugin list and try to enable it as auth. It
fails:

```console
$ bao auth enable totp
Error enabling totp auth: Error making API request.

URL: POST http://127.0.0.1:9437/v1/sys/auth/totp
Code: 400. Errors:

* plugin not found in the catalog: totp
```

`totp` is a **secret engine** — it *generates* TOTP codes for keys you give
it. The thing you actually want for MFA lives in the **identity store** at
`identity/mfa/method/totp` and needs no mount at all. We use both in §7.

The correct command is:

```console
$ bao secrets enable totp
Success! Enabled the totp secrets engine at: totp/
```

---

## 4. AppRole in depth — the machine path

### 4.1 The concept

**AppRole is a two-part credential.** A role is defined once on the server.
To act as that role you must present *both* halves:

- **`role_id`** — a stable UUID identifying *the role*. **Not a secret.**
- **`secret_id`** — a high-entropy value proving *you were allowed to become
  this role right now*. **This is the secret.**

The server's rule is simple: `role_id` alone identifies a door; `secret_id`
proves you have a key that is still valid for that door.

> **What breaks if you skip it:** *If a role only needs `role_id`, then anyone
> who can reach the OpenBao API and can enumerate role IDs can become that
> role. Role IDs are not designed to be unguessable — they are identifiers,
> and they show up in audit logs, in entity aliases, and in your own
> deployment manifests.*

### 4.2 Enable the method

```console
$ bao auth enable approle
Success! Enabled approle auth method at: approle/
```

### 4.3 Write the role — every option, with a reason

```console
$ bao write auth/approle/role/ai-harness-service \
  token_policies="ai-harness-service" \
  token_no_default_policy=true \
  token_ttl=15m token_max_ttl=1h \
  secret_id_ttl=1h secret_id_num_uses=1 \
  secret_id_bound_cidrs="127.0.0.1/32" token_bound_cidrs="127.0.0.1/32"
Success! Data written to: auth/approle/role/ai-harness-service
```

Read it back — the server fills in every default for you:

```console
$ bao read auth/approle/role/ai-harness-service
Key                        Value
---                        -----
bind_secret_id             true
local_secret_ids           false
secret_id_bound_cidrs      [127.0.0.1/32]
secret_id_num_uses         1
secret_id_ttl              1h
token_bound_cidrs          [127.0.0.1]
token_explicit_max_ttl     0s
token_max_ttl              1h
token_no_default_policy    true
token_num_uses             0
token_period               0s
token_policies             [ai-harness-service]
token_strictly_bind_ip     false
token_ttl                  15m
token_type                 default
```

> **Notice:** `token_bound_cidrs` came back as `[127.0.0.1]`, not
> `[127.0.0.1/32]`. OpenBao normalises a single-host CIDR to the bare address.
> A list is still a list, so `token_bound_cidrs="10.0.0.0/8,192.168.0.0/16"`
> gives you two entries.

Here is what each option does and what it costs you:

| Option | Value here | What it does | What it costs |
|---|---|---|---|
| `token_policies` | `ai-harness-service` | Policies on the issued token. **Replaces** the default set — it is not additive with `default` unless `default` is also listed. | If you forget a policy the app gets 403s, not silent over-access. Good. |
| `token_no_default_policy` | `true` | Drops the built-in `default` policy. | See §4.6 — you also lose `lookup-self`, `renew-self`, `capabilities-self`. |
| `token_ttl` | `15m` | How long the token lives. | Too long and a leaked token is a long-lived liability. |
| `token_max_ttl` | `1h` | Ceiling on renewal. The token dies at 1h *even if* it is being used. | A long-running job that needs more must re-login. |
| `token_num_uses` | `0` | 0 = unlimited uses. Set it and the token dies after N requests. | 1-use tokens break anything that needs two calls. |
| `secret_id_ttl` | `1h` | How long a minted `secret_id` stays redeemable. | Too long and a leaked `secret_id` is redeemable for an hour. |
| `secret_id_num_uses` | `1` | How many times the `secret_id` can be redeemed. `1` = one-shot. | A crash-looping container cannot retry with the same `secret_id`. |
| `secret_id_bound_cidrs` | `127.0.0.1/32` | Source-IP allowlist, checked **at login**. | Breaks if your workload's egress IP changes. |
| `token_bound_cidrs` | `127.0.0.1/32` | Source-IP allowlist, checked **at login and on every request**. | Same. Use it when the token could be stolen and replayed elsewhere. |
| `bind_secret_id` | `true` (default) | Require a `secret_id` at login. | See §4.9 — OpenBao 2.7.1 will not let you turn it off safely. |

> **Production:** *`secret_id_num_uses=1` plus a short `secret_id_ttl` plus a
> CIDR pin is the shape you want for a workload that redeploys often. If the
> container might restart in place, use `secret_id_num_uses=0` with a short
> TTL instead — a crash loop that burns its one-shot ID on every restart
> will page you at 3am.*

### 4.4 `role_id` vs `secret_id` — the distinction that matters

```console
$ bao read auth/approle/role/ai-harness-service/role-id
Key        Value
---        -----
role_id    6b035535-fa5a-3955-772d-2c5eced94da4
```

```console
$ bao write -f auth/approle/role/ai-harness-service/secret-id
Key                   Value
---                   -----
secret_id             cf2f63ec-c8af-ff10-1905-0ad37f2a8f83
secret_id_accessor    a2dc0ad8-541b-32a0-a9f7-fbf80ef36df5
secret_id_num_uses    1
secret_id_ttl         1h
```

| | `role_id` | `secret_id` |
|---|---|---|
| Secret? | **No** | **Yes** |
| Stable? | Yes — until you delete the role | No — a new one every time you call `secret-id` |
| Where it may live | App image, `docker-compose.yml`, Kubernetes ConfigMap, public docs | CI secret store, a `0400` file, a tmpfs volume |
| In the audit log? | Yes, as the entity alias name | Never — only the `secret_id_accessor` is logged |
| Revocable individually? | No — delete the role | **Yes** — destroy the accessor (§4.10) |

> **Production:** *The `role_id` is a *routing address*, not a credential.
> Put it wherever. The `secret_id` is the credential. It must be delivered
> at deploy time, over a channel you trust, and it should expire.*

### 4.5 The full login round trip

```console
$ bao write -format=json auth/approle/login \
    role_id="6b035535-fa5a-3955-772d-2c5eced94da4" \
    secret_id="cf2f63ec-c8af-ff10-1905-0ad37f2a8f83"
{
    "request_id": "8a07b731-913d-905a-8bde-121700577036",
    "lease_id": "",
    "lease_duration": 0,
    "renewable": false,
    "data": null,
    "warnings": null,
    "auth": {
        "client_token": "s.cY7GJrI090bqupZfv1RMdF4Q",
        "accessor": "lZI4BmMQnq3FgoCknwSAoCqy",
        "policies": [
            "ai-harness-service"
        ],
        "token_policies": [
            "ai-harness-service"
        ],
        "identity_policies": null,
        "metadata": {
            "role_name": "ai-harness-service"
        },
        "orphan": true,
        "entity_id": "b9a00e52-aaca-6873-6cdc-64bc4f81d9d9",
        "lease_duration": 900,
        "renewable": true,
        "mfa_requirement": null
    }
}
```

Read that carefully — it is the whole AppRole contract:

- **`client_token`** — the bearer credential. `s.`-prefixed.
- **`accessor`** — a *non-secret* handle on the token. You can revoke by
  accessor without ever holding the token. This is what you put in an
  incident ticket.
- **`policies`** — `["ai-harness-service"]` **only**. No `default`, no
  `root`. That is `token_no_default_policy=true` doing its job.
- **`metadata.role_name`** — the audit trail. Six months from now you can
  answer "which role minted this?".
- **`lease_duration: 900`** — 15 minutes, matching `token_ttl=15m`.
- **`renewable: true`** — the token *can* be renewed, but only up to
  `token_max_ttl=1h`.
- **`lease_id: ""`** — note the top-level `lease_id` is empty. Per
  `VERIFIED-FACTS.md` §4, a plain token's lifetime lives in
  `auth.lease_duration`; the top-level `lease_id` is for *dynamic* secrets.
- **`orphan: true`** — no entity alias was attached to this login. (See
  §4.11 for why that matters for MFA.)
- **`entity_id`** — the login still created an entity. More on that in §4.11.

> **CLI gotcha:** `bao write -f auth/approle/login` prints a **table**, and
> the field is called `token`, **not** `client_token`:
>
> ```console
> $ bao write -f auth/approle/login role_id="$R" secret_id="$S"
> Key                     Value
> ---                     -----
> token                   s.Ti3tHBhjQERnTDI1UygeTv0B
> token_accessor          vPxDpqm6FjR9RYQfJ9RTALMA
> token_duration          15m
> token_renewable         true
> token_policies          ["ai-harness-service"]
> identity_policies       []
> policies                ["ai-harness-service"]
> token_meta_role_name    ai-harness-service
> ```
>
> If you script this with `awk '/^client_token/'` you will get an **empty
> string** and then spend twenty minutes wondering why every request is a
> 403. Use `-format=json` and `auth.client_token`, or use `^token `.

### 4.6 Reading the token back — and a genuine 2.7.1 trap

Introspecting your own token is the first thing you want in a debugging
session:

```console
$ BAO_TOKEN="$T" bao write -f auth/token/lookup-self
Error writing data to auth/token/lookup-self: Error making API request.

URL: PUT http://127.0.0.1:9437/v1/auth/token/lookup-self
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

Why? Because `auth/token/lookup-self` is granted by the built-in `default`
policy, and we set `token_no_default_policy=true`.

Here is the trap: **the built-in `default` policy only grants `read` on that
path, and in OpenBao 2.7.1 `read` is not enough.** The `default` policy
ships with exactly this:

```hcl
path "auth/token/lookup-self" {
    capabilities = ["read"]
}
```

Write two probe policies that differ only in the capability, mint a token
against each, and call the endpoint with each token:

```console
$ cat > probe-read.hcl <<'EOF'
path "auth/token/lookup-self" {
  capabilities = ["read"]
}
EOF
$ bao policy write probe-read probe-read.hcl
Success! Uploaded policy: probe-read

$ cat > probe-update.hcl <<'EOF'
path "auth/token/lookup-self" {
  capabilities = ["update"]
}
EOF
$ bao policy write probe-update probe-update.hcl
Success! Uploaded policy: probe-update
```

With `read`:

```console
$ BAO_TOKEN="$READ_TOKEN" bao write -f auth/token/lookup-self
Error writing data to auth/token/lookup-self: Error making API request.

URL: PUT http://127.0.0.1:9437/v1/auth/token/lookup-self
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

With `update`:

```console
$ BAO_TOKEN="$UPDATE_TOKEN" bao write -f auth/token/lookup-self
Key                 Value
---                 -----
accessor            koPOUZ6x1Zeufzo3xhXzyV16
creation_time       1792602866
creation_ttl        768h
display_name        token
entity_id           n/a
expire_time         2026-11-22T17:14:26.642558271Z
explicit_max_ttl    0s
id                  s.1535DTS85xo5xPJd53g3eFhB
issue_time          2026-10-21T17:14:26.642568859Z
meta                <nil>
num_uses            0
orphan              false
path                auth/token/create
policies            [default probe-update]
renewable           true
ttl                 767h59m59s
type                service
```

The endpoint is a **write** endpoint, so it needs the `update` capability.
`read` on a write path buys you nothing.

And it is not just the `default` policy — a token that *does* carry
`default` still gets 403:

```console
$ BAO_TOKEN="$T" bao write -f auth/token/lookup-self
Error writing data to auth/token/lookup-self: Error making API request.

URL: PUT http://127.0.0.1:9437/v1/auth/token/lookup-self
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

> **If you find a tutorial saying "the default policy lets a token look up
> itself":** *it is describing HashiCorp Vault. In OpenBao 2.7.1 the
> `lookup-self` endpoint requires the **`update`** capability, and the
> built-in `default` policy grants only `read`. A stock `default` policy
> therefore cannot look up its own token.*

**What to do.** If your machine identity needs self-introspection, grant it
explicitly:

```hcl
path "auth/token/lookup-self" {
  capabilities = ["update"]
}
path "auth/token/renew-self" {
  capabilities = ["update"]
}
path "auth/token/revoke-self" {
  capabilities = ["update"]
}
path "sys/capabilities-self" {
  capabilities = ["update"]
}
```

> **Trade-off:** *`token_no_default_policy=true` is correct for a workload
> that only reads a secret. It is wrong for a workload that needs to renew
> itself. `renew-self` and `revoke-self` *also* come from `default` — drop
> it and the client cannot renew its own token, so a 15-minute TTL becomes a
> 15-minute outage.*

### 4.7 `bao token capabilities` — your testing tool

`sys/capabilities-self` is how you ask "what can this token actually do?".
It also comes from `default`, so grant it explicitly (see §4.6) or use the
root token.

**The machine token cannot ask by itself.** `token_no_default_policy=true`
means the `ai-harness-service` token does not carry `default`, and
`default` is what grants `sys/capabilities-self`. Ask with the machine
token and you get:

```console
$ BAO_TOKEN="$T" bao token capabilities ai/platform/data/llm/gemini
Error listing capabilities: Error making API request.

URL: POST http://127.0.0.1:9437/v1/sys/capabilities-self
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

So the question has to be asked with a token that *has* the capability.
Grant it explicitly, exactly as §4.6 recommends:

```console
$ cat > capabilities-probe.hcl <<'EOF'
path "sys/capabilities-self" {
  capabilities = ["update"]
}
path "ai/platform/data/llm/gemini" {
  capabilities = ["read"]
}
EOF
$ bao policy write capabilities-probe capabilities-probe.hcl
Success! Uploaded policy: capabilities-probe

$ PROBE=$(bao token create -policy=capabilities-probe -ttl=10m -field=token)
```

Now the probe token answers precisely:

```console
$ BAO_TOKEN="$PROBE" bao token capabilities ai/platform/data/llm/gemini
read
$ BAO_TOKEN="$PROBE" bao token capabilities ai/platform/data/db/postgres
deny
$ BAO_TOKEN="$PROBE" bao token capabilities ai/platform/data/llm/
deny
```

Three answers, three meanings:

| Answer | Meaning |
|---|---|
| `read` | Exactly one capability. The token can fetch the Gemini key and nothing else on that path. |
| `deny` | No capability at all. A 403. |
| `deny` on the *directory* | The token cannot even **list** what secrets exist under `ai/platform/data/llm/`. Secret *names* are metadata too, and `ai-harness-service.hcl` deliberately does not grant `list`. |

> **Production:** *Put `bao token capabilities` in CI. A policy change that
> accidentally widens a service's reach shows up as a diff in capabilities
> output, not as an incident.*

### 4.8 The denied access — with the real error text

The allow and the deny are equally important. Here is the harness trying to
read the Postgres password with the AI harness token:

```console
$ BAO_TOKEN="$T" bao kv get ai/platform/db/postgres
Error reading ai/platform/data/db/postgres: Error making API request.

URL: GET http://127.0.0.1:9437/v1/ai/platform/data/db/postgres
Code: 403. Errors:

* 1 error occurred:
	* permission denied
```

And the allowed read, for contrast:

```console
$ BAO_TOKEN="$T" bao kv get -format=json ai/platform/llm/gemini | python3 -m json.tool
{
    "request_id": "fdaada20-c0cb-5c19-04e4-96ef3aadc17d",
    "lease_id": "",
    "lease_duration": 0,
    "renewable": false,
    "data": {
        "data": {
            "api_key": "AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr"
        },
        "metadata": {
            "created_time": "2026-10-21T16:33:53.193929382Z",
            "custom_metadata": null,
            "deletion_time": "",
            "destroyed": false,
            "version": 1
        }
    },
    "warnings": null
}
```

Note the double `.data` — `data.data.api_key`. Module 02 covered that; it
is unchanged here.

### 4.9 Failure modes — every one of them, with the real text

**Expired `secret_id`.** `secret_id_ttl=5s`, wait 8 seconds:

```console
$ bao write -f auth/approle/login role_id="$R" secret_id="$S"
Error writing data to auth/approle/login: Error making API request.

URL: PUT http://127.0.0.1:9437/v1/auth/approle/login
Code: 400. Errors:

* invalid role or secret ID
```

**A completely wrong `secret_id`:**

```console
$ bao write -f auth/approle/login role_id="$R" secret_id="00000000-0000-0000-0000-000000000000"
Error writing data to auth/approle/login: Error making API request.

URL: PUT http://127.0.0.1:9437/v1/auth/approle/login
Code: 400. Errors:

* invalid role or secret ID
```

**A wrong `role_id`:**

```console
$ bao write -f auth/approle/login role_id="11111111-2222-3333-4444-555555555555" secret_id="$S"
Error writing data to auth/approle/login: Error making API request.

URL: PUT http://127.0.0.1:9437/v1/auth/approle/login
Code: 400. Errors:

* invalid role or secret ID
```

> **Notice that all three produce the *identical* message.** That is
> deliberate: a different message for "expired" vs "wrong" would be an
> oracle telling an attacker which half of the credential they got right.

**A `secret_id` that has already been redeemed** (`secret_id_num_uses=1`):

```console
$ bao write -f auth/approle/login role_id="$R" secret_id="$S"
Error writing data to auth/approle/login: Error making API request.

URL: PUT http://127.0.0.1:9437/v1/auth/approle/login
Code: 400. Errors:

* invalid role or secret ID
```

**Source IP outside `secret_id_bound_cidrs`:**

```console
$ bao write -f auth/approle/login role_id="$R" secret_id="$S"
Error writing data to auth/approle/login: Error making API request.

URL: PUT http://127.0.0.1:9437/v1/auth/approle/login
Code: 400. Errors:

* source address "127.0.0.1" unauthorized by CIDR restrictions on the role: %!w(<nil>)
```

> **Yes, `%!w(<nil>)` is really in the error.** It is a Go formatting bug in
> OpenBao 2.7.1 (a `%w` verb with a nil error). Copy the message verbatim
> when you write a runbook — grepping for it will not match anything
> tidier.

### 4.10 `token_bound_cidrs` is enforced at login **and** at use

This is the difference between the two CIDR options, and it is worth
proving rather than asserting.

The lab server was rebound to `0.0.0.0` so that a second source IP was
available. The role was pinned to `127.0.0.1/32`:

```console
$ bao write auth/approle/role/uid-demo token_policies="ai-harness-service" \
    token_no_default_policy=true token_ttl=15m secret_id_ttl=1h secret_id_num_uses=1 \
    token_bound_cidrs="127.0.0.1/32"
Success! Data written to: auth/approle/role/uid-demo
```

Logging in from `127.0.0.1` (inside the CIDR) and then using the token from
a different address:

```console
$ BAO_TOKEN="$T" bao kv get ai/platform/llm/gemini
======= Secret Path =======
ai/platform/data/llm/gemini

======= Metadata =======
Key                Value
---                -----
created_time       2026-10-21T16:33:53.193929382Z
custom_metadata    <nil>
deletion_time      n/a
destroyed          false
version            1
```

```console
$ BAO_ADDR="http://172.26.27.12:9437" BAO_TOKEN="$T" bao kv get ai/platform/llm/gemini
Error making API request.

URL: GET http://172.26.27.12:9437/v1/sys/internal/ui/mounts/ai/platform/llm/gemini
Code: 403. Errors:

* permission denied
```

(The address `172.26.27.12` is this lab's own non-loopback interface — read
`hostname -I` on yours. The point is that the *same token* was accepted
from `127.0.0.1` and rejected from the other address.)

**The token works from one address and is rejected from another.** A stolen
token replayed from the attacker's host is useless.

| | `secret_id_bound_cidrs` | `token_bound_cidrs` |
|---|---|---|
| Checked at login | ✅ | ✅ |
| Checked on every request | ❌ | ✅ |
| Protects against | Leaking the `secret_id` to the wrong network | **Replaying a stolen token** from somewhere else |
| Use it when | The `secret_id` travels over a network you control | The token could be exfiltrated |

> **Production:** *Use both. `secret_id_bound_cidrs` protects the credential
> on the way in; `token_bound_cidrs` protects the credential on the way out.
> They cost you nothing except a static egress IP.*

### 4.11 `bind_secret_id=false` is blocked — and that is a feature

You might think "I have a private network, I'll just use the `role_id`".
OpenBao 2.7.1 refuses:

```console
$ bao write auth/approle/role/nosecret bind_secret_id=false secret_id_ttl=1h secret_id_num_uses=1
Error writing data to auth/approle/role/nosecret: Error making API request.

URL: PUT http://127.0.0.1:9437/v1/auth/approle/role/nosecret
Code: 500. Errors:

* 1 error occurred:
	* at least one constraint should be enabled on the role
```

The full matrix, verified by probing every combination:

| `bind_secret_id` | `secret_id_ttl` | `secret_id_num_uses` | `secret_id_bound_cidrs` | Result |
|---|---|---|---|---|
| `true` | — | — | — | ✅ OK |
| `true` | `1h` | `1` | — | ✅ OK |
| `false` | `1h` | `1` | — | ❌ 500 "at least one constraint should be enabled on the role" |
| `false` | — | — | `127.0.0.1/32` | ✅ OK |

**The only constraint that satisfies `bind_secret_id=false` is
`secret_id_bound_cidrs`.** So even if you insist on a `role_id`-only login,
OpenBao forces you to pin the source address. That is a good trade: it means
the "role_id only" configuration cannot exist without a network control
alongside it.

### 4.12 Two more operational endpoints

**Mint a `secret_id` with a value you choose.** Useful when the delivery
mechanism needs a deterministic value (a file provisioned by an init
container, for example):

```console
$ bao write -format=json auth/approle/role/ai-harness-service/custom-secret-id \
    secret_id="5f9a3c71-2d84-4b6e-9a15-7c3e8b4d1f20"
{
    "request_id": "8076d915-0152-9145-f7f4-43ec4e0485e3",
    "lease_id": "",
    "lease_duration": 0,
    "renewable": false,
    "data": {
        "secret_id": "5f9a3c71-2d84-4b6e-9a15-7c3e8b4d1f20",
        "secret_id_accessor": "c4811ac0-77e8-41af-67fa-afaf4a9fbee4",
        "secret_id_num_uses": 1,
        "secret_id_ttl": 3600
    },
    "warnings": null
}
```

**Look up and destroy a single `secret_id` without holding it.** This is
how you revoke one deployment's credential without touching the role:

```console
$ bao write -format=json auth/approle/role/uses-demo/secret-id-accessor/lookup \
    secret_id_accessor="4d71184d-42b3-5701-2c27-71d43d640e5f"
{
    "request_id": "7e63597d-9638-4866-a59f-65b2b0369fbb",
    "lease_id": "",
    "lease_duration": 0,
    "renewable": false,
    "data": {
        "cidr_list": [],
        "creation_time": "2026-10-21T16:36:29.721344302Z",
        "expiration_time": "2026-10-21T17:36:29.721344302Z",
        "last_updated_time": "2026-10-21T16:36:29.721344302Z",
        "metadata": {},
        "secret_id_accessor": "4d71184d-42b3-5701-2c27-71d43d640e5f",
        "secret_id_num_uses": 1,
        "secret_id_ttl": 3600,
        "token_bound_cidrs": []
    },
    "warnings": null
}
```

```console
$ bao write -f auth/approle/role/uses-demo/secret-id-accessor/destroy \
    secret_id_accessor="4d71184d-42b3-5701-2c27-71d43d640e5f"
Success! Data written to: auth/approle/role/uses-demo/secret-id-accessor/destroy
```

> **CLI gotcha:** the path is `secret-id-accessor/…` — **not**
> `secret-id/accessor/…`. The latter is a 404:
>
> ```console
> $ bao write -f auth/approle/role/uses-demo/secret-id/accessor/destroy secret_id_accessor="…"
> Error writing data to auth/approle/role/uses-demo/secret-id/accessor/destroy: Error making API request.
>
> URL: PUT http://127.0.0.1:9437/v1/auth/approle/role/uses-demo/secret-id/accessor/destroy
> Code: 404. Errors:
>
> * 1 error occurred:
> 	* unsupported path
> ```

**And revoke an issued token by its accessor** — you never need to hold the
token itself, which is exactly what you want during an incident:

```console
$ bao write -f auth/token/revoke-accessor accessor="Cosb5SADzlIChLOhfDRz17ew"
Success! Data written to: auth/token/revoke-accessor
```

The token is dead immediately, even though nobody ever read it:

```console
$ BAO_TOKEN="$T" bao kv get -field=api_key ai/platform/llm/gemini
Error making API request.

URL: GET http://127.0.0.1:9437/v1/sys/internal/ui/mounts/ai/platform/llm/gemini
Code: 403. Errors:

* permission denied
```

**And a janitor for expired `secret_id`s:**

```console
$ bao write -f auth/approle/tidy/secret-id role_name=ai-harness-service
WARNING! The following warnings were returned from OpenBao:

  * Tidy operation successfully started. Any information from the operation
  will be printed to OpenBao's server logs.
```

---

## 5. The hard part: how a `secret_id` reaches a container

Everything above was easy. This is the part that decides whether your
secret store is real or theatre.

### 5.1 Why the `.env` pattern dies here

The previous engineer's `.env` file looked like this:

```dotenv
# .env  (DO NOT COMMIT)
GEMINI_API_KEY=AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr
POSTGRES_PASSWORD=Xk9pL2mN4qR7sT1vW3yZ6bC8dF5gH0jA2eK
REDIS_PASSWORD=Yb3mQ8vT1xW6rK4pL9zD2nF7gH5jA0sC4eU
```

Swap that for an AppRole credential and you would be tempted to write:

```dotenv
# .env  (STILL WRONG)
BAO_ROLE_ID=6b035535-fa5a-3955-772d-2c5eced94da4
BAO_SECRET_ID=cf2f63ec-c8af-ff10-1905-0ad37f2a8f83
```

**That is the same mistake with a new variable name.** Here is the
anatomy, in four layers:

| Layer | What leaks | Can you avoid it? |
|---|---|---|
| **1. Git** | The file is in the repository, in every clone, in the history forever, in every fork. | Yes — `.gitignore` + secret scanning, but you now rely on humans. |
| **2. The image** | `COPY .env .` bakes the file into a layer. `docker history` shows it. The layer persists even if a later layer deletes it. | Yes — but then the deploy needs another channel anyway. |
| **3. The container's environment** | `docker inspect <container>` shows `Env` to anyone with Docker socket access — which is *root on the host*. `ENV`/`ARG` in a Dockerfile end up in `docker history` too. | **No.** Container environment is not a secret store. |
| **4. The running process** | `/proc/<pid>/environ` is readable by the same UID and by root. `ps eww` dumps it. Any crash reporter, APM agent, or sidecar that scrapes the environment gets it. | **No.** Not while the process lives. |

Layer 3 is the one that kills it. Once a secret is in the container
environment, it is a *host-level* secret, and a host-level secret is
exactly the thing you built OpenBao to stop depending on.

> **The rule:** *A secret should be in the container's **filesystem** or in
> the process's **memory** — never in its **environment**, and never in an
> image layer.* The environment is the one place you cannot control the
> blast radius.

The `role_id` is exempt. It is not a secret.

### 5.2 Pattern A — CI/CD injection

**The idea:** the pipeline mints a fresh `secret_id` and hands it to the
deploy step as a masked CI variable. The deploy step writes it to a
temporary file (or passes it via stdin) and deletes it afterwards.

**The server side** (this is the part you get right for free):

```console
$ bao write -f auth/approle/role/ai-harness-service/secret-id
Key                   Value
---                   -----
secret_id             cf2f63ec-c8af-ff10-1905-0ad37f2a8f83
secret_id_accessor    a2dc0ad8-541b-32a0-a9f7-fbf80ef36df5
secret_id_num_uses    1
secret_id_ttl         1h
```

**The pipeline side** — GitHub Actions shape, matching Meridian AI's stack:

```yaml
# .github/workflows/deploy-ai-harness.yml
name: deploy ai-harness

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production          # enables environment-scoped secrets + reviewers
    steps:
      - uses: actions/checkout@v4

      - name: Mint a single-use AppRole secret_id
        id: mint
        env:
          BAO_ADDR: https://bao.meridian-ai.example
          BAO_TOKEN: ${{ secrets.BAO_DEPLOY_TOKEN }}
        run: |
          set -euo pipefail
          # The TTL and the use-count come from the ROLE, not from this call.
          # See the gotcha below.
          bao write -f auth/approle/role/ai-harness-service/secret-id > secret_id.txt
          echo "secret_id=$(awk '/^secret_id /{print $2}' secret_id.txt)" >> "$GITHUB_OUTPUT"
          # never echo the value; GitHub masks it in logs, but do not rely on that

      - name: Deploy
        env:
          BAO_ROLE_ID: 6b035535-fa5a-3955-772d-2c5eced94da4
          BAO_SECRET_ID: ${{ steps.mint.outputs.secret_id }}
        run: |
          set -euo pipefail
          # write it to a 0400 file, not into the image
          umask 077
          printf '%s' "$BAO_SECRET_ID" > ./secret_id
          ./deploy.sh                 # your deploy tool
          shred -u ./secret_id 2>/dev/null || rm -f ./secret_id
```

> **CLI gotcha — the generation call does not take TTL overrides.**
> `secret_id_ttl` and `secret_id_num_uses` belong to the **role**. Passing
> them to the generation endpoint is silently ignored:
>
> ```console
> $ bao write -f auth/approle/role/ai-harness-service/secret-id \
>     secret_id_ttl=10m secret_id_num_uses=1
> WARNING! The following warnings were returned from OpenBao:
>
>   * Endpoint ignored these unrecognized parameters: [secret_id_num_uses
>   secret_id_ttl]
>
> Key                   Value
> ---                   -----
> secret_id             604fbf4f-b22a-03d9-6957-662e88b1e9a3
> ```
>
> To shorten the life of a minted `secret_id`, shorten it **on the role**
> (§4.3). If you need per-deployment lifetimes, create a second role.

**Trade-offs:**

- ✅ The `secret_id` never lands in a file on a developer's laptop.
- ✅ Short TTL and single use bound the damage if the CI runner is reused.
- ✅ A new `secret_id` per deploy means a leaked one is dead in minutes.
- ❌ The CI runner holds the secret **in an environment variable** — layer 3
  of the anatomy above, applied to the runner. Mitigate with a dedicated,
  ephemeral runner and a short-lived `BAO_DEPLOY_TOKEN`.
- ❌ `BAO_DEPLOY_TOKEN` is itself a long-lived credential in the CI secret
  store. You have moved the problem one level up, not solved it. The
  honest framing: **CI/CD injection is a *convenience* pattern, and it is
  the right one for a pipeline that already has a secret store.** It is not
  a pattern for a company with no secret store.

### 5.3 Pattern B — the mounted file

**The idea:** the `secret_id` is written to a file *outside* the image and
bind-mounted (or mounted as a Docker secret / a Kubernetes `Secret` volume)
at container start. The app reads it once at startup, exchanges it for a
token, and drops it.

**The reader** — stdlib only, no third-party client, no `.env`:

```python
#!/usr/bin/env python3
"""Log in to OpenBao with AppRole, reading both IDs from files.

Stdlib only. No third-party client, no .env file, no env vars.
"""
import json, os, sys, urllib.error, urllib.request

BAO_ADDR = os.environ.get("BAO_ADDR", "http://127.0.0.1:8200")
SECRETS_DIR = os.environ.get("BAO_SECRETS_DIR", "/run/secrets/openbao")

def read_secret(name: str) -> str:
    path = os.path.join(SECRETS_DIR, name)
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read().strip()

def approle_login(role_id: str, secret_id: str) -> dict:
    body = json.dumps({"role_id": role_id, "secret_id": secret_id}).encode()
    req = urllib.request.Request(
        f"{BAO_ADDR}/v1/auth/approle/login", data=body, method="PUT",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)

if __name__ == "__main__":
    try:
        result = approle_login(read_secret("role_id"), read_secret("secret_id"))
    except urllib.error.HTTPError as exc:
        print(f"login failed: HTTP {exc.code}", file=sys.stderr)
        print(exc.read().decode(), file=sys.stderr)
        sys.exit(1)
    auth = result["auth"]
    print("token   :", auth["client_token"])
    print("policies:", auth["policies"])
    print("ttl     :", auth["lease_duration"], "seconds")
    print("entity  :", auth.get("entity_id"))
```

**Verified run** against the live lab server, with both files at mode
`0400`:

```console
$ ls -l /run/secrets/openbao
-r-------- 1 meridian meridian 36 Aug 21 16:42 role_id
-r-------- 1 meridian meridian 36 Aug 21 16:42 secret_id

$ python3 login_from_file.py
token   : s.DQBrA1c4ISh8SwIP8FeQCJPk
policies: ['ai-harness-service']
ttl     : 900 seconds
entity  : b9a00e52-aaca-6873-6cdc-64bc4f81d9d9
```

**The mount** — Docker Compose shape:

```yaml
services:
  ai-harness:
    build: ./app
    environment:
      BAO_ADDR: https://bao.meridian-ai.example
      BAO_SECRETS_DIR: /run/secrets/openbao
    secrets:
      - openbao_role_id
      - openbao_secret_id
    read_only: true
    tmpfs:
      - /tmp
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]

secrets:
  openbao_role_id:
    file: ./secrets/role_id
  openbao_secret_id:
    file: ./secrets/secret_id
```

**Trade-offs:**

- ✅ The `secret_id` is **not** in the environment and **not** in an image
  layer. It is in a file that only the app's UID can read.
- ✅ The file can live on a tmpfs — it never touches a disk.
- ✅ The same file can be replaced on a running container (see the
  rotation section in [Module 07](../07-app-integration/README.md)).
- ❌ **The file has to exist somewhere before the container starts.** If
  that somewhere is a file on the deploy host, you are back to "a secret in
  a file" — just a better-protected file.
- ❌ A `secret_id` baked into a file is a *long-lived* credential, so it
  must be paired with a short `secret_id_ttl` and a way to refresh it.

### 5.4 Pattern C — the bootstrap init container

**The idea:** a one-shot container runs *before* the app, logs in, and
writes the resulting **token** (not the `secret_id`) to a shared tmpfs
volume. The app container mounts that volume read-only and never sees a
`secret_id` at all.

**The bootstrap** — run once, then exit:

```python
#!/usr/bin/env python3
"""Bootstrap container: exchange role_id + secret_id for a token ONCE,
then write the token (and nothing else) to a shared volume.

This is the pattern that kills the .env file: the secret_id exists in this
process's memory for a few milliseconds and is never written to a file,
an env var, or an image layer.
"""
import json, os, sys, urllib.error, urllib.request

BAO_ADDR = os.environ.get("BAO_ADDR", "http://127.0.0.1:8200")
SECRETS_DIR = os.environ.get("BAO_SECRETS_DIR", "/run/secrets/openbao")
OUT_DIR = os.environ.get("BAO_OUT_DIR", "/run/bao")

def read_secret(name):
    with open(os.path.join(SECRETS_DIR, name), "r", encoding="utf-8") as fh:
        return fh.read().strip()

def api(path, payload=None, token=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Vault-Token"] = token
    req = urllib.request.Request(f"{BAO_ADDR}/v1/{path}", data=data,
                                 method="PUT" if data else "GET", headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}

def write_out(name, value, mode=0o400):
    path = os.path.join(OUT_DIR, name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w") as fh:
        fh.write(value)
    os.chmod(path, mode)

if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    try:
        login = api("auth/approle/login", {
            "role_id": read_secret("role_id"),
            "secret_id": read_secret("secret_id"),
        })
    except urllib.error.HTTPError as exc:
        print(f"AppRole login failed: HTTP {exc.code}", file=sys.stderr)
        print(exc.read().decode().strip(), file=sys.stderr)
        sys.exit(1)
    token = login["auth"]["client_token"]
    write_out("token", token)
    print(f"wrote {OUT_DIR}/token (mode 0400), ttl={login['auth']['lease_duration']}s")
```

**Verified run:**

```console
$ python3 bootstrap.py
wrote /run/bao/token (mode 0400), ttl=900s

$ ls -l /run/bao
-r-------- 1 meridian meridian 26 Aug 21 16:42 token

$ bao kv get -field=api_key ai/platform/llm/gemini
AIzaSyD8fJ2mKpQ7nR4tVxZ1bYc6HfJ1mN9pQr
```

And the second run fails, because the one-shot `secret_id` is spent:

```console
$ python3 bootstrap.py
AppRole login failed: HTTP 400
{"errors":["invalid role or secret ID"]}
```

**Trade-offs:**

- ✅ The app container **never** handles a `secret_id`. It gets a token that
  expires in 15 minutes.
- ✅ The `secret_id` exists only in the bootstrap process's memory, for
  milliseconds. It is never written anywhere.
- ✅ The bootstrap container is trivially re-runnable: mint a new
  `secret_id`, re-run it, restart the app.
- ❌ The token on the shared volume is still a bearer credential, and it
  lives until it expires. Rotate it (§5.5).
- ❌ Kubernetes equivalent (`initContainer` + `emptyDir: medium: Memory`)
  works exactly the same way — but a `medium: Memory` volume is
  node-local, so the pod cannot be rescheduled without re-running the
  init container. That is fine, because the init container re-runs on
  reschedule.

### 5.5 Choosing between the three

| | **A: CI/CD injection** | **B: Mounted file** | **C: Bootstrap init container** |
|---|---|---|---|
| Where the `secret_id` lives | CI runner env → temp file | A file, often tmpfs | One process's memory, for milliseconds |
| App container sees | A `secret_id` | A `secret_id` | Only a **token** |
| Works without a CI system | ❌ | ✅ | ✅ |
| Rotatable without a redeploy | ❌ (needs a pipeline run) | ✅ (replace the file) | ✅ (re-run the bootstrap) |
| Credential lifetime | Minutes (`secret_id_ttl`) | Until the file is rotated | 15 minutes (the token TTL) |
| Failure mode | CI runner leak | File on the deploy host leaks | Bootstrap container logs the failure |
| **Best for** | Pipelines you already run | Simple single-host deploys | Kubernetes and anything that must not hold a `secret_id` |

> **Production:** *Meridian AI should use **C** for the Kubernetes
> deployment of `ai-harness`, and **B** for a plain-Docker deployment, with
> **A** as the *generator* of the `secret_id` in both cases. The `secret_id`
> is always minted by a privileged pipeline step; the app never sees it.*

---

## 6. OIDC with Keycloak

### 6.1 The realm Meridian AI already has

`lab/keycloak/realm-export.json` is the real realm. The parts that matter:

```json
{
  "realm": "meridian-ai",
  "groups": [
    { "name": "platform-team",  "path": "/platform-team",  "realmRoles": ["platform-operator"] },
    { "name": "security-team",  "path": "/security-team",  "realmRoles": ["platform-admin"] }
  ],
  "clients": [
    {
      "clientId": "ai-harness",
      "publicClient": false,
      "standardFlowEnabled": true,
      "secret": "meridian-ai-harness-client-secret-rotate-me",
      "redirectUris": ["http://localhost:8000/*", "http://localhost:3000/*"],
      "attributes": { "pkce.code.challenge.method": "S256" },
      "defaultClientScopes": ["openid", "profile", "email", "roles", "web-origins", "groups"]
    }
  ],
  "clientScopes": [
    {
      "name": "groups",
      "protocolMappers": [
        { "name": "groups", "protocolMapper": "oidc-group-membership-mapper",
          "config": { "claim.name": "groups", "claim.property": "path",
                      "multivalued": "true", "id.token.claim": "true" } }
      ]
    }
  ],
  "users": [
    { "username": "aisha.rahman", "groups": ["/platform-team"], "realmRoles": ["platform-operator"] }
  ]
}
```

Five things this tells you:

1. The **issuer** is `http://keycloak:8080/realms/meridian-ai` (from the
   realm name). That is the discovery URL you give OpenBao.
2. The **client** is `ai-harness`, a *confidential* client
   (`publicClient: false`) with a secret.
3. **PKCE is on** (`pkce.code.challenge.method: S256`) — good, and OpenBao
   will use it (§6.7).
4. The **groups** are the mapping key. `platform-team` →
   `platform-operator`, `security-team` → `platform-admin`.
5. The `groups` claim is what OpenBao's CEL program will read, so the
   realm has to emit it. ⚠️ **The `roles` client scope does not do this.**
   `roles` gives you `realm_access.roles` — the *realm roles* a user has.
   It does **not** give you `groups`, which is the *group path* a user
   belongs to. They are different things, and confusing them is the single
   most common reason a Keycloak → OpenBao OIDC login fails with
   "the token has no groups".

   So this realm defines a `groups` client scope with a
   `oidc-group-membership-mapper` and adds it to the client's
   `defaultClientScopes`:

   ```json
   "clientScopes": [
     {
       "name": "groups",
       "protocolMappers": [
         {
           "name": "groups",
           "protocolMapper": "oidc-group-membership-mapper",
           "config": {
             "claim.name": "groups",
             "claim.property": "path",
             "multivalued": "true",
             "id.token.claim": "true"
           }
         }
       ]
     }
   ]
   ```

   and the client lists it:

   ```json
   "defaultClientScopes": ["openid", "profile", "email", "roles", "web-origins", "groups"]
   ```

   With that mapper in place the ID token carries
   `"groups": ["platform-team"]`, which is exactly what the CEL program in
   §6.8 tests for. If you see an ID token with `realm_access` but no
   `groups`, this is why.

> **Trade-off:** *You can also map groups into `realm_access.roles`
> instead, and then write the CEL program against
> `claims.realm_access.roles`. Both work. Explicit `groups` is easier to
> read in a token and does not collide with the realm-role namespace, so
> this course uses a dedicated claim.*

### 6.2 Enable the method

```console
$ bao auth enable oidc
Success! Enabled oidc auth method at: oidc/
```

### 6.3 The discovery URL gotcha

Your instinct is to paste the full well-known URL. OpenBao rejects it:

```console
$ bao write auth/oidc/config \
    oidc_discovery_url="http://keycloak:8080/realms/meridian-ai/.well-known/openid-configuration" \
    oidc_client_id="ai-harness" \
    oidc_client_secret="meridian-ai-harness-client-secret-rotate-me" \
    role="platform-operator"
Error writing data to auth/oidc/config: Error making API request.

URL: PUT http://127.0.0.1:9437/v1/auth/oidc/config
Code: 400. Errors:

* 'oidc_discovery_url' contains '.well-known' component
```

**Give OpenBao the issuer URL. It appends the `.well-known` path itself.**
The error message from the next failure proves it:

```console
$ bao write auth/oidc/config \
    oidc_discovery_url="http://keycloak:8080/realms/meridian-ai" \
    oidc_client_id="ai-harness" \
    oidc_client_secret="meridian-ai-harness-client-secret-rotate-me" \
    role="platform-operator"
Error writing data to auth/oidc/config: Error making API request.

URL: PUT http://127.0.0.1:9437/v1/auth/oidc/config
Code: 400. Errors:

* error checking oidc discovery URL: error creating provider with given values: NewProvider: unable to create provider: Get "http://keycloak:8080/realms/meridian-ai/.well-known/openid-configuration": dial tcp: lookup keycloak on 192.168.0.10:53: no such host
```

Read the URL in that message carefully: OpenBao requested
`http://keycloak:8080/realms/meridian-ai/.well-known/openid-configuration`.
It added the suffix.

### 6.4 The config write must be *complete*

Another surprise. A partial update is rejected outright:

```console
$ bao write auth/oidc/config default_role="platform-operator"
Error writing data to auth/oidc/config: Error making API request.

URL: PUT http://127.0.0.1:9437/v1/auth/oidc/config
Code: 400. Errors:

* exactly one of 'jwt_validation_pubkeys', 'jwks_url', 'jwks_pairs', 'oidc_discovery_url', or 'provider_config' must be set
```

**Every write to `auth/oidc/config` must include exactly one key-source.**
So "just change the client secret" is not a one-liner — you resend the
whole config. Write it as a file and apply it as a unit.

```bash
#!/usr/bin/env bash
# apply-oidc-config.sh - always send the complete config
set -euo pipefail
bao write auth/oidc/config \
  oidc_discovery_url="http://keycloak:8080/realms/meridian-ai" \
  oidc_client_id="ai-harness" \
  oidc_client_secret="meridian-ai-harness-client-secret-rotate-me" \
  default_role="platform-operator"
```

Two more traps in that block:

- **`role=` is not a field.** It is silently ignored — the write succeeds
  and nothing changes. The real field is **`default_role=`**.
- **`default_role` names an OIDC *role*, not a policy.** A later login
  without a role proves it:

  ```console
  $ bao write -format=json auth/oidc/login jwt="$IDT"
  Error writing data to auth/oidc/login: Error making API request.

  URL: PUT http://127.0.0.1:9437/v1/auth/oidc/login
  Code: 400. Errors:

  * role "platform-operator" could not be found
  ```

  OpenBao looked for a *role* called `platform-operator`. Your policy is
  also called `platform-operator`; they are different namespaces and the
  names collide confusingly. Name OIDC roles after the *group*:
  `platform-team`, `security-team`.

### 6.5 The role: `auth/oidc/role` — **singular**

```console
$ bao write auth/oidc/roles/platform-team bound_claims.groups=platform-team
Error writing data to auth/oidc/roles/platform-team: Error making API request.

URL: PUT http://127.0.0.1:9437/v1/auth/oidc/roles/platform-team
Code: 404. Errors:

* 1 error occurred:
	* unsupported path
```

It is `auth/oidc/role/{name}`. (Vault Enterprise's group-mapping endpoint
was `auth/oidc/roles`; in OpenBao 2.7.1 it is `auth/oidc/role`.)

Two more required fields surface one at a time — and **not in the order you
would guess.** OpenBao checks `allowed_redirect_uris` first, so that is the
error a bare write gives you:

```console
$ bao write auth/oidc/role/probe2 user_claim="email" bound_claims.groups=platform-team
Error writing data to auth/oidc/role/probe2: Error making API request.

URL: PUT http://127.0.0.1:9437/v1/auth/oidc/role/probe2
Code: 400. Errors:

* 'allowed_redirect_uris' must be set if 'role_type' is 'oidc' or unspecified.
```

Add `allowed_redirect_uris` and the *next* missing field appears:

```console
$ bao write auth/oidc/role/probe2 bound_claims.groups=platform-team \
    allowed_redirect_uris="http://localhost:8000/oidc/callback"
Error writing data to auth/oidc/role/probe2: Error making API request.

URL: PUT http://127.0.0.1:9437/v1/auth/oidc/role/probe2
Code: 400. Errors:

* a user claim must be defined on the role
```

With both present, the write goes through:

```console
$ bao write auth/oidc/role/probe2 user_claim="email" bound_claims.groups=platform-team \
    allowed_redirect_uris="http://localhost:8000/oidc/callback"
Success! Data written to: auth/oidc/role/probe2
```

> **Note what that write did *not* do:** it reported success and stored
> `bound_claims` as `null`. Read on — the CLI's map syntax is a trap.

### 6.6 `bound_claims` needs the JSON API

The CLI's `field.key=value` form **does not persist** the map. Verified:

```console
$ bao write auth/oidc/role/platform-team \
    bound_claims.groups=platform-team \
    user_claim="email" groups_claim="groups" \
    allowed_redirect_uris="http://localhost:8000/*" \
    token_policies="platform-operator" token_ttl=1h
Success! Data written to: auth/oidc/role/platform-team

$ bao read -format=json auth/oidc/role/platform-team | jq .data.bound_claims
null
```

The server accepted it, stored nothing, and reported success. Use the JSON
API:

```console
$ curl -s -X PUT -H "X-Vault-Token: $BAO_TOKEN" -H "Content-Type: application/json" \
  -d '{
    "bound_claims": {"groups": "platform-team"},
    "bound_claims_type": "string",
    "claim_prefix": "platform_team",
    "user_claim": "email",
    "groups_claim": "groups",
    "bound_issuer": "http://keycloak:8080/realms/meridian-ai",
    "allowed_redirect_uris": ["http://localhost:8000/oidc/callback"],
    "token_policies": ["platform-operator"],
    "token_ttl": "1h"
  }' http://127.0.0.1:9437/v1/auth/oidc/role/platform-team
```

Now it sticks:

```console
$ bao read -format=json auth/oidc/role/platform-team | python3 -c "
import json,sys;d=json.load(sys.stdin)['data']
for k in ('bound_claims','bound_claims_type','claim_prefix','user_claim','groups_claim','allowed_redirect_uris','token_policies','token_ttl','role_type'):
    print(f'{k:26} = {d.get(k)!r}')"
bound_claims               = {'groups': 'platform-team'}
bound_claims_type          = 'string'
claim_prefix               = None
user_claim                 = 'email'
groups_claim               = 'groups'
allowed_redirect_uris      = ['http://localhost:8000/oidc/callback']
token_policies             = ['platform-operator']
token_ttl                  = 3600
role_type                  = 'oidc'
```

> **Two things to notice.**
> 1. `claim_prefix` and `bound_issuer` are **accepted by the write and not
>    returned by the read** in OpenBao 2.7.1. Verify the *effect* of
>    `claim_prefix` (the group name it produces) rather than trusting the
>    read-back. §6.7 shows how.
> 2. `bound_claims_type` accepts only `"string"`:
>
>    ```console
>    $ bao write auth/oidc/role/probe3 bound_claims_type="array" ...
>    Code: 400. Errors:
>
>    * invalid 'bound_claims_type': array
>    ```
>
>    Keycloak emits `groups` as a **JSON array**, so a strict
>    `bound_claims` equality check against a Keycloak ID token will not
>    match. **Use `groups_claim` (array-aware) for group extraction, and
>    `bound_claims` only for single-valued claims.** This is the single
>    most important OIDC detail for the Meridian AI realm.

### 6.7 What OpenBao actually sends the browser

OpenBao does not proxy Keycloak. It builds the authorization URL and the
browser goes to Keycloak directly. That URL is observable without a
browser:

```console
$ bao write -format=json auth/oidc/oidc/auth_url \
    role="platform-team" \
    redirect_uri="http://localhost:8000/oidc/callback"
{
    "request_id": "1eb1c235-9f98-f6bd-54ef-bb8a6120d52e",
    "lease_id": "",
    "lease_duration": 0,
    "renewable": false,
    "data": {
        "auth_url": "http://127.0.0.1:18080/realms/meridian-ai/protocol/openid-connect/auth?client_id=ai-harness&code_challenge=LDL1flaU9VCAdVrQl8PVG3cVYw40iLJaHv_HMdMNT9Q&code_challenge_method=S256&nonce=n_5UB4JcukFzLBfX2D7OFC&redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Foidc%2Fcallback&response_type=code&scope=openid&state=st_O1Pwu8e7uIt49IM6gXWH"
    },
    "warnings": null
}
```

Read the parameters — this is the security contract:

| Parameter | Value | Why it matters |
|---|---|---|
| `response_type=code` | Authorization Code flow | The ID token never crosses the front channel. |
| `code_challenge_method=S256` | PKCE | Matches `pkce.code.challenge.method: S256` in the realm export. |
| `code_challenge` | random | Binds the code to the client that requested it. |
| `nonce` | random | Binds the ID token to *this* login attempt. |
| `state` | random | CSRF protection for the redirect back to you. |
| `scope=openid` | | Minimum scope. `profile`/`email` come from the role's claims. |

> **Production:** *Never disable PKCE on the Keycloak client. The realm
> export already has `S256`. If you ever find yourself writing
> `code_challenge_method=plain`, stop.*

### 6.8 CEL roles — and why the classic role cannot log in

OpenBao 2.7.1 has **two** kinds of OIDC role.

**`role_type: "oidc"`** is the Vault-style role: `bound_claims`,
`user_claim`, `groups_claim`. You can create it and read it back — but you
**cannot log in with it**:

```console
$ bao write -format=json auth/oidc/login role="platform-team" jwt="$IDT"
Error writing data to auth/oidc/login: Error making API request.

URL: PUT http://127.0.0.1:9437/v1/auth/oidc/login
Code: 400. Errors:

* role with oidc role_type is not allowed
```

**`role_type: "cel"`** lives at a different path — `auth/oidc/cel/role` —
and is logged in against with `auth/oidc/cel/login`. The role body is a
**CEL program** (Common Expression Language) that decides, from the token
claims, who the caller is and what policies they get.

```console
$ curl -s -X PUT -H "X-Vault-Token: $BAO_TOKEN" -H "Content-Type: application/json" \
  -d '{
    "bound_audiences": ["ai-harness"],
    "cel_program": {
      "variables": [
        {"name": "is_platform_team",
         "expression": "claims.groups.exists(g, g == \"platform-team\")"},
        {"name": "result",
         "expression": "pb.Auth{display_name: claims.email, policies: is_platform_team ? [\"platform-operator\"] : [\"default\"], num_uses: 0}"}
      ],
      "expression": "is_platform_team ? result : false"
    }
  }' http://127.0.0.1:9437/v1/auth/oidc/cel/role/platform-team-cel
```

That program says, in plain English:

> *"If the ID token's `groups` claim contains `platform-team`, the caller is
> `claims.email` and gets the `platform-operator` policy. Otherwise they
> get `default`. If the group is absent, the final expression returns
> `false` and the login is blocked."*

**And it works.** A login with `groups: ["platform-team"]`:

```console
$ curl -s -X PUT -H "X-Vault-Token: $BAO_TOKEN" -H "Content-Type: application/json" \
  -d "{\"role\":\"platform-team-cel\",\"jwt\":\"$IDT\"}" \
  http://127.0.0.1:9437/v1/auth/oidc/cel/login | python3 -c "
import json,sys;a=json.load(sys.stdin)['auth']
print('token    :',a['client_token']); print('policies :',a['policies']); print('ttl      :',a['lease_duration'])"
token    : s.L3D8JQn5qM0WdHUMKoFnpZYQ
policies : ['default', 'platform-operator']
ttl      : 2764800
```

**And a login with the wrong group is blocked:**

```console
$ curl -s -X PUT -H "X-Vault-Token: $BAO_TOKEN" -H "Content-Type: application/json" \
  -d "{\"role\":\"platform-team-cel\",\"jwt\":\"$IDT2\"}" \
  http://127.0.0.1:9437/v1/auth/oidc/cel/login
{"errors":["error executing cel program: CEL role 'platform-team-cel' blocked authorization with boolean false return"]}
```

Read that message carefully: it names the **role** and says the role
*blocked authorization*. That is the program doing exactly what it was
written to do — the final expression evaluated to `false` and the login
was refused.

**And if the ID token has no `groups` claim at all**, the failure moves
*inside* the program, and the message points at the exact line that broke:

```console
{"errors":["error executing cel program: CEL auth program failed: failed to evaluate variables: variable[0].is_platform_team: failed to evaluate expression \"claims.groups.exists(g, g == \\\"platform-team\\\")\": no such key: groups"]}
```

`no such key: groups` is the error you will see in the real world if the
Keycloak realm does not emit the `groups` claim — which is exactly the
realm-export problem §6.1 warns about. Two different messages, two
different root causes: *the group is there but does not match* versus
*the group is not there at all*.

> **Warning — the TTL.** `2764800` seconds is **32 days**. A CEL role has
> **no `token_ttl` field** (its read-back exposes only `bound_audiences`,
> `cel_program`, `clock_skew_leeway`, `expiration_leeway`, `message`,
> `name`, `not_before_leeway`), so the token inherits the **system default
> TTL**. A 32-day human session is not acceptable. Two ways to bound it:
> 1. Lower the system default token TTL, or
> 2. Enforce MFA on the login (§7.5), which turns a long token into a
>    short one.
>
> **Verified CEL field names** (probed by provoking type errors): `alias`
> (a protobuf message), `display_name` (string), `policies` (list of
> strings), `num_uses` (int), `period` (duration), `bound_cidrs` (list of
> strings). There is **no** `token_ttl`, `ttl`, `groups`, `subject`,
> `entity`, or `metadata` field. `size(x)` is the length function —
> `len(x)` is **not** supported and fails with
> `no such overload: len`.

### 6.9 VERIFIED / NOT VERIFIED HERE — the honesty table

Keycloak is **not running** in this lab. Here is the exact boundary.

| Step | Status | Evidence |
|---|---|---|
| `bao auth enable oidc` | ✅ **VERIFIED** | Real output above. |
| `oidc_discovery_url` must not contain `.well-known` | ✅ **VERIFIED** | Real 400 above. |
| OpenBao appends `/.well-known/openid-configuration` | ✅ **VERIFIED** | Visible in the DNS-failure message above. |
| A partial `auth/oidc/config` write is rejected | ✅ **VERIFIED** | Real 400 above. |
| `role=` is ignored; `default_role=` is the field | ✅ **VERIFIED** | Read-back showed `default_role` empty after `role=`. |
| `default_role` names a *role*, not a policy | ✅ **VERIFIED** | Real 400 "role 'platform-operator' could not be found". |
| The role path is `auth/oidc/role` (singular) | ✅ **VERIFIED** | 404 for `auth/oidc/roles`. |
| `allowed_redirect_uris` is required | ✅ **VERIFIED** | Real 400 above. |
| `bound_claims` needs the JSON API | ✅ **VERIFIED** | CLI form stored `null`. |
| `bound_claims_type` accepts only `string` | ✅ **VERIFIED** | Real 400 "invalid 'bound_claims_type': array". |
| `auth_url` contains PKCE S256 + nonce + state | ✅ **VERIFIED** | Real URL above. |
| A `role_type: "oidc"` role cannot log in | ✅ **VERIFIED** | Real 400 above. |
| CEL role create / read / evaluate | ✅ **VERIFIED** | Real outputs above. |
| A full OIDC login returning a token with `platform-operator` | ⚠️ **VERIFIED against a local stub, NOT against Keycloak** | See below. |
| **The browser redirect to Keycloak** | ❌ **NOT VERIFIED HERE** | Needs a live Keycloak + browser. |
| **Keycloak issuing the ID token with `groups`** | ❌ **NOT VERIFIED HERE** | The stub minted the token, not Keycloak. |
| **The authorization-code exchange at Keycloak's `/token` endpoint** | ❌ **NOT VERIFIED HERE** | Not exercised. |
| **The `code` → `id_token` → `auth/oidc/oidc/callback` → `auth/oidc/oidc/poll` sequence** | ❌ **NOT VERIFIED HERE** | The endpoints exist in the API; the flow was not run. |
| **Keycloak's `platform-team` group containing `aisha.rahman`** | ❌ **NOT VERIFIED HERE** | Read from the realm export only. |
| **MFA enforced on an OIDC login** | ⚠️ **PARTIAL** | The MFA machinery is verified via AppRole (§7.5); the OIDC-specific wiring is not. |

**How the OIDC login *was* verified.** A local test double served the
OpenID Connect **Discovery document** and a **JWKS**, over
`http://127.0.0.1:18080/realms/meridian-ai`. An RSA keypair was generated
with `openssl`, the public half published as a JWKS, and an ID token
minted in the exact shape Keycloak emits (`iss`, `aud`, `sub`, `email`,
`groups: ["platform-team"]`, `realm_access`, `iat`, `exp`, `nonce`, `azp`,
`sid`). OpenBao fetched the discovery document, fetched the JWKS, verified
the RS256 signature, evaluated the CEL program and issued a token.

**What that proves:** the OpenBao side of OIDC — config parsing, JWKS
fetching, signature validation, CEL claim evaluation, group→policy
mapping, token issuance — works on OpenBao 2.7.1.

**What that does not prove:** anything about Keycloak's own behaviour. The
browser flow, the code exchange, and Keycloak's claim shape are unverified
here. Run the §12 homework against a real Keycloak to close that gap.

---

## 7. MFA

### 7.1 Why a secret store demands MFA

For most applications, password-only login is an inconvenience. For a
secret store it is a **single point of total compromise**:

- An OpenBao token is a **bearer credential**. Whoever holds it *is* the
  workload, until it expires.
- The `platform-admin` policy grants read+write over every secret path. A
  single phished password yields every Gemini key, every database
  password, every certificate.
- There is no "change my password" for a stolen token. You have to
  enumerate every token and revoke it.

MFA fixes the gap that the password leaves: a phished password is no
longer sufficient. This is why §6's OIDC path is the right one for humans
*and* why you must enforce MFA on it.

### 7.2 The `totp` secret engine — generating codes

The engine stores a shared secret and generates 6-digit codes from it. You
supply the key; the engine does the maths.

```console
$ bao secrets enable totp
Success! Enabled the totp secrets engine at: totp/

$ bao write -format=json totp/keys/aisha.rahman \
    key="JBSWY3DPEHPK3PXP" \
    issuer="meridian-ai" \
    account_name="aisha.rahman@meridian-ai.example"
```

The write returns nothing (204). Reading it back shows the metadata and
**not** the secret:

```console
$ bao read -format=json totp/keys/aisha.rahman | python3 -m json.tool
{
    "request_id": "d936c099-d37e-f062-6027-1eac409033e9",
    "lease_id": "",
    "lease_duration": 0,
    "renewable": false,
    "data": {
        "account_name": "aisha.rahman@meridian-ai.example",
        "algorithm": "SHA1",
        "digits": 6,
        "issuer": "meridian-ai",
        "period": 30
    },
    "warnings": null
}
```

And a code:

```console
$ bao read -format=json totp/code/aisha.rahman | python3 -m json.tool
{
    "request_id": "59936880-1329-a925-176a-480c6f539c5a",
    "lease_id": "",
    "lease_duration": 0,
    "renewable": false,
    "data": {
        "code": "244069",
        "expire_time": 1792600740,
        "generated": 1792600729,
        "period": "30s"
    },
    "warnings": null
}
```

> **This engine is not MFA.** It is a code generator for secrets you
> already hold. The MFA method is in the identity store — next section.

### 7.3 TOTP enrollment in the identity store

**Step 1 — configure the method.** The path has **no** `{method_id}` in it;
the server generates the ID:

```console
$ curl -s -X POST -H "X-Vault-Token: $BAO_TOKEN" -H "Content-Type: application/json" \
  -d '{
    "method_name": "aisha.rahman",
    "issuer": "meridian-ai",
    "digits": 6, "period": 30, "algorithm": "SHA1",
    "key_size": 20, "skew": 1, "max_validation_attempts": 3, "qr_size": 200
  }' http://127.0.0.1:9437/v1/identity/mfa/method/totp
{
  "request_id": "3cbd6c1e-25ac-2a2b-214e-73c539e50cd9",
  "lease_id": "",
  "lease_duration": 0,
  "renewable": false,
  "data": {
    "method_id": "0d979295-056d-5a32-55a0-71c91ea5f3aa"
  },
  "wrap_info": null,
  "warnings": null,
  "auth": null
}
```

(The create endpoint returns `warnings: null` — the "Endpoint replaced the
value of these parameters…" warning belongs to the **update** endpoint
below, not to the create.)

The configuration is now visible:

```console
$ curl -s -X LIST -H "X-Vault-Token: $BAO_TOKEN" \
    http://127.0.0.1:9437/v1/identity/mfa/method/totp | python3 -m json.tool
{
    "request_id": "af5cb253-dde2-6ae8-6c38-76623409d4ee",
    "lease_id": "",
    "renewable": false,
    "lease_duration": 0,
    "data": {
        "key_info": {
            "0d979295-056d-5a32-55a0-71c91ea5f3aa": {
                "algorithm": "SHA1",
                "digits": 6,
                "id": "0d979295-056d-5a32-55a0-71c91ea5f3aa",
                "issuer": "meridian-ai",
                "key_size": 20,
                "max_validation_attempts": 3,
                "name": "aisha.rahman",
                "namespace_id": "root",
                "namespace_path": "",
                "period": 30,
                "qr_size": 200,
                "skew": 1,
                "type": "totp"
            }
        },
        "keys": [
            "0d979295-056d-5a32-55a0-71c91ea5f3aa"
        ]
    },
    "wrap_info": null,
    "warnings": null,
    "auth": null
}
```

> **Trap:** the path `identity/mfa/method/totp/{method_id}` is the
> **update** endpoint, not a second create endpoint. Two things follow.
>
> * With an *empty* body it rejects the write instead of silently doing
>   nothing:
>
>   ```console
>   $ curl -s -X POST -H "X-Vault-Token: $BAO_TOKEN" -H "Content-Type: application/json" \
>       -d '{}' http://127.0.0.1:9437/v1/identity/mfa/method/totp/0d979295-056d-5a32-55a0-71c91ea5f3aa
>   {"errors":["issuer must be set"]}
>   ```
>
> * With a body it returns **HTTP 204** and **rewrites** the method. The
>   fields you do not mention are reset to their defaults — in this lab
>   `max_validation_attempts` silently went from `3` back to the default
>   `5`:
>
>   ```console
>   $ curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "X-Vault-Token: $BAO_TOKEN" \
>       -H "Content-Type: application/json" \
>       -d '{"method_name":"aisha.rahman","issuer":"meridian-ai"}' \
>       http://127.0.0.1:9437/v1/identity/mfa/method/totp/0d979295-056d-5a32-55a0-71c91ea5f3aa
>   204
>   ```
>
> Always send the **complete** method body when you update it.
>
> And the `method_id` has to be a **UUID**, not a human name:
> `identity/mfa/method/totp/aisha.rahman` returns
> `404 unsupported path`. The human name goes in `method_name`; the UUID
> is the key.

**Step 2 — generate the secret for the entity.** The admin variant takes
the entity:

```console
$ bao write -format=json identity/mfa/method/totp/admin-generate \
    entity_id="b9a00e52-aaca-6873-6cdc-64bc4f81d9d9" \
    method_id="0d979295-056d-5a32-55a0-71c91ea5f3aa"
{
    "request_id": "49082376-1abc-34a2-e3a1-c175ce324776",
    "lease_id": "",
    "lease_duration": 0,
    "renewable": false,
    "data": {
        "barcode": "iVBORw0KGgoAAAANSUhEUgAAAMgAAADIEAAAAADYoy0BAAAHmUlEQVR4nOyb0Y5kNwhEIdr//2XytBJSucrc3o3S3Cn2xcJQOGOdkrtn8qsqHF8U//xe+EJ8Ib4QX4gvxBfiC/GF+EJ8Ib4QX4gvxBfiC/GF+EJ8Ib4QX4gvxBfiC/GF+EJ8Ib4QX4gv5P++kF+/F7fI/L26RdW9l9VUnet7F6vEDOvCU+F5emAvKuioGhTZsmxZtqy/Z1lztHUwA9HGgpXYhZUR58oINYXpsDxmnv5MTMgXE2LL2m1ZDMMqVVN1NxBtDpl3BZZhCmwW5lEZA3dR04QsJMSW9QbLmkeVghqD2Q4ai85k3nX6ugdqMgUT8gMIsWX9LMtiZvLUBLA3YprpUXVeMwWcy7pMyEsJsWW9wbLm2GZOjStCGQVWMqPDPL64emBlz7MurWNCXkSILWu3Zc0RRvD/7rrHJD9Z6zOzWU9/JiZkFSG+kC+7kKwiO3/4bw6yxh9Ng/XquV1Hr1GH1ZiQH0CILWurZXVgmS10wLEr4pzXdhGhFFgwZTaddfW17sWoIhsmZBMhtqzdltVDQ82wzXyW77ss/gsD6ed5eraqs44JWUiIv8va/V0WwhgxzSC2HecqZRdaYaLP8pNZqNB1dFTJbRPy7YT4lbX1lTVBFU0A66uUWtUn9T2PZ5ivI9Tu5CRYyXpNyBJC/Mra+spC9DTCrIuFNgcWaBq41l2Z6gyZ597Jy1CfwYQsIcSvrDe8shjsLBDnHiyvAydqZVaP+QilzHRYTPRNyBcTYsvaalnaECLUbtXZKFgv02F59t+Qea9nyjoy1fZEwYQsIcQfDLd+MOzIs3yVglr3Pg3WhSdhU3oldk0yfa1PqCtNyBcT4lfW1lcWxmeYM6gxmE7mfVersTNU3XfZdAxUMyELCfEra+sriyEccc4wkCNUF/ZO7GgeqIbKPR9xzmON1kQ1E7KEEL+y3vDKYjBmKoQjzhnsZcqoydZM+elcDJwYcT+DCVlLiC1rq2VlPgNT12ijmOtjb8RZ57PzTKagwmSiCVlCiC1rq2UxPDWkWMm6egYj8+/sZqq5rLIH62LBTmVClhBiy9pqWZlTtBHhya7Od4UIlddTIqb1EUohU2WeTjchX0yILWu3ZUUoMHEX16g2UYg491adMxGq67MpPc96WZcJWUuIf2O4+zeGVWfkMYOVESqTea7JVOueYWq42xUm9WwKZnqedZmQVYT4lfWeVxbmJ/Bmfr47mYhRRTaIGs7Cs01mZZ7zJmQVIbasN1gWRtWzetY76WJWxhRYPat8qoP1VeeMCVlIiD8Y7v5giAB2MBnOiDBGplKOeNbL5maed6vULvayuWxtQtYSYsvaalkIYOa9puq8ZkbBoopsyF20FBbarKpU5WcTTcgSQvzBcPcHw7nJRJxNQM9jylXTSjYXdTKnU3TXZHqVLDUh30uIX1lbX1kMYZZnlbjb1xpzXYlrzPRg+d7F5mI+87xrQpYTYsvabVkRCsmeYfAi2n0dcTaBrjDX6ZW41hPZ7iTPdEzIQkJsWVstq2qKZOZdASurzvlMNR13u1rmPc90sDfiWQ07mwlZRYi/y9r6XVaHtCPJgqHN5mk1pskyTyeyLpaZz8V6E7KKEL+ytr6yGJg9qqZdWmHe1SuZTub9nJjXszLv9SbkFYT4lfX+VxbbRcAxgwq9JmKqEHE/W9VdcxKZz6aYkFWE+JW1+5XFwNSo4u/vcLcr9MhUs7AGIxNS0IUKrAsDz4YnNCFrCfEra+sraw44q2GVPVgXU4h4NmV+zoj7LtZgPWZMyCpC/Mra+srqSDL8I86ZTPUtE/ZGqF6t33czz9bRp7PAXhZds4oUmZCthPiVtfWVhYGQ9kymgppVRkwVIlRNz/TQCqjDFJh+hOo1IQsJsWXttqxMtY2wI7x6F6f0yh6si9Wz0Do9g/VsIsuYkIWE2LLeYFlV50yHNOKex8hUNXo6y0TcZ/WJmed1D5af7JqQVYTYst5gWWgpHVJcoyF8FhPNyaki7l0Yf6LT8yZkFSG2rK2WhQD2TMQZz0wF/qQX63um1+NEvYvBZjEFrI9QvSZkISG2rK2WxYDFYGYSca9HfT0Re6vULur0PMZnar2m75qQhYTYsnZbVsQZz0lGYx5x3mWRqbYnZ+iVveZP5uJ0E7KcEP9d1ta/y5qAOTeKCGUdzBz0xN6FvbqLRea5CxXQ9FivCVlFiC1rq2Vlkg34h/9Lzty4Ij7pQrvoa63ZT8t0MqdzMfSuCfl6QmxZWy1rAmDmHeeqc73W/6wr81xTda/peRa9vnehaZuQtYRsuhBbFloWw5nhyYyL9TJlpoP1TDlC9VapXvyw2dfz05qQhYTYst5gWfNAbDMV4Mwoeh5ruk7PR5y75pGpFHB6z5iQVxBiy/pZlqUR7rtoMhOj0L1aIeKuUHWeO+nNPOuYkFWE2LLeYFlVf1rDrAAxx0zP4xS9y/LsVH261ulzmaYJWUiILWu3ZWUOikglQs1qIlQ+U9WgmbAM6414Vq/XJmQ5If5T0vf8KakJMSE/gBBfiC/EF+IL8YX4QnwhvhBfiC/EF+IL8YX4QnwhvhBfiC/EF+IL8YX4QnwhvhBfiC/EF+IL8YV8zYX8OwAfx2Ogmxf9SwAAAABJRU5ErkJggg==",
        "url": "otpauth://totp/meridian-ai:b9a00e52-aaca-6873-6cdc-64bc4f81d9d9?algorithm=SHA1&digits=6&issuer=meridian-ai&period=30&secret=DB2M2O5TGRPS2ZFEJ7HM6KCR575HTWZJ"
    },
    "warnings": null
}
```

Two outputs, for two clients:

- **`url`** — the `otpauth://` URI. You render it as a QR code; the
  authenticator app reads it. `secret=DB2M2O5TGRPS2ZFEJ7HM6KCR575HTWZJ`
  is the base32 shared secret.
- **`barcode`** — a base64 PNG of the QR code, ready to drop into a
  self-service enrollment page.

> **The entity id matters.** The TOTP secret is attached to the entity you
> pass to `admin-generate`, and the login-enforcement in §7.5 names the
> entities that must present it. Point `admin-generate` at the *same*
> entity the enforcement names — here, the entity the AppRole login
> creates (`b9a00e52-...`, see §7.7) — or the validation in §7.6 fails
> with `MFA secret for method name "..." not present in entity "..."`.

> **Production:** *Deliver the QR as an image, once, over an authenticated
> channel. Never put the `otpauth://` URL in an email, a ticket, or a
> chat message. If it leaks, treat the TOTP secret as compromised and
> re-enroll the user.*

The self-service path is `identity/mfa/method/totp/generate` with
`method_id=…` — but it requires the calling token to have an **entity**,
otherwise:

```console
$ bao write identity/mfa/method/totp/generate method_id="0d979295-056d-5a32-55a0-71c91ea5f3aa"
Error writing data to identity/mfa/method/totp/generate: Error making API request.

URL: PUT http://127.0.0.1:9437/v1/identity/mfa/method/totp/generate
Code: 400. Errors:

* missing entityID
```

The **root token has no entity**, so use `admin-generate` for the
bootstrap case, as above.

### 7.4 `mfa_require` is a silent no-op in OpenBao 2.7.1

Nearly every tutorial says "set `mfa_require=true` on the role". In
OpenBao 2.7.1 that key is **accepted and ignored**:

```console
$ bao write auth/approle/role/mfa-probe mfa_require=true token_policies="ai-harness-service"
Success! Data written to: auth/approle/role/mfa-probe

$ bao read -format=json auth/approle/role/mfa-probe | python3 -m json.tool
{
    "request_id": "8bc98a89-3b38-e352-cee-0e3a58566001",
    "lease_id": "",
    "lease_duration": 0,
    "renewable": false,
    "data": {
        "bind_secret_id": true,
        "local_secret_ids": false,
        "secret_id_bound_cidrs": null,
        "secret_id_num_uses": 0,
        "secret_id_ttl": 0,
        "token_bound_cidrs": [],
        "token_explicit_max_ttl": 0,
        "token_max_ttl": 0,
        "token_no_default_policy": false,
        "token_num_uses": 0,
        "token_period": 0,
        "token_policies": ["ai-harness-service"],
        "token_strictly_bind_ip": false,
        "token_ttl": 0,
        "token_type": "default"
    },
    "warnings": null
}
```

**No `mfa_require` in the output.** It is not there. And it is not a
typo-detection problem — OpenBao **ignores unknown keys entirely** on
this endpoint:

```console
$ bao write auth/approle/role/mfa-probe totally_bogus_key=1
Success! Data written to: auth/approle/role/mfa-probe
```

> **This is the most dangerous class of bug in a secret store: a
> configuration that appears to work and does nothing.** `mfa_require=true`
> on an approle role, on an OIDC role, or on a token role in OpenBao 2.7.1
> is *exactly* as effective as `totally_bogus_key=1`.
>
> **If you find a tutorial saying "set mfa_require on the role":** *it is
> describing HashiCorp Vault, where the key exists on token roles. In
> OpenBao 2.7.1 the enforcement mechanism is `identity/mfa/login-enforcement`.*
> **Always read the role back and confirm the field is there.**

### 7.5 The real mechanism: `identity/mfa/login-enforcement`

An **enforcement** is a named policy: *these entities (or these auth
methods) must present this MFA method to log in.*

```console
$ bao write -format=json identity/mfa/login-enforcement/ai-harness-entity \
    mfa_method_ids="0d979295-056d-5a32-55a0-71c91ea5f3aa" \
    identity_entity_ids="b9a00e52-aaca-6873-6cdc-64bc4f81d9d9"
```

Read it back:

```console
$ bao read -format=json identity/mfa/login-enforcement/ai-harness-entity | python3 -m json.tool
{
    "request_id": "1eddc29e-b446-ee56-a3ef-07ee9df1bebb",
    "lease_id": "",
    "lease_duration": 0,
    "renewable": false,
    "data": {
        "auth_method_accessors": [],
        "auth_method_types": [],
        "id": "72f66132-09ab-c51a-6b4b-f667766dd946",
        "identity_entity_ids": ["b9a00e52-aaca-6873-6cdc-64bc4f81d9d9"],
        "identity_group_ids": [],
        "mfa_method_ids": ["0d979295-056d-5a32-55a0-71c91ea5f3aa"],
        "name": "ai-harness-entity",
        "namespace_id": "root",
        "namespace_path": ""
    },
    "warnings": null
}
```

Four ways to scope an enforcement:

| Scope field | Effect |
|---|---|
| `identity_entity_ids` | These specific entities must present MFA. |
| `identity_group_ids` | Everyone in these groups must present MFA. **This is the one for Meridian AI** — bind it to the `platform-team` group. |
| `auth_method_accessors` | Everyone logging in through this auth mount must present MFA. |
| `auth_method_types` | Everyone logging in through this auth *method type* (e.g. `oidc`) must present MFA. |

> **Production:** *For Meridian AI, scope by `identity_group_ids` (the
> `platform-team` and `security-team` groups) and by
> `auth_method_types=["oidc"]`. Scoping by entity is for machine
> identities; scoping by group is for humans. Never scope by
> `auth_method_types=["approle"]` — you would force TOTP on a container
> that has no phone.*

### 7.6 A real MFA-gated login, start to finish

**Step 1 — the login is refused a token, and hands back a request ID:**

```console
$ bao write -format=json auth/approle/login role_id="$R" secret_id="$S"
A login request was issued that is subject to MFA validation. Please make sure
to validate the login by sending another request to sys/mfa/validate endpoint.

{
    "request_id": "d0d27388-e4fd-f893-3aa2-5dc81668d784",
    "lease_id": "",
    "lease_duration": 0,
    "renewable": false,
    "data": null,
    "warnings": [
        "A login request was issued that is subject to MFA validation. Please make sure to validate the login by sending another request to mfa/validate endpoint."
    ],
    "auth": {
        "client_token": "",
        "accessor": "",
        "policies": null,
        "token_policies": null,
        "identity_policies": null,
        "metadata": null,
        "orphan": false,
        "entity_id": "",
        "lease_duration": 0,
        "renewable": false,
        "mfa_requirement": {
            "mfa_request_id": "186a0297-38be-2cae-7e96-b95f170c562f",
            "mfa_constraints": {
                "ai-harness-entity": {
                    "any": [
                        {
                            "type": "totp",
                            "id": "0d979295-056d-5a32-55a0-71c91ea5f3aa",
                            "uses_passcode": true,
                            "name": "aisha.rahman"
                        }
                    ]
                }
            }
        }
    }
}
```

**Note `client_token: ""`.** No token was issued. The server is holding the
login open, keyed by `mfa_request_id`.

**Step 2 — the user (or the device) supplies the second factor:**

```console
$ curl -s -X PUT -H "X-Vault-Token: $BAO_TOKEN" -H "Content-Type: application/json" \
  -d '{
    "mfa_request_id": "186a0297-38be-2cae-7e96-b95f170c562f",
    "mfa_payload": {"0d979295-056d-5a32-55a0-71c91ea5f3aa": ["813661"]}
  }' http://127.0.0.1:9437/v1/sys/mfa/validate
{
    "request_id": "d4c3d286-1993-1c70-e8b2-63e5c480a210",
    "lease_id": "",
    "lease_duration": 0,
    "renewable": false,
    "data": null,
    "wrap_info": null,
    "warnings": null,
    "auth": {
        "client_token": "s.KUevPDzHxWoaVGuj0tVTcutG",
        "accessor": "BCQfJek6nJTcgNefhHAFbkTw",
        "policies": ["ai-harness-service"],
        "token_policies": ["ai-harness-service"],
        "metadata": {"role_name": "ai-harness-service"},
        "lease_duration": 900,
        "renewable": true,
        "entity_id": "b9a00e52-aaca-6873-6cdc-64bc4f81d9d9",
        "token_type": "service",
        "orphan": true,
        "mfa_requirement": null,
        "num_uses": 0
    }
}
```

**The token is issued, with the right policies and the right TTL.**

**Step 3 — the failure path.** A wrong code:

```console
$ curl -s -X PUT -H "X-Vault-Token: $BAO_TOKEN" -H "Content-Type: application/json" \
  -d '{
    "mfa_request_id": "589e33ac-6895-b9af-a0ba-996350ed8290",
    "mfa_payload": {"0d979295-056d-5a32-55a0-71c91ea5f3aa": ["000000"]}
  }' http://127.0.0.1:9437/v1/sys/mfa/validate
{"errors":["failed to satisfy enforcement ai-harness-entity. error: 2 errors occurred:
	* MFA credentials not supplied or incorrect
	* login MFA validation failed for methodID: [0d979295-056d-5a32-55a0-71c91ea5f3aa]
"]}
```

`max_validation_attempts` (3 in our config) bounds how many wrong codes a
single login attempt tolerates.

> **CLI gotcha — the CLI cannot send `mfa_payload`.** It is a
> map-of-lists, and `bao write` cannot express that. All three of these
> fail:
>
> ```console
> $ bao write -format=json sys/mfa/validate mfa_request_id="$REQ" "mfa_payload.$MID=$CODE"
> Code: 403. Errors:
> * failed to satisfy enforcement ai-harness-entity. error: failed to sanitize MFA creds, 1 error occurred:
> 	* failed to find MFA credentials associated with an MFA method ID 0d979295-…, method name aisha.rahman
>
> $ bao write -format=json sys/mfa/validate mfa_request_id="$REQ" "mfa_payload.0=$CODE"
> Code: 403. Errors:   (same)
> ```
>
> **Use `curl` or an API client for `sys/mfa/validate`.** In production
> this call lives in your OIDC client library, not in a shell.

### 7.7 Why the AppRole login produced a stable entity

Look again at the login response in §4.5: `entity_id:
b9a00e52-aaca-6873-6cdc-64bc4f81d9d9`. Two separate logins of the *same
role* returned the **same** entity:

```console
login 1: entity_id=b9a00e52-aaca-6873-6cdc-64bc4f81d9d9
login 2: entity_id=b9a00e52-aaca-6873-6cdc-64bc4f81d9d9
```

And the entity carries an alias named after the **role_id**:

```console
$ bao read -format=json identity/entity/id/b9a00e52-aaca-6873-6cdc-64bc4f81d9d9
{
    ...
    "aliases": [
        {
            "canonical_id": "b9a00e52-aaca-6873-6cdc-64bc4f81d9d9",
            "id": "a4bf3b51-d47f-e1cb-11e9-8ca1be55ae74",
            "local": false,
            "metadata": {"role_name": "ai-harness-service"},
            "mount_accessor": "auth_approle_b1ff5f46",
            "mount_path": "auth/approle/",
            "mount_type": "approle",
            "name": "6b035535-fa5a-3955-772d-2c5eced94da4"
        }
    ],
    "name": "entity_58f41b0e.root",
    "policies": []
}
```

That stable entity is what makes `identity_entity_ids` enforcement
possible for a machine identity. It is also why `orphan: true` in the
login response is a bit misleading: the token is orphaned from *group*
membership, but the entity is the same one every time.

---

## 8. The GUI for this module

Open <http://127.0.0.1:8200/ui> and sign in with your root token. (The
lab server for this module listens on port 9437; in your own lab use
whichever port you chose.)

### 8.1 Auth methods

> **How these paths were verified.** The OpenBao UI is a browser app, so
> clicking through it is not possible in a terminal. Instead I pulled the
> UI's own JavaScript bundle and read the route → label pairs out of it:
>
> ```bash
> $ curl -s http://127.0.0.1:8200/ui/ \
>     | grep -oE 'assets/[a-zA-Z0-9._-]+\.js' | sort -u
> assets/chunk.475.0d3d12c9247a2b3e141f.js
> assets/chunk.524.db8024bf66127c1bac18.js
> assets/engine-vendor.js
> assets/engine.js
> assets/vendor.js
> assets/vault.js
>
> $ for f in $(curl -s http://127.0.0.1:8200/ui/ \
>       | grep -oE 'assets/[a-zA-Z0-9._-]+\.js' | sort -u); do
>     curl -s "http://127.0.0.1:8200/ui/$f" -o "$(basename $f)"
>   done
> $ cat *.js > all.js
> $ grep -o '"vault.cluster.access[^"]*","[^"]*"' all.js | sort -u
> ```
>
> The labels below are the **exact strings the shipped UI uses**, including
> capitalisation. That matters: the UI section is `Secrets engines`, not
> `Secrets`; and the identity pages live under `Access`, not under a
> top-level `Identity` section. If you go looking for "Identity" in the
> left-hand nav you will not find it — everything identity-related sits
> under **Access**.

| GUI | CLI equivalent |
|---|---|
| **Access → Authentication methods** | `bao auth list` |
| **Access → Authentication methods → AppRole → Configuration** | `bao read auth/approle/config` |
| **Access → Authentication methods → OIDC → Configuration** | `bao read auth/oidc/config` |
| **Access → Authentication methods → OIDC → Login** | The browser button that starts the redirect flow |

> **What the 2.7.1 UI does *not* have — verified, not guessed.** Four
> things were checked against the shipped bundle and the live
> `sys/internal/ui/mounts` endpoints, and all four came back negative:
>
> * The strings **`Role ID`**, **`Secret ID`** and **`Custom Secret ID`**
>   do not appear anywhere in the JavaScript the server serves
>   (`assets/vault.js`, `assets/chunk.*.js`, `assets/vendor.js`,
>   `assets/engine*.js` — 8.3 MB of it).
> * The literal string `AppRole` appears **four times** in that bundle,
>   all four in `assets/vault.js` and nowhere else: once in the *enable an
>   auth method* picker (`{displayName:"AppRole",value:"approle",…}`), twice
>   more in that same wizard's header block
>   (`["AppRole","cpu","Docs: AppRole Authentication",…]`), and once in a
>   documentation blurb. There is no AppRole **role** form anywhere — and
>   the field names `role_id`, `secret_id`, `secret_id_ttl`,
>   `secret_id_num_uses`, `bind_secret_id`, `token_bound_cidrs` and
>   `token_policies` appear **zero** times in the entire bundle.
> * `sys/internal/ui/mounts/auth/approle` returns the mount record with
>   **no `paths` block**, and the UI's tab helper
>   (`vault/helpers/tabs-for-auth-section`) only renders per-type tabs
>   when that block is present. So the AppRole page in 2.7.1 has exactly
>   one tab: **Configuration**.
> * The OIDC section routes in the bundle are `assignments`, `clients`,
>   `keys`, `providers` and `scopes` — those belong to the separate
>   "OpenBao as an OIDC **provider**" feature — and there is no
>   `vault.cluster.access.oidc.roles` route.
>
> **So: creating an AppRole role, reading its `role_id`, minting a
> `secret_id`, destroying a `secret_id_accessor`, and writing an
> `auth/oidc/role` are all CLI-only in 2.7.1.** That is not a gap in your
> knowledge — it is a gap in the product, and it is the best single reason
> to learn the CLI. An AppRole role is a machine credential; the thing
> that owns it is a deployment pipeline, not a browser. (The OIDC *login*
> button is the exception: the browser redirect needs a browser.)

### 8.2 MFA and identity

| GUI | CLI equivalent |
|---|---|
| **Access → Multi-factor authentication** | `bao list identity/mfa/method/totp` |
| **Access → Multi-factor authentication → Enforcement** | `bao list identity/mfa/login-enforcement` |
| **Access → Enforcement → ai-harness-entity** | `bao read identity/mfa/login-enforcement/ai-harness-entity` |
| **Access → Entities** | `bao list identity/entity/name` |
| **Access → Groups** | `bao list identity/group/name` |
| **Access → Entities → aisha.rahman → MFA methods** | `bao list identity/mfa/method/totp` |
| **Access → Leases** | `bao list sys/leases/lookup/<prefix>` |
| **Access → Namespaces** | `bao namespace list` |

> **The tab is called "Enforcement", not "Login Enforcement".** The string
> `Login Enforcement` does not exist in the 2.7.1 bundle; the tab label is
> `Enforcement` and the route behind it is
> `vault.cluster.access.mfa.enforcements`. The *CLI* endpoint is the one
> that says "login-enforcement" — the UI and the API disagree about the
> name, and the UI is the shorter one.
>
> **And the Leases page has no CLI "count".** `sys/leases/count` is a dead
> route on 2.7.1 (it answers 404 on GET and 405 on POST — see
> [Module 04 §6.5](../04-namespaces-entities/README.md)). To count leases
> from the CLI, list the ids under a prefix and count the entries:
> `bao list -format=json sys/leases/lookup/ai/pki`.

### 8.3 What the GUI does *not* expose — and why the CLI is primary

- **`bound_claims` as a map.** The GUI form for the OIDC role does not let
  you build a claim→value map, and the CLI's `field.key=value` form
  silently drops it (§6.6). You need the JSON API either way.
- **CEL programs.** `auth/oidc/cel/role` has no GUI form in 2.7.1. This is
  CLI-and-`curl` territory.
- **`sys/mfa/validate`.** By design — it is part of a login flow, not a
  configuration screen.
- **The exact error text.** The GUI shows a friendly "permission denied";
  the CLI shows the real message, including the `%!w(<nil>)` bug. When you
  are writing a runbook, you want the real text.

> **Production:** *Use the GUI to *see* and the CLI to *change*. The GUI is
> how you confirm that a human can actually operate the thing you built —
> during onboarding, for example.*

---

## 9. The two flows, side by side

### 9.1 The human (Aisha) — OIDC + MFA

```
 Aisha                  Keycloak                  OpenBao
   │                       │                        │
   │  click "Login"        │                        │
   ├──────────────────────>│                        │
   │                       │  authenticate + MFA   │
   │  <── login page ───────┤                        │
   │  enter password+OTP   │                        │
   ├──────────────────────>│                        │
   │                       │  issue id_token        │
   │  <── id_token ────────┤                        │
   │                                               │
   │  POST auth/oidc/oidc/callback (code)          │
   ├──────────────────────────────────────────────>│
   │                                               │ exchange code→id_token
   │                                               │ verify signature vs JWKS
   │                                               │ evaluate CEL role
   │                                               │  → policies: platform-operator
   │  <── OpenBao token (short TTL) ──────────────┤
   │                                               │
   │  ... later, MFA enforcement fires ...         │
   │                                               │
   │  POST auth/oidc/login (id_token)              │
   ├──────────────────────────────────────────────>│
   │                                               │ mfa_requirement returned,
   │                                               │ NO token issued
   │  <── mfa_request_id ──────────────────────────┤
   │  user types 6-digit code                     │
   │  POST sys/mfa/validate                        │
   ├──────────────────────────────────────────────>│
   │                                               │ verify TOTP
   │  <── OpenBao token ───────────────────────────┤
```

### 9.2 The machine (the `ai-harness` container) — AppRole

```
 CI / init container            OpenBao              ai-harness
      │                            │                     │
      │  write auth/approle/role/  │                     │
      │  ai-harness-service/       │                     │
      │  secret-id                 │                     │
      ├───────────────────────────>│                     │
      │  <── secret_id ────────────┤                     │
      │                            │                     │
      │  deliver secret_id via     │                     │
      │  0400 file / tmpfs         │                     │
      ├───────────────────────────────────────────────>│
      │                            │                     │
      │                            │  PUT auth/approle/ │
      │                            │  login             │
      │                            │  <──────────────┐  │
      │                            │                 │  │
      │                            │  token (15m) ───┼──┤
      │                            │                 │  │
      │                            │  GET ai/platform│  │
      │                            │  /data/llm/     │  │
      │                            │  gemini ────────┼─>│
      │                            │                 │  │
```

**Notice the difference in shape.** The human flow is *interactive and
multi-round-trip* — the browser, Keycloak, the callback, the MFA prompt,
the validation. The machine flow is *one round trip and then silence* — one
login, one token, a TTL, and a re-login before the TTL expires.

> **That difference is why you need two auth methods.** A single mechanism
> forces one of the two flows to be awkward. OIDC for a container means
> implementing a browser flow headlessly. AppRole for a human means
> pretending a person is a deployment.

---

## 10. What you learned

- [ ] Why OpenBao's job is "turn a credential into a token with policies"
- [ ] The difference between a human credential and a machine credential —
      and why using one method for both is a design error
- [ ] The six built-in auth methods in OpenBao 2.7.1, and which plugins
      moved to the external catalogue
- [ ] That `totp` is a **secret** engine, not an auth method
- [ ] `role_id` vs `secret_id`: which one is secret, and where each may live
- [ ] Every AppRole role option, and what it costs you
- [ ] The full AppRole login round trip, including `accessor`,
      `metadata.role_name`, and `auth.lease_duration`
- [ ] That `bao write -f auth/approle/login` returns `token`, **not**
      `client_token`
- [ ] That `auth/token/lookup-self` needs the **`update`** capability in
      2.7.1 — the built-in `default` policy's `read` is not enough
- [ ] `token_no_default_policy=true` and what you lose with it
- [ ] `secret_id_ttl`, `secret_id_num_uses`, `secret_id_bound_cidrs`,
      `token_bound_cidrs` — and the real error for each failure
- [ ] That `token_bound_cidrs` is enforced at login **and** at use
- [ ] That `bind_secret_id=false` requires `secret_id_bound_cidrs` in 2.7.1
- [ ] `secret-id-accessor/lookup` and `/destroy` for surgical revocation
- [ ] Why a secret in a container **environment** is a host-level secret
- [ ] The three delivery patterns: CI/CD injection, mounted file, bootstrap
      init container — and their trade-offs
- [ ] That `oidc_discovery_url` must **not** contain `.well-known`
- [ ] That `auth/oidc/config` writes must be complete
- [ ] That `default_role` names a role, not a policy, and that `role=` is
      silently ignored
- [ ] That the OIDC role path is `auth/oidc/role` (singular)
- [ ] That `bound_claims` needs the JSON API, and that
      `bound_claims_type: array` is invalid in 2.7.1
- [ ] What the `auth_url` endpoint produces (PKCE S256, nonce, state)
- [ ] That a `role_type: "oidc"` role cannot log in, and that CEL roles at
      `auth/oidc/cel/role` can
- [ ] That the CEL OIDC token inherits the **system default TTL** (32 days)
- [ ] The two-step TOTP enrollment, and that `method_id` is a UUID
- [ ] That `identity/mfa/method/totp/{method_id}` is the **update**
      endpoint, and that a partial body silently resets the fields you
      omitted
- [ ] That `mfa_require` is a **silent no-op** in OpenBao 2.7.1
- [ ] `identity/mfa/login-enforcement` and its four scoping fields
- [ ] The real MFA-gated login: `mfa_request_id` → `sys/mfa/validate`
- [ ] That the CLI cannot send `mfa_payload`
- [ ] The habit of reading configuration **back** and checking the field is
      there

---

## 11. What's next

You now have two working identity paths and a working second factor. What
you do **not** have yet is a way to *move* a secret from OpenBao into a
running application without a hand-rolled HTTP client, and a way to
*derive* secrets you should not store at all.

[Module 06 — Crypto Tooling](../06-crypto-tooling/README.md) covers
`sys/tools/random` and `sys/tools/hash` (the right way to generate a
secret and the right way to verify a webhook HMAC), response wrapping
(`wrap`/`unwrap` — including the `text=` vs `-text=` trap), the cubbyhole,
and Transit: encrypting data with a key that never leaves OpenBao, so you
can store PII in Postgres without storing the encryption key beside it.

Then [Module 07 — App Integration](../07-app-integration/README.md) takes
the AppRole flow from §5 and finishes it: the client code, the FastAPI
lifespan hook, the Dockerfile that has no secrets in it, and the proof
that the secret is gone from the environment, the filesystem and `/proc`.

---

## 12. Homework

All five tasks are runnable against the OpenBao instance from Module 02
(with `ai/platform` mounted and the five policies from
`lab/policies/*.hcl` applied), plus a real Keycloak for tasks 4 and 5.

**1 — Build a hardened `data-pipeline` AppRole.**
Create `auth/approle/role/data-pipeline` with `token_policies=data-pipeline-service`,
`token_no_default_policy=true`, `token_ttl=15m`, `token_max_ttl=1h`,
`secret_id_ttl=30m`, `secret_id_num_uses=1`, and CIDR pinning. Then prove
all of it:
- log in and show the token's `policies` array contains **only**
  `data-pipeline-service`;
- show that `ai/platform/data/llm/gemini` is `deny`;
- show that a second login with the same `secret_id` fails with
  `invalid role or secret ID`;
- show that `bao token capabilities ai/platform/data/db/postgres` returns
  `read`.

**2 — Demonstrate token expiry and renewal.**
Set `token_ttl=30s` on a scratch role, log in, and:
- show `lease_duration` in the login response is `30`;
- wait 35 seconds and show the token is rejected;
- separately, show `token_max_ttl` capping a renewal: renew a token past
  `token_max_ttl` and show the server refuses.

**3 — Revoke one deployment without touching the role.**
Mint two `secret_id`s, log in with each, then
`secret-id-accessor/lookup` one of them, `secret-id-accessor/destroy` it,
and show that the destroyed one can no longer log in while the other still
works. Then use `auth/token/revoke-accessor` to kill the *issued token*
of the surviving login, and show the app's next read fails with 403.

**4 — Stand up Keycloak and run the real OIDC flow.**
Import `lab/keycloak/realm-export.json` into a Keycloak container. Then:
- confirm the discovery document is reachable at
  `http://<keycloak>:8080/realms/meridian-ai/.well-known/openid-configuration`
  and that the issuer matches what you gave OpenBao;
- write `auth/oidc/config` with the **issuer** URL (not the well-known URL)
  and read it back to confirm `status: valid`;
- open the GUI, log in as `aisha.rahman` (password `Lab-Only-Passw0rd!`),
  and confirm the redirect lands back on your app with a `code`;
- complete the login and show the resulting token's `policies` array
  contains `platform-operator` and **not** `platform-admin`;
- **now** check the `groups` claim in the ID token and confirm whether
  `bound_claims` matched it (it may not — Keycloak sends an array). If it
  did not, switch to `groups_claim` + a CEL role and show the difference.

**5 — Enforce MFA on a human login.**
Enroll TOTP for `aisha.rahman` through the GUI, then create an
`identity/mfa/login-enforcement` scoped to the `platform-team` group.
Log in through the browser flow and prove the login stops at the MFA
prompt — capture the `mfa_request_id` — then complete it with
`sys/mfa/validate` and show you finally get a token. Then, to prove the
point of §7.4: set `mfa_require=true` on the OIDC role, read the role
**back**, and show that `mfa_require` is not in the output.

---

*Meridian AI now has no shared root token in a file. Humans authenticate
through Keycloak with a second factor; machines authenticate with a
single-use `secret_id` that is minted at deploy time and expires in
minutes. The next module makes sure the secrets those identities fetch
arrive without ever touching an environment variable.*
