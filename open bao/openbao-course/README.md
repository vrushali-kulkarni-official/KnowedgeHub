# OpenBao 2.7.1 — The Complete Course
### From absolute zero to production-grade enterprise secrets management

---

## Who this is for

You are building an **Enterprise AI harness** with this stack:

```
Python · FastAPI · LangChain · JWT/OAuth/OIDC · Keycloak
OpenBao · PostgreSQL · Redis · Git/GitHub/GitHub Actions · Docker/Docker Compose
```

You want everything containerised, you want open-source tools, you want
production-grade security, and you want to understand OpenBao from the ground up.

This course takes you from *"what even is a secret manager"* to *"I run a
multi-namespace, HA, auto-unsealed OpenBao cluster with a PKI, dynamic database
credentials, and CI that pulls secrets via OIDC."*

---

## Version target — read this first

| Item | Value |
|---|---|
| OpenBao release taught | **v2.7.1** (released 1 Oct 2026) |
| CLI binary | `bao` (NOT `vault`) |
| Docs source | `openbao.org/docs` (2.7.x branch) + `github.com/openbao/openbao` tag `v2.7.1` |
| Language | Python 3.11+ |
| Licence | MPL-2.0, Linux Foundation / OpenSSF |

> **Everything in this course was verified against the shipped `v2.7.1` source
> tree and its `CHANGELOG.md`.** Where 2.5/2.6/2.7 removed or deprecated
> something, you will see an explicit ⚠️ **REMOVED** / **DEPRECATED** callout
> rather than the old way of doing things.

### The "do not learn this" list (things people still teach that are now wrong)

| Old thing | Status in 2.7.1 | What to do instead |
|---|---|---|
| `vault` CLI | Renamed long ago | `bao` |
| `storage "file"` | **REMOVED in 2.7.0** | `storage "raft"` (integrated) or `storage "postgresql"` |
| `storage "pebbledb"` | Deprecated *for `operator migrate`*, removal in 2.8.0 | Still valid as a non-HA durable backend |
| Consul / DynamoDB / S3 / etcd storage | Removed | Raft or PostgreSQL only |
| Built-in `awskms`/`gcpckms`/`azurekeyvault`/`alicloudkms`/`ocikms`/`pkcs11` seals | **REMOVED from binary in 2.7.0** | Install as KMS plugins from `openbao/openbao-plugins` |
| Built-in Kerberos / LDAP (auth) / RADIUS (auth) / LDAP (secrets) | **REMOVED from binary in 2.7.0** | Install as plugins from `openbao/openbao-plugins` |
| `openbao-hsm` container image / HSM distribution | **Discontinued in 2.7.0** | `kms-pkcs11` plugin with the standard image |
| `sys/generate-root/attempt` (unauthenticated) | **Deprecated**; disabled by default | `sys/generate-root-token` (authenticated) — `bao operator generate-root` already uses it |
| Legacy unauthenticated `/sys/rekey/*` endpoints | **Disabled by default** (`disable_unauthed_rekey_endpoints = true`) | Leave it that way |
| `sys/health` → `performance_standby`, `last_wal` fields | Removed in 2.6.0 | Don't script against them |
| `stored_shares` param on `sys/init` | Removed in 2.6.0 (ignored) | Don't send it |
| Arm64-specific container tags (`2.7.0-arm64`) | Not published since 2.6.0 | Use the multi-arch tag `openbao/openbao:2.7.1` |
| FQDNs with trailing dot (`example.com.`) in PKI | Rejected (Go 1.27 change) | Use `example.com` |
| `build_date` in `sys/seal-status` / `sys/version-history` | Renamed `commit_date` in 2.6.0 | Use `commit_date` |
| OpenBao-HSM `openbao-hsm:*` images | Discontinued | Standard image + PKCS#11 KMS plugin |

---

## Course map

Each level builds directly on the previous one. Do them in order.

| # | Chapter | You will learn | Time |
|---|---|---|---|
| 0 | [FOUNDATIONS.md](00-FOUNDATIONS.md) | What OpenBao is, why you need it, the threat model, the 10 vocabulary words that make everything else obvious | 45 min |
| 1 | [CONCEPTS.md](01-CONCEPTS.md) | The mental model: server → barrier → storage, seal/unseal, tokens, policies, auth methods, secret engines, audit devices, leases | 90 min |
| 2 | [HANDS-ON.md](02-HANDS-ON.md) | Level 0 → working OpenBao in Docker. Init, unseal, KV v2, policies, userpass, AppRole. First real policy | 2 h |
| 3 | [POLICIES-TOKENS-IDENTITY.md](03-POLICIES-TOKENS-IDENTITY.md) | Authorization deep dive: ACL syntax, capabilities, templating, groups, entities, token hierarchy, orphans, accessors, batch tokens | 2 h |
| 4 | [SECRET-ENGINES.md](04-SECRET-ENGINES.md) | KV v2, Transit (encryption-as-a-service), PKI (internal CA), Database (dynamic creds), TOTP, SSH, Cubbyhole, response wrapping | 3 h |
| 5 | [SECURITY-HARDENING.md](05-SECURITY-HARDENING.md) | The production security baseline: TLS, mlock, auto-unseal design, root token hygiene, audit strategy, quotas, hardening checklist | 2 h |
| 6 | [HA-PRODUCTION.md](06-HA-PRODUCTION.md) | Reference architecture: 5-node Raft HA, PostgreSQL backend, snapshots & restore, upgrades, observability, DR, namespaces | 3 h |
| 7 | [INTEGRATION-STACK.md](07-INTEGRATION-STACK.md) | Wiring OpenBao into *your* stack: Keycloak OIDC, FastAPI, LangChain, PostgreSQL dynamic creds, Redis, GitHub Actions | 3 h |
| 8 | [EXPERT.md](08-EXPERT.md) | Namespaces, plugin system + OCI distribution, workflows engine, External Keys, post-quantum crypto, CEL roles, control groups | 2 h |
| 9 | [REFERENCE.md](09-REFERENCE.md) | Cheatsheets: every important command, API path map, config reference, full production runbook | reference |
| 10 | [KEYCLOAK-OIDC.md](10-KEYCLOAK-OIDC.md) | **Keycloak ⇄ OpenBao, deep dive.** The `oidc`/`jwt` mount anatomy, claim→policy pipeline, `groups_claim`, `claim_mappings`, JSON pointers, callback modes, service accounts, OpenBao-as-IdP | 2 h |
| 11 | [GITHUB-ACTIONS-OIDC.md](11-GITHUB-ACTIONS-OIDC.md) | **Secrets-free CI.** GitHub OIDC → OpenBao, `bound_claims` hardening, `token_policies_template_claims`, per-environment authorisation, the reverse (OpenBao as provider) | 2 h |

### Labs

Runnable Docker Compose labs live in [`labs/`](labs/):

```
labs/
├── lab01-dev-stack/        # OpenBao + Postgres + Redis + Keycloak, one command
├── lab02-ha-raft/          # 5-node Raft HA cluster with TLS
├── lab03-full-reference/   # The full production reference architecture
└── lab04-ci-oidc/          # Secrets-free CI: GitHub Actions OIDC → OpenBao
```

---

## How to use this course

1. **Type every command.** Reading commands teaches you nothing. Copy/paste teaches you less.
2. **Break it on purpose** once per level. Rename a policy path, break a token, revoke a lease — then read the audit log to see what happened. The audit log is the debugger.
3. **Keep a scratch file.** Every level gives you a "scratchpad" section. Track your own `role_id`s, mount paths, policies. You will forget them.
4. **Never commit secrets.** Not to git, not to Slack, not to a `.env` file that ends up in the repo. Add `.env*` to `.gitignore` on day one.
5. **Read the audit log.** It is the single most underrated feature in this product.

---

## Why OpenBao and not HashiCorp Vault?

| | OpenBao | HashiCorp Vault |
|---|---|---|
| Licence | MPL-2.0 (OSI open source) | BSL 1.1 (source-available) |
| Governance | Linux Foundation / OpenSSF, vendor-neutral | Single vendor (IBM) |
| Namespaces (multi-tenancy) | **Free**, since 2.3.1 | Enterprise only |
| HSM/PKCS#11 auto-unseal | **Free** (2.7: via KMS plugin) | Enterprise only |
| Standby nodes serving reads | **Free** (Raft since 2.5, Postgres since 2.7) | Enterprise only |
| Cross-cluster replication | Not available | Enterprise only |
| Advanced policy roles | CEL | Sentinel (Enterprise) |
| FIPS-validated builds | Not available | Enterprise |
| Managed cloud | None — self-host only | HCP Vault |
| **Cost for you** | **$0** | $$ (or Enterprise $$$) |

OpenBao forked from Vault 1.14.x when HashiCorp relicensed to BSL in Aug 2023. The
data-plane APIs are compatible, so `hvac`, Terraform/OpenTofu providers and
existing scripts generally keep working. But the APIs **diverged** after 1.14 —
do not assume Vault 1.15+ features exist. And note the CLI is `bao`, not `vault`.

---

## Canonical sources used to build this course

- `https://openbao.org/docs/` — 2.7.x documentation
- `https://github.com/openbao/openbao` — source tree at tag `v2.7.1`, incl. `CHANGELOG.md`
- `https://github.com/openbao/openbao-plugins` — external plugin builds
- `https://github.com/openbao/openbao-helm` — Helm chart `0.30.x` for Kubernetes
- `https://openbao.org/community/release-notes/2-7-0/` — 2.7 release notes

---

## ✅ How this course was verified (and how to re-verify it)

This is not "I read the docs and wrote some commands". The course was checked
against the **actual `bao` v2.7.1 binary** (`a5db72cef75c24b920ade02065b18dd8eb666bac`).

| Check | Result |
|---|---|
| Every `bao …` command and subcommand in this course | ✅ exists in v2.7.1 (`bao <cmd> --help`) |
| OIDC/JWT mount paths (`config`, `role/<name>`, `login`, `oidc/*`, `cel/*`) | ✅ enumerated with `bao path-help` on both `oidc` and `jwt` mounts |
| `oidc_discovery_url` against a live mock IdP **and** against real GitHub | ✅ `status: "valid"` in both cases |
| Full OIDC authorization-URL generation (PKCE S256 + nonce + scopes) | ✅ real URL produced and inspected |
| Full GitHub-Actions OIDC exchange (signed JWT → OpenBao token) | ✅ token issued with the right policies and TTL |
| Negative cases: wrong audience / wrong repo / wrong ref / tampered payload / missing `kid` | ✅ all correctly rejected |
| `token_policies_template_claims` deriving policies from claims | ✅ `ci-prod` + `ci-your-org` granted from `environment` + `repository_owner` |
| **Full CI flow end-to-end** (OIDC token → OpenBao token → secret read → audit trail) | ✅ run in `labs/lab04-ci-oidc` against a live server |
| The audit trail showing `actor` / `repository` / `ref` / `workflow` / `environment` | ✅ captured in the lab's real output |
| Negative case: a token from a different repo | ✅ refused — *"claim 'repository' does not match any associated bound claim values"* |
| Every built-in auth method type | ✅ verified by enabling each: `oidc`, `jwt`, `approle`, `userpass`, `kubernetes`, `cert` — and confirming `ldap`/`kerberos`/`radius`/`github`/`aws` are **plugin-only** |
| Every built-in secrets engine type | ✅ verified by enabling each: `kv`, `kv-v2`, `transit`, `pki`, `database`, `totp`, `ssh` — and confirming `ldap`/`aws`/`gcp`/`consul` are **plugin-only** |
| Every server-config HCL block in this course | ✅ passes `bao operator validate-config` |
| The three lab `openbao.hcl` files | ✅ pass `bao operator validate-config` |
| KV v2 read/write/version/metadata | ✅ run against a live 2.7.1 dev server |
| AppRole login, token creation, accessors | ✅ run against a live 2.7.1 dev server |
| Transit encrypt/decrypt round trip | ✅ run against a live 2.7.1 dev server |
| PKI root → intermediate → leaf chain | ✅ run against a live 2.7.1 dev server |
| Namespaces, wrapping, quotas, lease revocation | ✅ run against a live 2.7.1 dev server |
| Plugin OCI images on `ghcr.io/openbao` | ✅ live tag list pulled from the registry |
| All Compose files, shell scripts, JSON, Python | ✅ syntax-validated |

### Things that verification caught (and that most tutorials get wrong)

These are the 2.7.1 realities that this course now teaches correctly:

| Wrong (pre-2.7 / Vault habits) | Correct in 2.7.1 |
|---|---|
| `disable_mlock = false` in the config | **No such option** — removed in 2.0.0; the server refuses to start with it. Harden swap instead. |
| `telemetry { prometheus = true }` | `telemetry { prometheus_retention_time = "30s" }` — the boolean is gone |
| `bao audit enable file file_path=…` | **API audit creation is disabled by default.** Use the `audit "file" "file" { options { … } }` config stanza (two labels, string values) |
| `bao kv get -metadata secret/x` | `bao kv metadata get -mount=secret x` — and the path-like `secret/x` form is deprecated; use `-mount` |
| `bao policy fmt <policy-name>` | `bao policy fmt <local-file>` — it rewrites the file; there is no `-check` |
| `bao logout` | **No such command.** Delete `~/.vault-token` (or `$BAO_TOKEN_PATH`) |
| `~/.bao-token` | The default token file is `~/.vault-token` |
| `bao token create -field=accessor` | The accessor is under `auth`; use `-format=json \| jq -r .auth.accessor` |
| `bao read -field=role_id auth/approle/role/x` | `bao read -field=role_id auth/approle/role/x/role-id` |
| `bao sys capabilities-self <path>` | No CLI command — it is an API endpoint. Use `bao token capabilities <token> <path>` |
| `bao write auth/oidc/oidc …` | The config path is **`auth/<mount>/config`**; a role is **`auth/<mount>/role/<name>`** |
| `oidc_discovery_url="…/.well-known/openid-configuration"` | **Rejected** — it must be the **base URL**; OpenBao appends the suffix |
| `client_id=` / `client_secret=` on the OIDC config | Silently ignored — the keys are **`oidc_client_id`** / **`oidc_client_secret`** |
| `bound_claims=k=v` repeated on the CLI | `bound_claims` is a **map** — use a JSON write (`-` heredoc) |
| `bao status` inside a `set -e` script | It **exits 2** when sealed/uninitialised — capture the JSON first, then parse it |
| `jq -r '.sealed // "true"'` | jq's `//` treats `false` as empty → reports an **unsealed** server as sealed. Use an explicit `if` |
| `bao write -f transit/encrypt/...` expecting one bare value | `-f` is "raw format", not "one field" — use `-format=json \| jq -r .data.ciphertext` |
| `bao read` on `/v1/pki_int/ca` | That endpoint returns **raw PEM** — use `curl`, not `bao read` |
| `bao write sys/quotas/rate-limit rate=…` | Needs a name: `sys/quotas/rate-limit/<name>` |
| `bao -namespace=x secrets list` | The flag goes **after** the subcommand: `bao secrets list -namespace=x` |
| `key_bits=ecdsa-p521` in PKI | `key_bits` is an **integer** (`521`), and `key_type=ec` |
| `pki/root/generate/internal` with `issuer_name="Corp Root"` | Issuer names cannot contain spaces — use hyphens |
| PKI CA TTL shorter than requested | **`bao secrets tune -max-lease-ttl=…` first**, or the CA is silently capped at 768h |
| `bao write pki/ca` to export a chain | The CA endpoint returns **raw PEM** — use `curl`, not `bao read` |
| `storage "file"` | **Removed in 2.7.0** — use `raft` or `postgresql` |
| Two `listener` blocks to give the cluster port mTLS | The cluster listener **inherits** its parent listener's TLS settings — firewall port 8201 instead |

> 💡 **Reproduce the checks yourself:**
> ```bash
> # 1. Get the binary
> curl -sL -o bao.tgz \
>   https://github.com/openbao/openbao/releases/download/v2.7.1/openbao_2.7.1_linux_amd64.tar.gz
> tar xzf bao.tgz && sudo install -m0755 bao /usr/local/bin/bao
>
> # 2. Validate any config
> bao operator validate-config -config=./openbao.hcl
>
> # 3. Prove the engine/auth tables
> bao server -dev &
> for t in oidc jwt approle userpass kubernetes cert ldap kerberos radius github; do
>   bao auth enable -path="t_$t" "$t" >/dev/null 2>&1 && echo "built-in: $t" || echo "plugin:   $t"
> done
> ```


---

## The one-paragraph summary

OpenBao is a **secret manager**: it holds your passwords, API keys, certificates
and encryption keys encrypted at rest, decides *who* may read *which* of them
through code-reviewable policies, hands out **short-lived dynamic credentials**
instead of long-lived ones, and writes **an immutable audit log** of every single
request. Your applications never need to know a static secret; they ask OpenBao
"give me a Postgres credential that expires in an hour" and OpenBao creates a
real database user, hands it over, and deletes the user when the lease expires.
That single loop — *short-lived, auditable, automatically revoked* — is the whole
product. Everything else is detail.
