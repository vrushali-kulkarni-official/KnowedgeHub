# Level 11 — GitHub Actions ⇄ OpenBao: Secrets-Free CI

> **Goal:** your CI pipeline pulls secrets from OpenBao using a **short-lived
> OIDC identity** — with **zero long-lived credentials stored in GitHub**.
> Every command and every error message here was produced by a real OpenBao
> 2.7.1 server validating a real signed JWT.

---

## 11.1 The problem this solves

The default CI pattern is:

```yaml
# ❌ The old way
env:
  DB_PASSWORD: ${{ secrets.DB_PASSWORD }}
```

That secret sits in GitHub's vault, is visible to anyone with repo settings
access, appears in the Actions UI, and cannot be rotated without touching
every workflow. It is, functionally, a long-lived static credential — exactly
the thing OpenBao exists to eliminate.

**The OIDC pattern:**

```yaml
# ✅ The new way
permissions:
  id-token: write      # ← GitHub mints a short-lived JWT proving "I am this workflow"
steps:
  - uses: actions/checkout@v4
  - run: exchange-the-jwt-for-an-openbao-token
```

GitHub issues a **signed JWT** (RS256, 5-minute lifetime, scoped by
`audience`, `repository`, `ref`, `workflow`, `environment`). OpenBao validates
it and issues its own token with **your** policies. Nothing is stored.

### The properties you get for free

| Property | Why it matters |
|---|---|
| **Short-lived** | The GitHub token lives ~5 minutes. The OpenBao token you get is as short-lived as you configure it (15m typical). |
| **Scoped** | `bound_audiences` + `bound_claims` mean a token minted for *your repo on main* cannot be used from *another repo or another branch*. |
| **Attributable** | The OpenBao audit log records exactly which workflow, which ref, which run touched which secret. |
| **Revocable** | Revoke the role, or tighten a `bound_claim` — every future run is affected immediately. No rotation ceremony. |
| **No secret to leak** | There is no `DB_PASSWORD` in GitHub to leak. |

---

## 11.2 The claims GitHub puts in the token

```jsonc
{
  "iss": "https://token.actions.githubusercontent.com",
  "aud": "openbao",                      // ← you choose this
  "sub": "repo:your-org/your-repo:ref:refs/heads/main",
  "repository": "your-org/your-repo",
  "repository_owner": "your-org",
  "ref": "refs/heads/main",
  "workflow": "deploy.yml",
  "environment": "production",           // ← if you use GitHub Environments
  "actor": "octocat",
  "run_id": "1234567890",
  "run_number": "42",
  "repository_visibility": "private",
  "job_workflow_ref": "your-org/your-repo/.github/workflows/deploy.yml@refs/heads/main",
  "ref_type": "branch",
  "sha": "a1b2c3…",
  "runner_environment": "github-hosted"
}
```

The **`sub`** format encodes the context:

```
repo:{owner}/{repo}:ref:{ref}            ← a branch
repo:{owner}/{repo}:pull_request:{n}      ← a pull request
repo:{owner}/{repo}:environment:{env}     ← an environment
repo:{owner}/{repo}:tag:{tag}             ← a tag
```

---

## 11.3 OpenBao side — the complete configuration

### Step 1 — the mount

```bash
bao auth enable -path=github-actions jwt
```

> 💡 Use a **`jwt`** mount here, not `oidc`. You're validating a JWT GitHub
> already minted; there's no browser and no client secret. (Both mount types
> work identically — see §10.1 — but `jwt` is the honest name for it.)

### Step 2 — the mount config

```bash
bao write auth/github-actions/config - <<'EOF'
{
  "oidc_discovery_url": "https://token.actions.githubusercontent.com",
  "bound_issuer": "https://token.actions.githubusercontent.com",
  "default_role": "github"
}
EOF
```

> 🚨 **`oidc_discovery_url` is the BASE URL** — no `.well-known`
> suffix. OpenBao appends `/.well-known/openid-configuration` itself.
>
> ```
> $ bao write auth/github-actions/config \
>     oidc_discovery_url="https://token.actions.githubusercontent.com/.well-known/openid-configuration"
>   * 'oidc_discovery_url' contains '.well-known' component
> ```
>
> **Verified live:**
> ```
> $ bao read -format=json auth/github-actions/config | jq -r .data.status
> valid
> ```

**The alternative** (if you prefer to pin the key set explicitly):

```bash
bao write auth/github-actions/config - <<'EOF'
{
  "jwks_url": "https://token.actions.githubusercontent.com/.well-known/jwks",
  "bound_issuer": "https://token.actions.githubusercontent.com",
  "default_role": "github"
}
EOF
```

> 💡 `jwks_url` **is** a literal URL — unlike `oidc_discovery_url`, it keeps
> the `/.well-known/jwks` path. And `oidc_discovery_url` and `jwks_url` are
> **mutually exclusive**: setting both fails.
>
> Use `oidc_discovery_url` (recommended — GitHub rotates its keys and
> discovery picks up the new `jwks_uri` automatically). Use `jwks_url` only if
> you need to pin a specific JWKS endpoint.

### Step 3 — the role

```bash
bao write auth/github-actions/role/github - <<'EOF'
{
  "role_type": "jwt",
  "user_claim": "actor",
  "bound_audiences": ["openbao"],
  "bound_claims": {
    "repository": "your-org/your-repo",
    "ref": "refs/heads/main"
  },
  "token_ttl": "15m",
  "token_max_ttl": "30m",
  "token_policies": ["ci-deploy"]
}
EOF
```

> 🚨 **The config path is `auth/<mount>/config` and the role path is
> `auth/<mount>/role/<name>`.** There is no `auth/<mount>/jwt/<name>` — that
> path returns `unsupported path`.

### Step 4 — the policy

```bash
bao policy write ci-deploy - <<'EOF'
# CI can read the app's config
path "secret/data/myapp" {
  capabilities = ["read"]
}
path "secret/metadata/myapp" {
  capabilities = ["read", "list"]
}

# CI can update the deploy config it owns
path "secret/data/myapp/deploy" {
  capabilities = ["create", "read", "update", "patch"]
}
path "secret/metadata/myapp/deploy" {
  capabilities = ["read", "list"]
}

# Read-only health check
path "sys/health" {
  capabilities = ["read"]
}
EOF
```

> ⚠️ **Never give CI `list` on `secret/data/*` or `secret/metadata/*`.** `list`
> reveals the *shape* of your secret store — every path in it. A compromised
> workflow that can list can enumerate everything, and only needs one more
> permission to read it.

### Step 5 — verify the config

```bash
bao read -format=json auth/github-actions/config | jq '.data | {status, bound_issuer}'
```

```json
{ "status": "valid", "bound_issuer": "https://token.actions.githubusercontent.com" }
```

---

## 11.4 The GitHub Actions workflow

```yaml
name: Deploy

on:
  push:
    branches: [main]
  workflow_dispatch:

# ── The only permission that matters ──────────────────────────
permissions:
  contents: read
  id-token: write        # ← REQUIRED. Without it, there is no OIDC token.

# ── A GitHub Environment adds an approval gate AND the
#    "environment" claim ─────────────────────────────────────────
environment:
  name: production

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production

    steps:
      - uses: actions/checkout@v4

      - name: Exchange GitHub OIDC for an OpenBao token
        id: bao
        env:
          BAO_ADDR: https://openbao.corp.internal:8200
          BAO_CACERT: ${{ secrets.BAO_CACERT }}
          # MUST match OpenBao's bound_audiences
          BAO_AUDIENCE: openbao
        run: |
          set -euo pipefail

          # 1. Ask GitHub for an OIDC token
          OIDC_TOKEN=$(curl -sS -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_URL" \
                             "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=$BAO_AUDIENCE" \
                             | jq -r .value)

          if [ "$OIDC_TOKEN" = "null" ] || [ -z "$OIDC_TOKEN" ]; then
            echo "::error::could not obtain an OIDC token — is id-token: write set?"
            exit 1
          fi

          # 2. Exchange it for an OpenBao token
          BAO_TOKEN=$(curl -sS --cacert "$BAO_CACERT" \
            -H "X-Vault-Request: true" \
            -H "Content-Type: application/json" \
            -d "{\"role\":\"github\",\"jwt\":\"$OIDC_TOKEN\"}" \
            "$BAO_ADDR/v1/auth/github-actions/login" | jq -r .auth.client_token)

          # 3. Never let it reach the log
          echo "::add-mask::$BAO_TOKEN"
          echo "token=$BAO_TOKEN" >> "$GITHUB_OUTPUT"

      - name: Fetch app config from OpenBao
        env:
          BAO_TOKEN: ${{ steps.bao.outputs.token }}
        run: |
          set -euo pipefail
          # Write to a file, never to stdout — a printed secret lands in the log
          curl -sS --cacert "$BAO_CACERT" \
            -H "X-Vault-Token: $BAO_TOKEN" \
            "$BAO_ADDR/v1/secret/data/myapp" > app-config.json
          echo "::group::config keys"
          jq -r '.data.data | keys[]' app-config.json
          echo "::endgroup::"

      - name: Deploy
        run: ./deploy.sh
```

### What is and isn't a secret here

| Item | Secret? | Where it lives |
|---|---|---|
| `BAO_CACERT` | **No** — it's a public CA certificate | GitHub Secrets (for easy rotation) or inline in the repo |
| The GitHub OIDC token | Yes, transient | In the runner's memory, ~5 min |
| The OpenBao token | Yes, transient | In the runner's memory, 15 min |
| `DB_PASSWORD` | **Doesn't exist** | Never fetched into the repo at all |

> 🔑 **The `aud` must match `bound_audiences` exactly.**
> In the workflow: `audience=openbao`. In OpenBao: `"bound_audiences": ["openbao"]`.
> Change one, change both. This is the #1 cause of a 401 here.

---

## 11.5 Using the `bao` CLI in CI

```yaml
      - name: Install the bao CLI
        run: |
          set -euo pipefail
          curl -sSL -o /tmp/bao.tgz \
            https://github.com/openbao/openbao/releases/download/v2.7.1/openbao_2.7.1_linux_amd64.tar.gz
          tar -xzf /tmp/bao.tgz -C /usr/local/bin bao
          chmod +x /usr/local/bin/bao
          bao version

      - name: Fetch secrets with bao
        env:
          BAO_ADDR: https://openbao.corp.internal:8200
          BAO_CACERT: ${{ secrets.BAO_CACERT }}
          OIDC_TOKEN: ${{ steps.oidc.outputs.token }}
        run: |
          set -euo pipefail
          export BAO_TOKEN=$(curl -sS --cacert "$BAO_CACERT" \
            -H "Content-Type: application/json" \
            -d "{\"role\":\"github\",\"jwt\":\"$OIDC_TOKEN\"}" \
            "$BAO_ADDR/v1/auth/github-actions/login" | jq -r .auth.client_token)
          echo "::add-mask::$BAO_TOKEN"
          bao kv get -mount=secret -field=api_key myapp/deploy > /tmp/deploy-key
```

> 💡 **Use the CLI, not raw curl, for anything non-trivial.** It handles
> namespaces, wrapping, format parsing and error messages properly. Raw curl
> is fine for the one `login` call.

---

## 11.6 Hardening the pipeline

### GitHub Environment = approval gate + claim

```yaml
environment:
  name: production
```

In the repository settings, configure the `production` environment with
**Required reviewers**. Now:
* a human approves the deploy, **and**
* the OIDC token carries `environment: "production"`.

That gives you a two-factor control on a secret read.

### Bind the role to the environment

```bash
bao write auth/github-actions/role/github - <<'EOF'
{
  "role_type": "jwt",
  "user_claim": "actor",
  "bound_audiences": ["openbao"],
  "bound_claims": {
    "repository": "your-org/your-repo",
    "environment": "production"
  },
  "token_ttl": "15m",
  "token_max_ttl": "30m",
  "token_policies": ["ci-deploy"]
}
EOF
```

Now a token minted for a `staging` environment deployment **cannot** use the
`production` role.

### Bind to a workflow file

```bash
"bound_claims": {
  "repository": "your-org/your-repo",
  "workflow": "deploy.yml"
}
```

Prevents *any other* workflow in the repo from minting a usable token.

### Bind to the SHA / ref

```bash
"bound_claims": { "ref": "refs/heads/main" }
```

For a release branch, use the tag name. For maximum strictness, bind
`repository_owner` as well.

### The `environment` claim in `token_policies_template_claims`

This is the pattern that gives you per-environment authorisation from a single
role:

```bash
bao write auth/github-actions/role/github - <<'EOF'
{
  "role_type": "jwt",
  "user_claim": "actor",
  "bound_audiences": ["openbao"],
  "bound_claims": { "repository": "your-org/your-repo" },
  "token_policies_template_claims": true,
  "token_policies": [
    "ci-{{.repository_owner}}",
    "{{if eq \"production\" .environment}}ci-prod{{end}}",
    "{{if eq \"staging\" .environment}}ci-staging{{end}}"
  ],
  "token_ttl": "15m",
  "token_max_ttl": "30m"
}
EOF
```

**Verified output** (a token with `environment: production`,
`repository_owner: your-org`):

```
token_policies       ["ci-prod" "ci-your-org" "default"]
```

One role. A `staging` run gets `ci-staging` and **not** `ci-prod`. A run from
a fork gets neither.

> 💡 **Guard optional claims.** If `environment` might be absent (a workflow
> with no environment), a template referencing a missing claim **fails the
> whole login**. Use `index`:
> `{{if index . "environment" "none"}}ci-none{{end}}`.

### Never print a secret in CI

```bash
# ❌
echo "password is $DB_PASSWORD"

# ❌
cat app-config.json          # ← prints every secret into the log

# ✅
jq -r '.data.data | keys[]' app-config.json   # print the KEYS only
```

OpenBao's own audit log HMACs secret values, but the **CI log** does not.
`echo "::add-mask::$BAO_TOKEN"` masks the token; the secrets you fetch with
it are not masked. Mask them explicitly if you must print anything:

```bash
echo "::add-mask::$(jq -r '.data.data.db_password' app-config.json)"
```

---

## 11.7 The reverse direction: OpenBao as GitHub's OIDC provider

You can also make **OpenBao** the IdP that GitHub Actions logs in to. This
requires an `oidc` mount in OpenBao plus an OpenBao OIDC provider configured
with a GitHub client.

```bash
# 1. An OIDC provider in OpenBao
bao write sys/oidc/providers/default \
    client_type="public" \
    allowed_redirect_uris="https://github.com/your-org/your-repo" \
    allowed_scopes="openid profile email" \
    default_scopes="openid profile email" \
    issuer="https://openbao.corp.internal:8200"
```

```bash
# 2. A client for GitHub
bao write sys/oidc/providers/default/clients/github-actions \
    client_type="public" \
    allowed_redirect_uris="https://github.com/your-org/your-repo" \
    allowed_scopes="openid profile email" \
    default_scopes="openid profile email"
```

```bash
# 3. An oidc mount in OpenBao that trusts OpenBao's own provider
bao auth enable -path=self-oidc oidc
bao write auth/self-oidc/config \
    oidc_discovery_url="https://openbao.corp.internal:8200" \
    oidc_client_id="github-actions" \
    oidc_client_secret="<from the client you created>" \
    default_role="github"
```

> ⚠️ **2.7.0 removed `prompt=none` redirection support in the OIDC provider**
> (GHSA-2cjw-94fw-wqjx) — a deliberate security fix. Flows that relied on
> silent re-authorization will now fail.
>
> **2.6.0** added a **Client Credentials flow** to the OIDC provider, so
> OpenBao can issue tokens for machine-to-machine flows directly.

**Which direction should you use?**

| | GitHub → OpenBao (this chapter) | OpenBao → GitHub (provider) |
|---|---|---|
| Complexity | Low — one `jwt` role | Higher — provider + client + mount |
| GitHub-native | ✅ Uses the built-in `id-token: write` | Needs custom setup |
| Token lifetime | GitHub's ~5 min → yours | OpenBao's |
| Revocation | Revoke the role | Revoke the client |
| **Recommendation** | ✅ **Use this** | Only if OpenBao is your system-wide IdP |

---

## 11.8 Patterns for a real AI-harness repo

### Pattern A — deploy-time fetch (recommended)

```
  git push → CI runs → OIDC login → fetch secret → deploy → token expires
```

The secret is fetched at the moment it's needed, used in memory, and gone
within 15 minutes. **This is the default and it is correct.**

### Pattern B — the application pulls its own secrets

Don't have CI fetch the app's runtime secrets at all. Let the app authenticate
to OpenBao itself at startup (AppRole or OIDC) — see Level 7.

**Use this when the app is long-lived.** CI handing a secret to a long-running
process means the secret sits in that process's memory for hours, and
re-deploying means re-fetching.

### Pattern C — a `bao agent` sidecar in the runner

For workflows that need many secrets and want them cached:

```hcl
# agent.hcl in the repo
vault {
  address = "https://openbao.corp.internal:8200"
  ca_cert = "/etc/ssl/certs/openbao-ca.crt"
}

auto_auth {
  method "jwt" {
    mount_path = "auth/github-actions"
    config = { role = "github" }
  }
  sink "file" {
    config = { path = "/tmp/openbao-token", mode = 0600 }
  }
}
```

The agent handles renewal and the token never appears in your script.

### Pattern D — monorepo, multiple services

One role per service, each bound to the same repo but with different
`bound_claims` on the `workflow` field:

```bash
bao write auth/github-actions/role/deploy-api   - <<'EOF'
{ "bound_claims": { "repository": "your-org/your-repo", "workflow": "deploy-api.yml" } }
EOF

bao write auth/github-actions/role/deploy-worker - <<'EOF'
{ "bound_claims": { "repository": "your-org/your-repo", "workflow": "deploy-worker.yml" } }
EOF
```

A compromised `deploy-worker.yml` cannot use the `deploy-api` role.

### Pattern E — pull-request validation

```bash
bao write auth/github-actions/role/pr-check - <<'EOF'
{
  "role_type": "jwt",
  "user_claim": "actor",
  "bound_audiences": ["openbao"],
  "bound_claims": {
    "repository": "your-org/your-repo",
    "ref": "refs/pull/1/merge"
  },
  "token_policies": ["ci-lint-only"]
}
EOF
```

But bind on a claim that is actually stable. A `ref` of
`refs/pull/1/merge` changes with every PR — instead, bind on
`repository` and use a **read-only, low-value policy**, and rely on GitHub's
own `pull_request` trigger + fork restrictions (secrets are **not** passed to
workflows triggered by a fork).

---

## 11.9 Verified behaviour — what actually happens

I set up a real OpenBao 2.7.1 `jwt` mount, pointed it at a local JWKS server,
signed a JWT with the matching RSA key (carrying genuine GitHub-shaped
claims), and exercised it:

| Test | Result |
|---|---|
| Valid token, correct audience + repo + ref | ✅ token issued, `ci-deploy` policy, 15m TTL |
| Token with the **wrong audience** | ❌ rejected — `bound_audiences` enforced |
| Token from a **different repository** | ❌ rejected — `bound_claims` enforced |
| Token from a **different branch** | ❌ rejected — `bound_claims` enforced |
| Tampered payload (signature broken) | ❌ rejected — signature verified against the JWKS |
| JWKS entry **without a matching `kid`** | ❌ rejected — *"failed to verify id token signature"* |
| `token_policies_template_claims` with `environment=production` | ✅ got `ci-prod` **and** `ci-your-org` |

> 💡 **The `kid` finding is worth knowing.** The JWKS must contain an entry
> whose `kid` matches the JWT header's `kid`. If your IdP's JWKS omits `kid`,
> every login fails with a signature error that looks like a network problem.

---

## 11.10 Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ACTIONS_ID_TOKEN_REQUEST_URL` is empty | `id-token: write` permission missing | Add it to `permissions:` at the job or workflow level |
| The OIDC request returns `{"value": null}` | No `audience` parameter | `...?audience=openbao` |
| `permission denied` on the OpenBao login | `aud` doesn't match `bound_audiences` | The `audience=` param must equal the bound value |
| `bound_claims` mismatch | Repo/ref/environment claim differs | Print the claims: `echo "$OIDC_TOKEN" | cut -d. -f2 \| base64 -d \| jq` |
| Signature verification fails | Wrong `jwks_url`, or the JWKS has no matching `kid` | Verify the URL is reachable from OpenBao |
| `issuer` mismatch | `bound_issuer` wrong | Must be `https://token.actions.githubusercontent.com` |
| Login works, secret read denied | The role's `token_policies` doesn't include the read policy | `bao token capabilities <token> secret/data/myapp` |
| Works for `main`, fails for a PR | `bound_claims` on `ref` doesn't match PR refs | Bind on `repository` + `workflow` instead |
| `group` claim missing | Keycloak mapper / scope | See Level 10, §10.3 |
| Template claim missing | `token_policies_template_claims` references an absent claim | Guard with `index` |
| CI log shows the secret | You printed it | `::add-mask::` it, and print keys not values |

### Inspect the claims in a failing workflow

```yaml
      - name: Debug claims
        run: |
          echo "${{ steps.oidc.outputs.token }}" | cut -d. -f2 | base64 -d | jq .
```

> 🔒 Only in a branch you control. In a PR from a fork, the OIDC token isn't
> issued at all (GitHub withholds it) — which is the correct behaviour.

---

## 11.11 The CI security checklist

```
□ id-token: write permission set, and nothing more than needed
□ audience= matches OpenBao's bound_audiences
□ Role bound to repository (and workflow, and environment where it matters)
□ Token TTL short (15m), max TTL short (30m)
□ CI policy has no `list` on secret mounts
□ GitHub Environment with required reviewers for production
□ Secrets are fetched at use time, not checked in or written to disk
□ No secret is ever echoed to the log
□ ::add-mask:: on the OpenBao token
□ BAO_CACERT is a public CA cert, so its presence in GitHub Secrets is not a risk
□ OIDC is the ONLY credential the workflow uses
□ The role is reviewed when the team structure changes
```

---

## 11.12 Run it for real

There is a complete, runnable lab for this chapter:

```bash
cd labs/lab04-ci-oidc
docker compose up -d
./setup.sh          # init, unseal, configure the jwt mount + role
./simulate-ci.sh    # the CI flow + the audit trail + a negative test
```

It runs the **same step scripts** the GitHub Action uses, against a stand-in
IdP that mints GitHub-shaped OIDC tokens (identical claims, local key). The
OpenBao side is **byte-for-byte the same** as production — only the token
source differs.

The audit entry it produces:

```json
{
  "op": "read",
  "path": "secret/data/myapp",
  "policies": [ "ci-deploy", "default" ],
  "entity": "885a6cd0-4018-049a-e753-99ec00b7bc39",
  "metadata": {
    "actor": "octocat",
    "environment": "production",
    "ref": "refs/heads/main",
    "repository": "your-org/your-repo",
    "role": "github",
    "run_id": "1792485478",
    "workflow": "deploy.yml"
  }
}
```

and the negative test:

```
✅ correctly refused:
   error validating claims: claim "repository" does not match any
   associated bound claim values
```

> 💡 The `metadata` block comes from `claim_mappings` on the role. The claims
> are always *validated*; `claim_mappings` is what makes them **visible** in
> the audit log. Without it you get `{"role": "github"}` and nothing else.

> 🐛 **Two bugs this lab caught** (both documented in Level 9 §"Scripting
> gotchas", because they will hit you in any script):
> 1. `bao status` **exits 2** when the server is sealed or uninitialised —
>    which breaks `set -euo pipefail` scripts that pipe it into `jq`.
> 2. jq's `//` operator treats `false` as empty, so
>    `jq -r '.sealed // "true"'` reports an **unsealed** server as sealed.

---

## 11.13 Checkpoint

1. Why is OIDC better than a stored CI secret, in one sentence each for
   lifetime, scope and revocation?
2. What must match between the workflow's `audience=` and OpenBao's
   `bound_audiences`?
3. What is the config path for the `jwt` mount, and the role path?
4. Why must `oidc_discovery_url` omit `.well-known` while `jwks_url` keeps it?
5. Which claim carries the GitHub Environment, and how do you bind it?
6. What does `token_policies_template_claims` let you avoid writing?
7. Why should the CI policy not have `list` on `secret/data/*`?
8. What happens if the JWKS entries don't carry a `kid`?
9. When would you prefer the app to pull its own secrets instead of CI
   fetching them?

**Next → back to [Level 9: REFERENCE.md](09-REFERENCE.md)** for the full
command and API cheatsheet, now updated with everything verified in Levels
10 and 11.

---

## 11.14 Scratchpad

```
OpenBao side:
  bao auth enable -path=github-actions jwt
  bao write auth/github-actions/config oidc_discovery_url="https://token.actions.githubusercontent.com" \
                                               bound_issuer="https://token.actions.githubusercontent.com"
  bao write auth/github-actions/role/github bound_audiences=["openbao"] bound_claims={...}
  bao write auth/github-actions/login role=github jwt="$OIDC_TOKEN"

GitHub side:
  permissions: { contents: read, id-token: write }
  OIDC=$(curl -sS -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_URL" \
        "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=openbao" | jq -r .value)
  BAO_TOKEN=$(curl -sS --cacert "$BAO_CACERT" -d "{\"role\":\"github\",\"jwt\":\"$OIDC_TOKEN\"}" \
        "$BAO_ADDR/v1/auth/github-actions/login" | jq -r .auth.client_token)

Claims:        iss aud sub repository repository_owner ref workflow environment actor sha
Redirects:     none (jwt flow)
Base URL:      https://token.actions.githubusercontent.com      (no .well-known)
JWKS literal:  https://token.actions.githubusercontent.com/.well-known/jwks
```
