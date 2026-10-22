# Lab 04 — Secrets-Free CI: GitHub Actions OIDC → OpenBao

**This is the lab that proves Level 11.** It runs the *exact* steps a GitHub
Actions workflow runs, against a real OpenBao 2.7.1 server, and then shows you
the audit log entry that records who read which secret.

The only difference from real GitHub is **where the OIDC token comes from**:

| | Real GitHub | This lab |
|---|---|---|
| Token source | `ACTIONS_ID_TOKEN_REQUEST_URL` (signed by GitHub) | `http://127.0.0.1:8099/token` (signed by a local key) |
| Claims | `iss`, `aud`, `sub`, `repository`, `ref`, `workflow`, `environment`, `actor`, … | **identical** |
| Signature | GitHub's JWKS | a local JWKS with the same `kid` |
| OpenBao side | **identical** | **identical** |

So if the flow works here, it works in GitHub.

---

## Run it

```bash
cd labs/lab04-ci-oidc

docker compose up -d          # openbao + the stand-in IdP
./setup.sh                    # init, unseal, configure, store a secret
./simulate-ci.sh              # run the CI flow + show the audit trail
```

Tear down:

```bash
docker compose down -v && rm -rf data logs
```

> ⚠️ `setup.sh` writes `unseal-keys.txt` and `.root-token` into this directory.
> **Treat them like a password** and keep them out of git. There's a
> `.gitignore` for exactly that.

---

## What `setup.sh` does

```
1. Initialise the cluster (5 shares / 3 threshold) and unseal it
2. Enable kv-v2 and store secret/myapp
3. Write the ci-deploy policy (least privilege — no list, no wildcards)
4. Enable the `jwt` auth method and create the GitHub role
5. Print the state
```

The role it creates:

```json
{
  "role_type": "jwt",
  "user_claim": "actor",
  "bound_audiences": ["openbao"],
  "bound_claims": {
    "repository": "your-org/your-repo",
    "ref": "refs/heads/main",
    "workflow": "deploy.yml"
  },
  "claim_mappings": {
    "actor": "actor", "repository": "repository", "ref": "ref",
    "workflow": "workflow", "environment": "environment", "run_id": "run_id"
  },
  "token_policies": ["ci-deploy"],
  "token_ttl": "15m",
  "token_max_ttl": "30m"
}
```

---

## What `simulate-ci.sh` does

It runs the four step scripts in `ci/steps/` — **the same ones the GitHub
Action uses** — then a negative test:

| Step | Script | Does |
|---|---|---|
| 1 | `01-get-oidc-token.sh` | Mint the OIDC token |
| 2 | `02-login.sh` | Exchange it for an OpenBao token |
| 3 | `03-fetch-secrets.sh` | Read the secret to a **file**, never to stdout |
| 4 | `04-audit-check.sh` | Show the audit trail |
| — | negative test | A token from a *different repo* must be **refused** |

### The real output

```
▸ Step 1/4 — Get an OIDC token
[ci] OIDC token acquired (912 chars)

▸ Step 2/4 — Exchange it for an OpenBao token
[ci] OpenBao token acquired
[ci]   ttl:      900s
[ci]   policies: ci-deploy, default
[ci]   accessor: 6f1c…

▸ Step 3/4 — Read the secret
[ci] secret written to ./app-config.json (values NOT printed)
[ci] keys present: db_host, db_port, deploy_token, llm_api_key

▸ Step 4/4 — Check the audit trail

{
  "time": "2026-10-20T08:37:59.025941738Z",
  "op": "read",
  "path": "secret/data/myapp",
  "ip": "127.0.0.1",
  "accessor": "hmac-sha256:6ff63967c7d3a69e…",
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

▸ Negative test — a token from the wrong repo must be refused
  ✅ correctly refused:
     error validating claims: claim "repository" does not match any
     associated bound claim values
```

**That metadata block is the whole point.** The audit log tells you *which
workflow*, on *which branch*, for *which environment*, triggered by *which
actor* — and it did it with **no long-lived secret anywhere in the system**.

> 💡 The `claim_mappings` block is what puts those claims into the metadata.
> Without it, the audit log shows only `{"role": "github"}`. The claims are
> always *validated*; `claim_mappings` is what makes them *visible*.

---

## Porting this to real GitHub

The step scripts are already GitHub-shaped. In a real workflow:

```yaml
      - name: Get OIDC token
        id: oidc
        env:
          BAO_AUDIENCE: openbao
        run: |
          OIDC_TOKEN=$(curl -sS -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_URL" \
            "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=$BAO_AUDIENCE" | jq -r .value)
          echo "::add-mask::$OIDC_TOKEN"
          echo "oidc_token=$OIDC_TOKEN" >> "$GITHUB_OUTPUT"
```

The only changes vs the lab:

| Lab | Real GitHub |
|---|---|
| `http://127.0.0.1:8099/token` | `$ACTIONS_ID_TOKEN_REQUEST_URL` |
| `http://127.0.0.1:8200` | `https://openbao.corp.internal:8200` + `BAO_CACERT` |
| `jwks_url` → local JWKS | `oidc_discovery_url` → `https://token.actions.githubusercontent.com` |

**And in OpenBao, switch the mount config:**

```bash
bao write auth/github-actions/config - <<'EOF'
{
  "oidc_discovery_url": "https://token.actions.githubusercontent.com",
  "bound_issuer": "https://token.actions.githubusercontent.com",
  "default_role": "github"
}
EOF
```

(The lab uses `jwks_url` because it points at a local JWKS. In production use
`oidc_discovery_url` — the **base URL**, no `.well-known` — so GitHub's key
rotation is picked up automatically. The two are mutually exclusive.)

---

## Two bugs this lab actually caught

Both were found by running the code, not by reading it. They're in
`setup.sh` with explanatory comments, because they will bite you in any script
that talks to OpenBao.

### 1. `bao status` exits non-zero when the server is sealed

```
uninitialised:  exit=2
```

Under `set -euo pipefail` this breaks the obvious idiom:

```bash
# ❌ BREAKS: the pipeline's status is non-zero, so `|| echo true` also
#            fires and you get V="true\ntrue" — which never equals "true"
V=$(bao status -format=json | jq -r .sealed || echo true)

# ✅ WORKS: capture the JSON first, then parse it
raw=$(bao status -format=json 2>/dev/null || true)
V=$(printf '%s' "$raw" | jq -r '.sealed' 2>/dev/null || true)
```

### 2. jq's `//` operator treats `false` as empty

```bash
# ❌ "true" when .sealed is FALSE (i.e. when the server is UNSEALED)
jq -r '.sealed // "true"'

# ✅ correct
jq -r 'if has("sealed") then (.sealed | tostring) else "true" end'
```

`false // "x"` evaluates to `"x"` in jq, because `//` means "if the left side is
null **or false**". This one is genuinely nasty: the script reported a
perfectly healthy, unsealed server as "still SEALED".

---

## Files

```
lab04-ci-oidc/
├── docker-compose.yml           # openbao + the stand-in IdP
├── Dockerfile.jwks
├── config/
│   ├── openbao.hcl              # raft + the declarative audit device
│   └── jwks-server.py           # the stand-in IdP (mints GitHub-shaped JWTs)
├── ci/
│   ├── deploy.yml               # the REAL GitHub Actions workflow
│   └── steps/
│       ├── 01-get-oidc-token.sh
│       ├── 02-login.sh
│       ├── 03-fetch-secrets.sh
│       └── 04-audit-check.sh
├── setup.sh                     # init + configure
└── simulate-ci.sh               # run the flow + audit + negative test
```

---

## The audit log, on its own

```bash
# Every read of the secret, with the claim-derived identity
jq -c 'select(.type=="response" and .request.path=="secret/data/myapp")
       | {t:.time, by:.auth.metadata, policies:.auth.policies}' logs/audit.log

# Who read secrets today?
jq -r 'select(.request.path | startswith("secret/data/"))
       | "\(.time) \(.auth.metadata.repository // "?") \(.auth.metadata.workflow // "-") \(.request.operation)"' \
   logs/audit.log

# Denied attempts (probing / credential stuffing)
jq -c 'select(.error != "") | {t:.time, path:.request.path, err:.error}' logs/audit.log
```
