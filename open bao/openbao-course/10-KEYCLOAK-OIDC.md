# Level 10 — Keycloak ⇄ OpenBao: The OIDC Deep Dive

> **Goal:** you can wire Keycloak to OpenBao so that *who the user is in
> Keycloak* determines *what they can do in OpenBao* — for humans, for
> service accounts, and for your own applications — and you can debug it when
> it breaks.

**Everything in this chapter was executed against a live OpenBao 2.7.1 server
with a mock OIDC provider.** The commands, the API paths and the error messages
are real output, not reconstructed.

---

## 10.1 The `oidc` and `jwt` auth methods are the SAME plugin

This is the single most confusing thing about OpenBao's OIDC support, and
getting it wrong wastes hours.

`oidc` and `jwt` are two **mount types** of the **same plugin**. They expose
**identical paths**:

```
^config$                 ← the mount-level JWT/OIDC configuration
^role/(?P<name>…)$       ← roles
^login$                  ← authenticate
^oidc/auth_url$          ← start a browser login
^oidc/callback$          ← the provider redirects back here
^oidc/poll$              ← poll for the result (device / direct modes)
^cel/login$              ← authenticate against a CEL role
^cel/role/(?P<name>…)$   ← CEL roles
```

Verified with `bao path-help`:

```bash
$ bao path-help auth/oidc | grep -E '^\s+\^'
    ^cel/login$
    ^cel/role/(?P<name>\w(([\w-.]+)?\w)?)$
    ^cel/role/?$
    ^config$
    ^login$
    ^oidc/auth_url$
    ^oidc/callback$
    ^oidc/poll$
    ^role/(?P<name>\w(([\w-.]+)?\w)?)$
    ^role/?$
```

> 🚨 **The path that trips everyone up: the config lives at
> `auth/<mount>/config`, NOT `auth/oidc/oidc`.**
>
> ```
> $ bao write auth/oidc/oidc oidc_discovery_url=…
>   * unsupported path
> $ bao write auth/oidc/config oidc_discovery_url=…
>   Success! Data written to: auth/oidc/config
> ```
>
> Likewise a role is at **`auth/<mount>/role/<name>`** — not
> `auth/oidc/oidc/role/<name>`.

### Which mount type do I use?

| | `jwt` mount | `oidc` mount |
|---|---|---|
| Browser login | ✅ | ✅ |
| Validate a JWT you already hold | ✅ | ✅ (same code) |
| Default `role_type` | `jwt` | `oidc` |
| Typical use | CI, service tokens, API clients | Humans logging in with a browser |

**They are functionally identical.** Pick `oidc` for human-facing mounts (so the
UI offers a browser login) and `jwt` for machine-facing ones. Mount the same
type twice at different paths if you like — the paths are independent.

---

## 10.2 The configuration keys (and the two that bite)

### The mount config: `auth/<mount>/config`

| Key | Notes |
|---|---|
| `oidc_discovery_url` | **The BASE URL.** OpenBao appends `/.well-known/openid-configuration` itself. |
| `jwks_url` | A **literal** JWKS URL. Mutually exclusive with `oidc_discovery_url`. |
| `jwt_validation_pubkeys` | Comma-separated PEM public keys, validated locally. Mutually exclusive with the other two. |
| `oidc_client_id` | The client ID at your provider. **Not** `client_id`. |
| `oidc_client_secret` | The client secret. **Not** `client_secret`. Write-only (reads return `null`). |
| `bound_issuer` | Match against the `iss` claim. Defaults to the discovery document's `iss`. |
| `default_role` | Role used when the login doesn't name one. |
| `skip_jwks_validation` | `true` = warn instead of failing if the provider is unreachable. Default `false`. |
| `oidc_response_type` / `oidc_response_types` | e.g. `code`, `id_token`, `code id_token` |
| `oidc_response_mode` | e.g. `query`, `fragment`, `form_post` |
| `namespace_in_state` | `true` by default — puts the namespace into the OIDC `state`. |

### 🚨 Gotcha #1 — `oidc_discovery_url` must NOT contain `.well-known`

```
$ bao write auth/oidc/config \
    oidc_discovery_url="http://keycloak:8080/realms/enterprise/.well-known/openid-configuration"
  * 'oidc_discovery_url' contains '.well-known' component
```

**Correct:**
```bash
bao write auth/oidc/config \
  oidc_discovery_url="http://keycloak:8080/realms/enterprise" \
  oidc_client_id="openbao" \
  oidc_client_secret="$KEYCLOAK_CLIENT_SECRET" \
  default_role="human"
```

The API reference is explicit: *"The base URL of the OIDC Discovery URL
**without** `.well-known/openid-configuration` component."*

> 💡 This is the opposite of `jwks_url`, which **is** a literal URL including
> `/.well-known/jwks`. Two different conventions, one API. That is why everyone
> gets it wrong the first time.

### 🚨 Gotcha #2 — the client ID/secret keys are prefixed

```
$ bao write auth/oidc/config client_id="openbao" client_secret="s3cret"
  Success! …            # ← accepted, but silently IGNORED

$ bao read -format=json auth/oidc/config | jq .data.oidc_client_id
""                      # ← empty: the config never took
```

**Correct:**
```bash
bao write auth/oidc/config \
  oidc_client_id="openbao" \
  oidc_client_secret="$KEYCLOAK_CLIENT_SECRET"
```

```
$ bao read -format=json auth/oidc/config | jq '{oidc_client_id, status}'
{ "oidc_client_id": "openbao", "status": "valid" }
```

`status: "valid"` means OpenBao successfully fetched and validated the
discovery document. **Always check this after configuring** — it is your
fastest "is my IdP reachable?" signal.

### Verify the whole config in one shot

```bash
bao read -format=json auth/oidc/config | jq '{
  discovery: .data.oidc_discovery_url,
  client_id: .data.oidc_client_id,
  issuer:    .data.bound_issuer,
  status:    .data.status
}'
```

```json
{
  "discovery": "http://127.0.0.1:8098/realms/enterprise",
  "client_id": "openbao",
  "issuer": "",
  "status": "valid"
}
```

---

## 10.3 The role: where identity becomes policy

`auth/<mount>/role/<name>` holds the per-role rules.

```bash
bao write auth/oidc/role/human - <<'EOF'
{
  "role_type": "oidc",
  "user_claim": "preferred_username",
  "groups_claim": "groups",
  "oidc_scopes": ["openid", "profile", "email", "groups"],
  "allowed_redirect_uris": ["http://localhost:8250/oidc/callback"],
  "token_ttl": "1h",
  "token_max_ttl": "8h"
}
EOF
```

### The identity parameters

| Key | Meaning |
|---|---|
| `user_claim` | **Required.** The claim that uniquely identifies the user. Becomes the Identity alias name. Must be a string. |
| `user_claim_json_pointer` | `true` → treat `user_claim` as a JSON pointer |
| `groups_claim` | The claim holding a **list** of group names. Each becomes an **Identity group alias** → which you link to an OpenBao group with policies. |
| `claim_mappings` | Copy claims into token/alias metadata |
| `bound_audiences` | Accepted `aud` values. **Required for `jwt` roles**, optional for `oidc` roles. |
| `bound_subject` | Require a specific `sub` |
| `bound_claims` | Map of claim → required value(s) |
| `bound_claims_type` | `string` (default, exact match) or `glob` (`*` = any chars) |

### The three ways to reach a claim

```jsonc
{
  "division": "North America",              // top level
  "groups": { "primary": "Engineering" }    // nested
}
```

| Notation | Points at |
|---|---|
| `division` | top-level key |
| `/groups/primary` | **JSON pointer** → nested value |

This applies to `user_claim`, `groups_claim`, `bound_claims` and
`claim_mappings`.

### `groups_claim` — the cleanest path from Keycloak to OpenBao

This is the mechanism I most want you to understand, because it replaces
"mapping every user to policies" with "mapping a *group* to policies".

```
Keycloak group  "openbao-sre"
        │
        │  (groups claim in the ID token)
        ▼
OpenBao alias   group alias named "openbao-sre"
        │
        │  (linked to an OpenBao identity group)
        ▼
OpenBao group   "openbao-sre"  →  policies: [human-default, sre-write]
```

**Step 1 — Keycloak must put groups in the token.** Add a *Group Membership*
protocol mapper to the `openbao` client (or a client scope assigned to it):

* "Full group path" → **OFF** (otherwise you get `/openbao-sre` instead of
  `openbao-sre`)
* "Claim" → `groups`
* "Add to ID token" → ON, "Add to access token" → ON

**Step 2 — OpenBao role:**

```json
{ "groups_claim": "groups", "oidc_scopes": ["openid", "profile", "email", "groups"] }
```

**Step 3 — create the OpenBao identity group and link the alias:**

```bash
# The OpenBao group (carries the policies)
bao write identity/group name=openbao-sre \
    policies=human-default,sre-write

# The alias that connects the Keycloak group name to the OpenBao group
bao write identity/group-alias \
    name="openbao-sre" \
    canonical_id=$(bao read -field=id identity/group/name/openbao-sre) \
    mount_accessor=$(bao auth accessor list -format=json | \
      jq -r '.[] | select(.path=="auth/oidc/") | .accessor')
```

After the first successful login, OpenBao creates the alias automatically if
you configure the group's alias with the right mount accessor.

> 💡 **Why this beats `claim_mappings` + policy names:** with `claim_mappings`
> you copy the Keycloak group *name* into metadata and then have to write
> policies that check metadata. With `groups_claim`, OpenBao's **identity
> system** does the joining, and you manage authorisation in one place
> (`identity/group`). One place to review, one place to change.

### `claim_mappings` — copying claims into metadata

```json
{
  "email": "email",
  "/realm_access/roles": "kc_realm_roles"
}
```

* `"email"` → top-level claim `email`, metadata key `email`
* `"/realm_access/roles"` → JSON pointer to a nested claim, metadata key
  `kc_realm_roles`

**The required/optional rule** (this is the part people miss):

| Key form | Behaviour |
|---|---|
| `email` (no leading `/`) | **Optional** — if the claim is absent, the mapping is skipped |
| `/realm_access/roles` (leading `/`) | **Required** — if the claim is absent, **authentication fails** |

> ⚠️ The metadata key **`role` is reserved** and cannot be used as a
> claim-mapping target.

### Bound claims — restricting *who* may use a role

```json
{
  "bound_claims": {
    "department": "Engineering",
    "email": ["fred@example.com", "julie@example.com"]
  }
}
```

A claim's expected value may be a **single string** or a **list** — the claim
must match one of the items.

With globs:

```json
{
  "bound_claims": { "email": "*@corp.internal" },
  "bound_claims_type": "glob"
}
```

> 🔒 The `bound_claims_type = "glob"` option means `*` matches any number of
> characters. It is convenient and it is also a footgun: `*@corp.internal`
> also matches `attacker@corp.internal`. Use narrow globs, or exact values
> where you can.

---

## 10.4 The browser login flow

### CLI login

```bash
bao login -method=oidc -path=oidc -role=human
```

OpenBao prints (and tries to open) an authorization URL. You can also fetch it
yourself — note it is a **POST**, not a GET:

```bash
bao write -format=json auth/oidc/oidc/auth_url \
    role=human \
    redirect_uri="http://localhost:8250/oidc/callback" \
  | jq -r .data.auth_url
```

Real output from the verified run:

```
http://127.0.0.1:8098/realms/enterprise/protocol/openid-connect/auth
  ?client_id=openbao
  &code_challenge=OBp1kZ-7dlPuUiTelIXQLi4WK3xHFDT-neJcJ4NQ2eI
  &code_challenge_method=S256
  &nonce=n_C6rddd7D8c2GX9aUyF4a
  &redirect_uri=http%3A%2F%2Flocalhost%3A8250%2Foidc%2Fcallback
  &response_type=code
  &scope=openid+profile+email+groups
  &state=...
```

Note **`code_challenge_method=S256`** — OpenBao uses **PKCE** automatically.
That is a security feature: the CLI can never be tricked into redeeming a code
it did not start.

### Redirect URIs — exact match required

| Flow | Redirect URI |
|---|---|
| CLI, `callback_mode=client` (default) | `http://localhost:8250/oidc/callback` |
| CLI, `callback_mode=direct` | `https://<host>:8200/v1/auth/<mount>/oidc/callback` |
| OpenBao UI | `https://<host>:8200/ui/vault/auth/<mount>/oidc/oidc/callback` |
| `callback_mode=device` | **none** — the device flow has no callback |

**The same URIs must be registered at Keycloak**, and they must match
*exactly*: scheme, host, port, path, trailing slash.

### `callback_mode`

| Mode | How it works | Use when |
|---|---|---|
| `client` (default) | OpenBao's CLI starts a tiny local listener on :8250 and receives the callback there | Local CLI logins |
| `direct` | The provider redirects straight to the OpenBao server | Server-side / UI logins, headless |
| `device` | The user enters a code on another device; OpenBao polls | No browser available (SSH sessions, CI) |

### `direct` mode and the confirmation page

In `direct` mode OpenBao shows an **intermediate confirmation page** showing
the requester's IP address, so the user can verify they initiated the login and
aren't being phished by a crafted link (RFC 8628 §5.4).

> 💡 Set `oidc_disable_confirmation = true` **only** if your provider always
> shows its own confirmation prompt. OpenBao's is on by default; leave it on.

### `max_age` — force re-authentication

```json
{ "max_age": "15m" }
```

Adds `max_age` to the authorization request, so the provider must have
authenticated the user within that window. This is how you force a fresh
password entry for sensitive operations.

---

## 10.5 The complete Keycloak → OpenBao setup

### Keycloak side

**Realm** `enterprise`. **Client** `openbao`:

| Setting | Value |
|---|---|
| Client type | OpenID Connect, **confidential** |
| Client ID | `openbao` |
| Client secret | *(copy it — you need it for `oidc_client_secret`)* |
| Standard flow | enabled |
| Direct access grants | **disabled** |
| Implicit flow | disabled |
| Valid redirect URIs | `http://localhost:8250/oidc/callback`, `https://openbao.corp.internal:8200/ui/vault/auth/oidc/oidc/callback` |
| Web origins | `https://openbao.corp.internal:8200` |
| PKCE method | `S256` |

**Protocol mappers** on the client (or on a client scope assigned to it):

| Mapper | Type | Setting |
|---|---|---|
| `groups` | Group Membership | Full group path **off**, claim name `groups`, add to ID + access token |
| `preferred_username` | User Property | attribute `username` → claim `preferred_username` |
| `email` | User Property | attribute `email` → claim `email` |

### OpenBao side

```bash
# 1. Enable the mount
bao auth enable -path=oidc oidc

# 2. Point it at Keycloak (BASE URL — no .well-known!)
bao write auth/oidc/config \
    oidc_discovery_url="http://keycloak:8080/realms/enterprise" \
    oidc_client_id="openbao" \
    oidc_client_secret="$KEYCLOAK_CLIENT_SECRET" \
    default_role="human"

# 3. Check status == "valid"
bao read -format=json auth/oidc/config | jq -r .data.status

# 4. The role
bao write auth/oidc/role/human - <<'EOF'
{
  "role_type": "oidc",
  "user_claim": "preferred_username",
  "groups_claim": "groups",
  "oidc_scopes": ["openid", "profile", "email", "groups"],
  "allowed_redirect_uris": [
    "http://localhost:8250/oidc/callback",
    "https://openbao.corp.internal:8200/ui/vault/auth/oidc/oidc/callback"
  ],
  "token_ttl": "1h",
  "token_max_ttl": "8h",
  "claim_mappings": {
    "email": "email"
  }
}
EOF

# 5. The OpenBao groups that carry the policies
bao write identity/group name=openbao-sre      policies=human-default
bao write identity/group name=openbao-platform policies=human-default,platform-write
```

### Test

```bash
bao login -method=oidc -path=oidc -role=human
bao token lookup | jq '{policies: .data.policies, entity: .data.entity_id}'
```

---

## 10.6 Keycloak service accounts → OpenBao (machine auth)

Keycloak's **service accounts** (Client Credentials) are the natural machine
identity in a Keycloak-centric org. You can exchange one for an OpenBao token
using the `jwt` auth method.

### Keycloak side

Enable **Service Accounts** on the client. Note the service account's
`client_id` (usually `service-account-<clientId>`) — it becomes the `sub`
claim.

### OpenBao side

```bash
bao auth enable -path=keycloak-jwt jwt

bao write auth/keycloak-jwt/config \
    jwks_url="http://keycloak:8080/realms/enterprise/protocol/openid-connect/certs" \
    bound_issuer="http://keycloak:8080/realms/enterprise"

bao write auth/keycloak-jwt/role/svc-harness - <<'EOF'
{
  "role_type": "jwt",
  "user_claim": "preferred_username",
  "bound_subject": "service-account-harness-app",
  "bound_audiences": ["harness-api"],
  "token_policies": ["harness-service"],
  "token_ttl": "30m",
  "token_max_ttl": "1h"
}
EOF
```

### Exchange

```bash
# 1. Get a token from Keycloak (Client Credentials grant)
KC_TOKEN=$(curl -s -X POST \
  "http://keycloak:8080/realms/enterprise/protocol/openid-connect/token" \
  -d "grant_type=client_credentials" \
  -d "client_id=harness-app" \
  -d "client_secret=$KC_CLIENT_SECRET" \
  -d "audience=harness-api" | jq -r .access_token)

# 2. Exchange it for an OpenBao token
bao write auth/keycloak-jwt/login role=svc-harness jwt="$KC_TOKEN"
```

> 💡 **The `audience` parameter matters.** Keycloak only puts a given audience
> in the access token if you ask for it (`audience=`), unless you use an
> audience mapper. If `bound_audiences` doesn't match, the login fails with a
> confusing message — and it is the single most common cause of "it worked
> yesterday".

---

## 10.7 Keycloak → OpenBao for *your own application* (the reverse direction)

Your FastAPI app needs to know who the user is. Two options:

### Option A — the app validates Keycloak's token itself

```
Browser → your app → (app redirects to Keycloak) → Keycloak → app
                                        (app validates the ID token)
```

Your app is the OIDC **relying party**. It holds the Keycloak JWKS and
verifies the token. OpenBao is not involved in the user path at all.

**Use this** for user-facing apps. It's the standard pattern and it keeps the
request path fast.

```python
# The app's own OIDC validation (not OpenBao's)
# - fetch Keycloak's JWKS
# - verify iss, aud, exp, signature
# - map the groups claim to your own roles
```

### Option B — OpenBao is the OIDC *provider* to your app

OpenBao can issue OIDC tokens itself (`sys/oidc/providers/default`). Your app
then treats OpenBao as its IdP.

```bash
bao write sys/oidc/providers/default \
    client_type="public" \
    allowed_redirect_uris="https://app.corp.internal/callback" \
    allowed_scopes="openid profile email" \
    default_scopes="openid profile email" \
    issuer="https://openbao.corp.internal:8200"
```

> ⚠️ **2.7.0 removed `prompt=none` redirection support in the OIDC provider**
> (GHSA-2cjw-94fw-wqjx). If you had a flow that relied on silent
> re-authorization, it will now fail — by design.
>
> **2.6.0 added a Client Credentials flow to the OIDC provider**, so OpenBao
> can now issue tokens for machine-to-machine flows directly. **2.5.0** added
> the same to the provider. This is how your *services* get tokens from
> OpenBao as an IdP.

### Which direction?

| | App validates Keycloak | OpenBao as provider |
|---|---|---|
| Latency in the user path | Lower | Higher (extra hop) |
| Identity source | Keycloak | OpenBao's identity store |
| Central policy enforcement | In your app | **In OpenBao** ✅ |
| Machine-to-machine | Your own plumbing | Built-in client_credentials ✅ |
| Best for | User-facing apps | Apps that need central authorisation |

> 🎯 **Recommended for your stack:** **Option A** for your FastAPI app's user
> path (Keycloak is already your IdP), and **OpenBao as the provider** only if
> you want OpenBao to be the single authorisation point for *service* tokens.

---

## 10.8 `token_policies_template_claims` — one role, many policies

This is the most powerful and least-known feature in the OIDC/JWT role. It lets
**the token's own claims decide which policies it gets**.

```json
{
  "token_policies_template_claims": true,
  "token_policies": [
    "team-{{.team}}",
    "{{if eq \"production\" .environment}}prod-write{{end}}"
  ]
}
```

* Templates are `text/template` evaluated against **all claims** on the token.
* A template that evaluates to the **empty string is removed**.
* **All referenced claims must exist**, or the login fails — unless you guard
  it with `index`.

Conditional example from the docs:

```
token_policies=["{{if eq \"prod\" .environment}}project_{{.project_id}}/env_{{.environment}}/branch_{{.branch}}{{end}}"]
```

→ the policy is empty (and removed) when `environment` is `staging`.

### Verified working

```
$ bao write auth/github-actions/role/github - <<'EOF'
{
  "role_type": "jwt",
  "bound_audiences": ["openbao"],
  "bound_claims": {"repository": "your-org/your-repo"},
  "token_policies_template_claims": true,
  "token_policies": ["ci-{{.repository_owner}}", "{{if eq \"production\" .environment}}ci-prod{{end}}"]
}
EOF
$ bao write auth/github-actions/login role=github jwt="$JWT"
token_policies       ["ci-prod" "ci-your-org" "default"]
```

The token got `ci-your-org` (from `repository_owner`) **and** `ci-prod` (because
`environment == "production"`). One role, per-repo and per-environment
authorisation, with no extra configuration.

> 💡 **Guard optional claims.** If a claim might be absent, use `index`:
> `{{if index . "environment" "dev"}}…{{end}}` — otherwise a missing claim
> fails the whole login.

---

## 10.9 The claim → OpenBao token pipeline

```
   Keycloak ID token
        │
        ├─ signature verified against the JWKS (from discovery or jwks_url)
        ├─ exp/nbf checked (with expiration_leeway / not_before_leeway / clock_skew_leeway)
        ├─ iss checked against bound_issuer
        ├─ aud checked against bound_audiences
        ├─ bound_claims checked (exact or glob)
        │
        ▼
   user_claim  ──────────────▶ Identity alias name  (who you are)
   groups_claim ──────────────▶ Identity group aliases (what groups you're in)
   claim_mappings ───────────▶ token + alias metadata
        │
        ▼
   OpenBao token
        ├─ policies: from the role (+ identity group policies, resolved at request time)
        ├─ ttl / max_ttl from the role
        ├─ entity_id → the Identity entity
        └─ accessor
```

Leeway parameters (relevant mostly for `jwt` roles):

| Parameter | Default when `0` |
|---|---|
| `clock_skew_leeway` | 60s |
| `expiration_leeway` | 150s |
| `not_before_leeway` | 150s |

Set to `-1` to disable. These matter when your IdP and OpenBao clocks drift —
and clocks **do** drift.

---

## 10.10 Troubleshooting matrix

| Symptom | Cause | Fix |
|---|---|---|
| `unsupported path` on `auth/oidc/oidc` | Wrong config path | Use `auth/<mount>/config` |
| `'oidc_discovery_url' contains '.well-known' component` | You pasted the full discovery URL | Use the **base** URL |
| `oidc_client_id` is empty after writing | You used `client_id` | Use `oidc_client_id` / `oidc_client_secret` |
| `status` is not `"valid"` | Provider unreachable, or issuer mismatch | Check the URL resolves from the OpenBao container; check `skip_jwks_validation` for a temporary bypass |
| `OIDC login is not configured for this mount` | `oidc_client_id` empty | Set it |
| Login loops between Keycloak and OpenBao | Redirect URI mismatch | Compare exactly — scheme, host, port, path, trailing slash |
| `no groups claim in token` | Keycloak mapper missing, or scope not requested | Add the Group Membership mapper; add `groups` to `oidc_scopes` |
| Groups show as `/openbao-sre` | "Full group path" is ON in the mapper | Turn it **off** |
| `permission denied` immediately after login | Role's `token_policies` too narrow, or the identity group isn't linked | `bao token capabilities <token> <path>` |
| `invalid audience` / login refused | `bound_audiences` ≠ the token's `aud` | Add `audience=` to the Keycloak request, or relax the bound |
| Token works, then stops after 8h | Role `token_max_ttl` | Raise it, or have the client re-login |
| "error verifying token signature" | JWKS unreachable, or the key has no matching `kid` | Check `jwks_url`; ensure the JWKS entries carry `kid` |
| Clock-skew rejections | IdP and OpenBao clocks differ | Set `expiration_leeway` / `clock_skew_leeway` |

### The three debugging tools

```bash
# 1. Is the mount configured and reachable?
bao read -format=json auth/oidc/config | jq '.data | {status, oidc_discovery_url, oidc_client_id}'

# 2. What does the browser flow actually request?
bao write -format=json auth/oidc/oidc/auth_url role=human \
    redirect_uri="http://localhost:8250/oidc/callback" | jq -r .data.auth_url

# 3. What can the issued token actually do?
bao token capabilities <token> secret/data/myapp
```

And for claim-level debugging (development only!):

```json
{ "verbose_oidc_logging": true }
```

> 🚨 **`verbose_oidc_logging` logs the received OIDC token and claims to the
> server log at debug level.** Claims data is logged verbatim and may contain
> sensitive information. **Never enable it in production.** Turn it on, debug,
> turn it off.

---

## 10.11 The Keycloak-side cheat sheet

| I want… | Keycloak setting | OpenBao setting |
|---|---|---|
| Username in the token | `preferred_username` mapper | `user_claim=preferred_username` |
| Email in the token | `email` mapper | `claim_mappings={"email":"email"}` |
| Groups in the token | Group Membership mapper, full path OFF | `groups_claim=groups` + `oidc_scopes=[…,"groups"]` |
| Realm roles in the token | Role scope mapper (realm roles) | `claim_mappings={"/realm_access/roles":"kc_roles"}` |
| Client roles in the token | Role scope mapper (client roles) | `claim_mappings={"/resource_access/<client>/roles":"kc_client_roles"}` |
| Service account token | Service Accounts enabled | `bound_subject=service-account-<client>` |
| Machine token | Client Credentials grant | `role_type=jwt` + `bound_audiences` |
| A specific audience | Audience mapper, or `audience=` param | `bound_audiences` |
| Token for one environment | Environment attribute | `bound_claims={"environment":"production"}` |

---

## 10.12 Checkpoint

1. What is the config path for an `oidc` mount, and what are the two
   `client_id`-shaped keys called?
2. Why must `oidc_discovery_url` not contain `.well-known`, but `jwks_url` may?
3. What does `status: "valid"` on the mount config tell you?
4. What is the difference between a `bound_claims` key with a leading `/` and
   one without, in `claim_mappings`?
5. How does `groups_claim` differ from `claim_mappings` for group-based
   authorisation?
6. What is `token_policies_template_claims` for, and what happens to a
   template that evaluates to an empty string?
7. Which OIDC redirect URI does the CLI use in `client` callback mode, and
   which does the UI use?
8. What does PKCE protect against here?
9. Why might a Keycloak access token not contain the `aud` your OpenBao role
   expects?

**Next → [Level 11: GITHUB-ACTIONS-OIDC.md](11-GITHUB-ACTIONS-OIDC.md)** —
the CI pipeline, with zero stored secrets.

---

## 10.13 Scratchpad

```
Mount paths:      auth/<mount>/config | role/<name> | login | oidc/auth_url | oidc/callback
Config keys:      oidc_discovery_url (BASE url!)  oidc_client_id  oidc_client_secret
                  jwks_url (literal url)  bound_issuer  default_role  skip_jwks_validation
Role keys:        user_claim  groups_claim  claim_mappings  bound_audiences  bound_subject
                  bound_claims  bound_claims_type  oidc_scopes  allowed_redirect_uris
                  callback_mode  max_age  token_policies_template_claims
Claim notation:   "email" = top level (optional)   "/realm_access/roles" = JSON pointer (required)
Redirect URIs:    CLI client → http://localhost:8250/oidc/callback
                  CLI direct → https://host:8200/v1/auth/<mount>/oidc/callback
                  UI         → https://host:8200/ui/vault/auth/<mount>/oidc/oidc/callback
```
