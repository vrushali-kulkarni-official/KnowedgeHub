# Level 3 — Policies, Tokens & Identity Deep Dive

> **Goal:** you can design an authorisation model for a real organisation —
> dozens of people, dozens of services, multiple teams — and you understand the
> exact mechanics of how a token ends up allowed or denied.

---

## 3.1 The authorisation model, in one picture

```
   ┌──────────────────────────────────────────────────────────────┐
   │  A REQUEST ARRIVES                                          │
   │  method + path + token                                      │
   └───────────────┬──────────────────────────────────────────────┘
                   │
                   ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  1. RESOLVE TOKEN                                            │
   │     token → { policies: [...], entity_id, ttl, ... }         │
   │     (or the request is unauthenticated → only sys/ paths)    │
   └───────────────┬──────────────────────────────────────────────┘
                   │
                   ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  2. RESOLVE PATH                                             │
   │     "secret/data/myapp" → mount "secret/" → kv-v2 plugin    │
   │     canonicalise (lower-case, strip trailing slash)          │
   └───────────────┬──────────────────────────────────────────────┘
                   │
                   ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  3. EVALUATE CAPABILITIES                                    │
   │     required = capability implied by the HTTP method/path   │
   │     granted  = union of all policy rules matching the path  │
   │     if "deny" present → DENY                                │
   │     if required ⊄ granted → DENY                            │
   └───────────────┬──────────────────────────────────────────────┘
                   │
                   ▼
        ALLOW ──▶ plugin executes ──▶ barrier decrypt ──▶ audit ──▶ response
```

Three consequences you should internalise:

1. **Everything is a path**, including `sys/`. There is no "special case" for
   admin endpoints.
2. **The union of policies is the grant.** Two policies both granting `read` on
   the same path = read. There's no "highest priority wins" — only `deny` is special.
3. **Denial is decided before the plugin runs.** A denied request never touches
   the secrets engine, and (crucially) is still audited.

---

## 3.2 Policy syntax — the complete reference

### The shape

```hcl
path "<glob>" {
  capabilities   = ["read", "list"]
  allowed_parameters = { "key" = ["value"] }
  denied_parameters  = { "key" = [] }
  min_wrapping_ttl  = "60s"
  max_wrapping_ttl  = "15m"
  control_group = { ... }          # 2.7.0 feature
}
```

### Path patterns — every form that matters

```hcl
# 1. Exact path
path "secret/data/myapp" { capabilities = ["read"] }

# 2. Prefix glob: everything below
path "secret/data/myapp/*" { capabilities = ["read"] }

# 3. Wildcard within one segment
path "secret/data/app-*" { capabilities = ["read"] }

# 4. "+" = any characters within a SINGLE segment
path "secret/data/+/config" { capabilities = ["read"] }
#    matches secret/data/foo/config
#    matches secret/data/bar/config
#    does NOT match secret/data/foo/bar/config

# 5. Combining
path "secret/data/+/+/secrets" { capabilities = ["read"] }

# 6. Explicit deny always wins over a broader grant
path "secret/data/myapp/root-keys" { capabilities = ["deny"] }
```

> 💡 **The "one path per secret" rule.** If you have `path "secret/data/*"` with
> `read`, then `path "secret/data/myapp/root-keys"` with `deny` — the deny wins
> for that exact path. This lets you write a broad base policy and carve out
> exceptions, which is far more maintainable than 200 narrow policies.

### Capabilities — precise meanings

| Capability | Use it for |
|---|---|
| `create` | First write to a path; also `KV v2` metadata create |
| `read` | Read a value; also KV v2 `data/` reads |
| `update` | Overwrite; also `metadata/`, `undelete/`, `destroy/` |
| `patch` | Merge-patch a JSON object |
| `delete` | Delete an object; KV v2 `metadata/` deletion |
| `list` | List direct children (needs `list` on the *parent* path) |
| `scan` | Recursive list |
| `sudo` | Perform the operation *as the root user*. Extremely powerful — e.g. `sudo` on `sys/raw` lets a token read the encrypted barrier directly. |
| `deny` | Hard deny, overrides wildcard grants |

**`sudo` deserves a warning.** A policy with `sudo` on `sys/raw` can decrypt the
whole storage barrier. Treat `sudo` grants like root.

### `list` needs `list` on the parent

Listing `secret/data/myapp` requires `list` on `secret/data/myapp` (and `read`
on `secret/metadata/myapp` for KV v2 metadata). A common gotcha:

```hcl
# ❌ This does NOT let you list
path "secret/data/myapp" { capabilities = ["read"] }

# ✅ This does
path "secret/data/myapp" {
  capabilities = ["read", "list"]
}
path "secret/metadata/myapp" {
  capabilities = ["read", "list"]
}
```

### Parameter control

```hcl
path "secret/data/app-config" {
  capabilities = ["create", "update"]
  allowed_parameters = {
    "environment" = ["dev", "staging", "prod"]
    "replicas"    = []
  }
  denied_parameters = {
    "debug" = []
  }
}
```

> 💡 This is a genuinely useful, under-used feature: it lets a deployment
> pipeline set environment and replica count, but **not** flip on debug mode.

### Response wrapping TTL control

```hcl
path "secret/data/super-secret" {
  capabilities = ["read"]
  min_wrapping_ttl = "60s"
  max_wrapping_ttl = "5m"
}
```

Prevents an operator from wrapping a response in a token that lives for a year.

### Policy templates — the identity-aware bit

```hcl
# Each user gets a folder named after their own username
path "secret/data/users/{{identity.entity.aliases.auth_userpass_XXXX.metadata.username}}/*" {
  capabilities = ["read", "list"]
}
```

The template is evaluated **at request time** against the *token's* identity.

Available template roots:

| Root | What it is |
|---|---|
| `identity.entity.id` | The entity UUID |
| `identity.entity.name` | Entity name |
| `identity.entity.aliases.<mount_accessor>.metadata.<key>` | Alias metadata |
| `identity.entity.aliases.<mount_accessor>.name` | Alias name (e.g. username) |
| `identity.entity.groups.<id>.name` | Group names |
| `identity.entity.policies` | Policies on the entity |

> 🔒 **2.6.0 security change (GHSA-59w7-v8rr-pr4p):** template values
> containing `+`, `*`, `/` or `,` are **rejected by default**. This prevents an
> attacker who controls a metadata field (e.g. a username) from escaping the
> intended path. The escape hatches
> `allow_wildcards_in_identity_templates`,
> `allow_slashes_in_identity_templates`,
> `allow_commas_in_identity_templates` and
> `allow_globs_in_identity_templates` restore the old behaviour.
>
> **Keep them off.** If a template fails, the fix is sanitising the source
> claim, not enabling a bypass.

### A realistic, production-shaped policy set

```hcl
# ─────────────────────────────────────────────────────────────
# app-readonly.hcl   — the application itself
# ─────────────────────────────────────────────────────────────
path "secret/data/myapp" {
  capabilities = ["read"]
}
path "secret/metadata/myapp" {
  capabilities = ["read", "list"]
}

# ─────────────────────────────────────────────────────────────
# deploy-writer.hcl   — the CI pipeline
# ─────────────────────────────────────────────────────────────
path "secret/data/myapp" {
  capabilities = ["create", "read", "update", "patch"]
}
path "secret/metadata/myapp" {
  capabilities = ["read", "list", "delete"]
}
path "secret/undelete/myapp" {
  capabilities = ["update"]
}
path "secret/destroy/myapp" {
  capabilities = ["update"]
}

# ─────────────────────────────────────────────────────────────
# breakglass-admin.hcl — humans, only via a protected auth path
# ─────────────────────────────────────────────────────────────
path "secret/data/*" {
  capabilities = ["create", "read", "update", "patch", "delete", "list", "scan"]
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
path "sys/policies/acl" {
  capabilities = ["list"]
}
path "auth/token/lookup-self" {
  capabilities = ["read"]
}
path "auth/token/renew-self" {
  capabilities = ["update"]
}
```

> ⚠️ Notice `breakglass-admin` has **no** `sudo`, no `sys/raw`, no
> `auth/token/create`. It can manage secrets but **cannot mint new tokens or
> escalate**. That's a deliberately constrained admin.

### Writing and testing policies safely

```bash
# Write (with a heredoc so the policy is reviewable in git)
bao policy write app-readonly - <<'EOF'
path "secret/data/myapp" { capabilities = ["read"] }
EOF

# Format / lint — NOTE: `policy fmt` operates on a LOCAL FILE and
# overwrites it in place. It does NOT take a policy name, and there is
# no `-check` flag.
bao policy fmt ./policies/app-readonly.hcl
#   (then re-upload: bao policy write app-readonly - < ./policies/app-readonly.hcl)

# Read back
bao policy read app-readonly

# List
bao policy list

# IMPORTANT: policy updates take effect IMMEDIATELY for all attached tokens
bao policy delete app-readonly
```

**Dry-run against a real token:**

```bash
bao token capabilities <token> secret/data/myapp
# Capabilities: [create read update]
```

`bao write -output-policy` shows you what a policy *would* need to be:

```bash
bao kv put -output-policy -mount=secret myapp value=x
# path "secret/data/myapp" { capabilities = ["create", "update"] }
```

---

## 3.3 EGP and RGP (a note of caution)

OpenBao's policy surface has three families:

| Family | Path | Purpose | Status in 2.7.1 docs |
|---|---|---|---|
| **ACL** | `sys/policies/acl/:name` | Path → capabilities. The 99% case. | ✅ Fully documented |
| **EGP** — Endpoint Governing Policy | `sys/policies/egp/:name` | Governs *who may call which endpoint* with *what* payload — e.g. restrict a specific API to specific arguments. | ⚠️ Referenced in the namespace docs and the `/sys/policies` API doc, but **not detailed** in the shipped 2.7.x public doc tree |
| **RGP** — Role Governing Policy | `sys/policies/rgp/:name` | Time-bound, just-in-time access to a role. | ⚠️ Same |

**Honest guidance:** learn ACL thoroughly first — it covers essentially
everything you will build for an AI harness. EGP/RGP are for very specific
"this API must only ever be called with these exact arguments" and "grant
production admin for 30 minutes, then it evaporates" requirements. Read them
directly from the API reference before using them, and **verify against your
specific build** with `bao sys/policies/ -detailed` style calls. I am not going
to invent exact JSON schemas for you and have you discover they're wrong at 2am.

For the "time-bound just-in-time access" need, the **2.7.0 Control Groups**
feature (Level 8) is the modern, documented way to require a second pair of eyes.

---

## 3.4 Tokens — the complete strategy

### Creating tokens properly

```bash
bao token create \
  -policy=app-readonly \
  -ttl=1h \
  -renewable=true \
  -explicit-max-ttl=8h \
  -display-name=myapp-prod \
  -meta=env=prod \
  -meta=owner=platform-team \
  -orphan=true
```

Useful flags:

| Flag | Why |
|---|---|
| `-orphan=true` | Root of its own tree; revoking the parent doesn't kill it (and vice versa) |
| `-display-name` | Human-readable label; shows up in the audit log |
| `-meta k=v` | Custom metadata; also shows in the audit log. **Great for attribution.** |
| `-explicit-max-ttl` | Hard ceiling regardless of mount/system max |
| `-period` | Periodic token (TTL resets on renew) |
| `-batch` | Batch token (no storage, non-renewable) |
| `-no-default-policy` | Drop the implicit `default` policy |
| `-num-uses=N` | Token can be used N times then dies |
| `-cidr="10.0.0.0/8"` | Bind the token to source IP ranges |
| `-explicit-orphan` | (API) |

### The token lifecycle in practice

```
  login ──▶ token (ttl=1h, renewable)
                │
                ├── renew ──▶ extends TTL (bounded by max TTL)
                │
                ├── create child ──▶ child token (inherits parent's tree)
                │
                └── revoke ──▶ token + all children + all leases die
```

```bash
bao token lookup                     # current token
bao token lookup <token>             # specific token
bao token renew                      # renew self
bao token renew -increment=2h        # ask for 2h from NOW
bao token renew -orphan              # renew as an orphan (no parent)
bao token revoke <token>
bao token revoke -accessor <accessor>     # revoke via accessor
bao token revoke -accessor <accessor> -revoke-lease   # also drop its leases
bao token revoke -orphan <accessor>      # revoke only that node of the tree
bao token capabilities <token> secret/data/myapp
```

### Accessors in anger

```bash
# 1. Create a token, keep only the accessor
ACC=$(bao token create -policy=app-readonly -ttl=1h -orphan=true -format=json | jq -r .auth.accessor)
TOKEN=$(bao token create ...)   # give the token to the workload

# 2. Later, in an emergency, kill it — without ever having stored the token
bao token revoke -accessor "$ACC"
```

> 💡 This is the pattern that makes secret *distribution* safe. The workload
> gets the token; your *control plane* stores the accessor. A leaked control
> plane can't authenticate. A leaked token can be revoked instantly.

### Batch tokens for scale

```bash
bao token create -policy=app-readonly -ttl=5m -batch=true
```

* Encrypted blob, **no storage write** → extremely cheap.
* Cannot renew, cannot have children, cannot be root, no accessor, no cubbyhole.
* Leases created by a batch token are bounded by the batch token's TTL.

**Use for:** CI jobs, high-frequency read-only automation, anything issuing
thousands of tokens an hour.

**Don't use for:** long-running services (you can't renew), or anything needing
revocation precision.

### Periodic tokens for long-lived services

```bash
bao token create -policy=app -period=24h -orphan=true
```

The TTL resets to 24h on each renewal. If the service stops renewing, the token
dies within 24h. This is how you give a service a "permanent" credential that
still self-destructs.

> ⚠️ Use a **short** period (1h, not 30d) and renew frequently. The period *is*
> your detection window.

### CIDR binding

```bash
bao token create -policy=app-readonly -ttl=1h -cidr="10.0.0.0/8"
```

If the token is used from outside the CIDR → denied. Great for a service that
should only ever talk to OpenBao from its own subnet. (Root tokens with a TTL
are also affected; non-expiring root tokens are not.)

### Token storage — where does the CLI put it?

| Mechanism | Path |
|---|---|
| Default token file | `~/.vault-token` (override with `BAO_TOKEN_PATH`) |
| Token helper | `bao config -h` → set `BAO_TOKEN_HELPER` to a helper binary |
| Env var | `BAO_TOKEN` (or legacy `VAULT_TOKEN`) |

```bash
# Inspect and change the helper
bao config -h
# or
bao config -output-policy   # see effective CLI config
```

> 🔐 **Production rule:** never use `BAO_TOKEN` in a long-lived shell or in
> CI logs. Use the token helper (e.g. `bao` + `pass`/`vault` helper) or
> `bao login -no-store` and re-login per session.

---

## 3.5 Identity — the graph that scales authorisation

### Entities, aliases, groups

```
  ENTITY (uuid)  ── represents a person or a machine
     │
     ├── ALIAS  ── "how this entity logs in"
     │              e.g. auth method = userpass, name = "alice"
     │              e.g. auth method = oidc,    name = "alice@corp.com"
     │
     ├── GROUP   ── a named bucket of entities, carries policies
     │              e.g. "platform-engineers" → [app-readonly, app-deploy]
     │
     ├── METADATA ── arbitrary key/values
     │              e.g. full_name = "Alice Smith", team = "platform"
     │
     └── POLICIES ── extra policies granted on top of the token's
```

### Why this matters

Without identity, you hardcode `user → policy` in the auth method. With 500
people across 3 teams and 2 IdPs, that's a nightmare of config. With identity:

* the auth method maps a *claim* to a *group name*,
* OpenBao's identity store maps group → policies,
* and a person in both Keycloak and (say) userpass resolves to **one entity**.

### Building it

```bash
# 1. Create a group with policies
bao write identity/group name=platform-engineers \
    policies=app-readonly,app-deploy,audit-reader

# 2. Create an entity (or let OpenBao create it on first login)
bao write identity/entity \
    name="alice" \
    metadata=full_name="Alice Smith" \
    metadata=team="platform" \
    policies=app-readonly

# 3. Get the entity id
ENTITY_ID=$(bao read -field=id identity/entity/name/alice)

# 4. Add the entity to the group
bao write identity/entity/id/$ENTITY_ID groups=platform-engineers
```

### Aliases — linking an IdP identity to an entity

An **alias** binds "a login in a specific auth method" to an entity. The alias
is unique by `(mount_accessor, alias_name)`.

```bash
# Get the accessor of the userpass mount
ACCESSOR=$(bao auth accessor list -format=json | \
  jq -r '.[] | select(.path=="auth/userpass/") | .accessor')

bao write identity/entity-alias \
    name="alice" \
    canonical_id="$ENTITY_ID" \
    mount_accessor="$ACCESSOR"
```

> 💡 The **alias name** each auth method reports:
>
> | Auth method | Alias name |
> |---|---|
> | AppRole | Role ID |
> | JWT/OIDC | configurable via `user_claim` (no default) |
> | Kubernetes | service account UID (default) or name |
> | userpass / LDAP / RADIUS / Kerberos | username |
> | TLS cert | Subject CommonName |
> | Token | `entity_alias` if provided |

### Entity policies are evaluated at request time

This is the important shift. A token's *policy names* are fixed at creation, but
the **contents** of policies, and any policies granted via the entity, are
resolved **on every request**.

```
  Token has policies: ["default"]
  Token has entity_id: <alice's entity>
  Entity has policies: ["app-readonly"]
  Group "platform" has policies: ["app-deploy"]

  Effective capabilities = default ∪ app-readonly ∪ app-deploy
```

So you can **change what a person can do without re-issuing their token** —
just edit the entity or the group. Revoke access instantly.

> 🚨 **Warning from the docs, and it is serious:**
> *"Be careful in granting permissions to non-readonly identity endpoints. If a
> user can modify an entity, they can grant it additional privileges through
> policies. If a user can modify an alias they can login with, they can bind it
> to an entity with higher privileges. If a user can modify group membership,
> they can add their entity to a group with higher privileges."*
>
> Practical rule: **never let an application write to `identity/entity-alias`,
> `identity/entity`, or `identity/group/members` with a capability beyond what
> it strictly needs.** A service that can write group membership is an
> escalation engine.

### Identity in namespaces

Entities and groups are **namespace-scoped**. A child namespace can inherit
policies/identities from its parent. Cross-namespace identity references are
**disabled by default** — and `unsafe_cross_namespace_identity` should stay
disabled (it "allows for unconfined permission sharing").

---

## 3.6 Designing the authorisation model for a real org

Here is a concrete, defensible design for a mid-size enterprise.

### Layer 0 — the root namespace holds only infrastructure

```
root/
├── auth/oidc/           (Keycloak — humans)
├── auth/approle/        (machines)
├── auth/kubernetes/     (K8s workloads)
├── identity/            (entities, groups, policies for humans)
├── sys/                 (cluster config)
└── secret/              (shared platform secrets: db, redis, kafka...)
```

### Layer 1 — namespaces per team

```bash
bao namespace create platform
bao namespace create payments
bao namespace create ai-harness
```

Each team gets its own namespace with its own admin, its own policies, its own
secrets. Root-namespace admins are not automatically admins inside a namespace
(they need a policy that grants it).

### Layer 2 — three policy tiers

| Tier | Who | TTL | Example policies |
|---|---|---|---|
| **Read** | Apps | 1h | `app-readonly` |
| **Operate** | Humans/SRE | 4h | `app-readonly` + `app-writer` + `audit-reader` |
| **Break-glass** | On-call | 30m | `breakglass-admin` (no sudo) |

### Layer 3 — bind tiers to groups

```bash
bao write identity/group name=app-services   policies=app-readonly
bao write identity/group name=sre-team        policies=app-readonly,app-writer,audit-reader
bao write identity/group name=breakglass      policies=breakglass-admin
```

### Layer 4 — bind groups to IdP claims (Keycloak, Level 7)

```bash
bao write auth/oidc/role/sre \
    user_claim=preferred_username \
    bound_claims=groups \
    claim_mappings="{\"sre-team\":{\"groups\":[\"sre-team\"]}}"
```

### The review checklist for any new policy

```
□ Is the path as narrow as possible?
□ Does it grant the minimum capabilities needed?
□ Does it need list/scan? (they leak the shape of your data)
□ Does it need sudo? (almost never)
□ Does it need create/update on a shared path? (someone else can overwrite you)
□ Is there a `deny` carve-out for the sensitive sub-paths?
□ Would this policy still make sense if the app were fully compromised?
□ Is it scoped to one namespace?
```

> 💡 **The "fully compromised" test** is the real bar. If the app is popped, what
> can the attacker reach? With `app-readonly` scoped to `secret/data/myapp`, they
> get one app's secrets. With `path "secret/data/*"`, they get everything.
> Design for the worst case, because the worst case *is* the case.

---

## 3.7 Auditing who did what

```bash
# 1. List all active token accessors
bao auth accessor list

# 2. Look up one
bao token lookup -accessor <accessor>

# 3. Revoke one
bao token revoke -accessor <accessor>
```

In the audit log, the fields that matter:

| Field | Use |
|---|---|
| `request.path` | What was touched |
| `request.operation` | read / update / delete / list |
| `request.remote_address` | Where from |
| `request.client_token_accessor` | Which token (HMAC'd) |
| `auth.display_name` | Token's display name |
| `auth.policies` | Effective policies at the time |
| `auth.entity_id` | Which identity |
| `time` | When |
| `error` | Empty = success |

> 🔍 **In 2.7.0, `X-Vault-Index` is returned on write operations**, giving you
> an opaque index you can use to force read-after-write consistency (see
> Level 6, "Consistency"). Also note: 2.7.0 fixed a bug where malformed
> request data could leak into audit logs in plaintext
> (GHSA-8xxq-mq9m-xmhw) — another reason to run 2.7.1.

---

## 3.8 Level 3 checkpoint

1. Why is the effective policy a *union* rather than a priority system? What is
   the one exception?
2. You have `path "secret/data/*" { capabilities=["read"] }` and
   `path "secret/data/x" { capabilities=["deny"] }`. Can you read `secret/data/x`?
3. What does `sudo` on `sys/raw` let a token do?
4. When do you want `-orphan=true`?
5. Why is the accessor safer to store than the token?
6. What's the difference between a batch token and a periodic token?
7. Your team has 300 engineers. Why would you use identity groups instead of
   `token_policies` in the auth method?
8. Why is write access to `identity/group/members` dangerous?
9. What happens to an already-issued token's effective permissions when you add
   a policy to a group its entity is in?

**Next → [Level 4: SECRET-ENGINES.md](04-SECRET-ENGINES.md)** — KV v2 in depth,
Transit, PKI, dynamic database credentials, TOTP, SSH, cubbyhole, wrapping.

---

## 3.9 Scratchpad

```
Policy verbs:      create read update patch delete list scan sudo deny
Templating roots:  identity.entity.{id,name,aliases,groups,metadata}
Accessors:         safe to store/log; can lookup+renew+revoke, cannot auth
Batch token:       b.  no storage, no renew, no revoke, no children
Periodic token:    period=1h → TTL resets on renew; dies if you stop
Entity policies:   evaluated at REQUEST time (not token creation time)
DANGER:            identity/entity*, entity-alias, group/members = escalation
```
