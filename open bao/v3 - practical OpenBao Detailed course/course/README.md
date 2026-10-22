# OpenBao: From Zero to Production

**A hands-on course for the Meridian AI platform team.**

Everything here is executed against a real **OpenBao v2.7.1** server. Every
command, every error message, and every output block in these modules was run
and captured — not copied from a tutorial. Where the behaviour of 2.7 differs
from older documentation (and it does, in several important ways), the
difference is called out explicitly rather than glossed over.

---

## The scenario

You just joined **Meridian AI**, a company selling an enterprise AI assistant
platform. The stack you'll be securing:

```
FastAPI + LangChain  →  Gemini API
       ↓
   Postgres  /  Redis
       ↓
   Keycloak (OIDC)  →  human login
```

A previous engineer left secrets in a committed `.env` file. Your job across
this course: stand up a production-grade OpenBao from scratch and migrate
Meridian AI onto it — without ever repeating the `.env` mistake.

We are not building a toy. Every module ends with something that would pass a
security review.

---

## What you can build by the end

Nine modules, and at the end of them you have:

| | What exists when you finish |
|---|---|
| 🗄️ | A **running, unsealed, production-shaped OpenBao 2.7.1** in Docker, with a declarative audit device and a pinned storage backend — and you can recover it from a cold restart without panicking |
| 🔑 | Meridian AI's **Gemini key, Postgres password, Redis password and Keycloak client secret** in a versioned KV v2 store with check-and-set writes, custom metadata and rollback |
| 🛡️ | **Five least-privilege policies** and **five identities**, so the AI harness can read the Gemini key and *provably cannot* read the database password |
| 🏢 | **Three namespaces** (`tenant-alpha`, `tenant-atlas`, `tenant-secure`) with real isolation, plus an identity store with entities, aliases and groups |
| 👤 | **Two working login paths** — AppRole for machines, userpass/OIDC for humans — with TOTP MFA enforced through `identity/mfa/login-enforcement` |
| 🔐 | **Transit, wrapping, hashing and randomness** as tools, so data that must never enter the secret store can still be encrypted, and values can be passed through a channel that must not see them |
| 🚀 | A **real FastAPI service in a real container** that pulls its secret at start-up, re-reads it on rotation without a restart, and never writes it to disk |
| 📜 | **A PKI, an SSH signer and a Postgres database engine**, so leaf certificates, SSH certificates and database credentials are issued on demand rather than stored |
| 🏭 | **TLS, HA, backups, monitoring, CI/CD and a runbook** — the hardening a security review will actually ask for |

---

## The modules

| # | Module | Hands-on artefact you leave with |
|---|---|---|
| 01 | [Foundations](modules/01-foundations/) | A running, unsealed server; a break-glass script that verifies its own output |
| 02 | [KV v2 Secrets](modules/02-kv-secrets/) | The Gemini key in `ai/platform/llm/gemini`, versioned, with CAS and custom metadata |
| 03 | [Policies & ACLs](modules/03-policies/) | Five policies; a live allow/deny matrix; an AI harness that cannot read the DB password |
| 04 | [Namespaces, Entities & Leases](modules/04-namespaces-entities/) | Three isolated namespaces; an identity store; a lease lifecycle you can trace |
| 05 | [Auth Methods, MFA & OIDC](modules/05-auth-mfa-oidc/) | AppRole, userpass and OIDC login; TOTP enrolled and enforced |
| 06 | [Crypto Tooling](modules/06-crypto-tooling/) | Transit encryption, wrapping tokens, hashing, datakeys for PII in Postgres |
| 07 | [App Integration](modules/07-app-integration/) | `openbao_client.py`, a FastAPI service and a container that never writes a secret to disk |
| 08 | [Other Engines](modules/08-other-engines/) | A PKI chain, an SSH signer, and dynamic Postgres credentials |
| 09 | [Production Hardening](modules/09-production-hardening/) | TLS, HA, audit, backups, monitoring, CI/CD, threat model and a runbook |

> Each module also ships a **`VERIFICATION.md`** — a record of exactly what was
> checked against a live 2.7.1 server, what was changed as a result, and what
> could **not** be verified. Read them when you want to know how much to
> trust a given transcript.

---

## Suggested learning order

**The straight path.** Modules 01 → 09 in order. Each one opens by saying
what the previous module left you with and closes by saying what the company
can now do that it could not before. The story only works in sequence.

**If you already run OpenBao** (or Vault), you can skim 01 and start at 02,
but **do not skip 03**. Policies are where most of the security lives, and
Module 03's live allow/deny matrix is the part of this course people tell
other people about.

**If you are here for one specific job:**

| You want to… | Go to |
|---|---|
| Fix a 403 | [03](modules/03-policies/) §2, then [Troubleshooting](docs/TROUBLESHOOTING.md) §10 |
| Stop a secret appearing in a log | [06](modules/06-crypto-tooling/) — Transit and wrapping |
| Get a secret into a container | [07](modules/07-app-integration/) |
| Issue certificates | [08](modules/08-other-engines/) §4 |
| Survive a security review | [09](modules/09-production-hardening/) |
| Look up a term | [Glossary](docs/GLOSSARY.md) |

---

## Setup (once)

```bash
git clone <your-repo> meridian-openbao-course
cd meridian-openbao-course/lab

cp -r config config.example.bak   # keep a pristine copy
docker compose up -d openbao
./scripts/init-lab.sh              # initialise + unseal
./scripts/setup-platform.sh        # mounts, policies, secrets, AppRole
```

Then:

```bash
source scripts/bao-lab.sh
use_lab_token      # exports BAO_TOKEN
bao status
```

**Requires:** Docker + Docker Compose. No local OpenBao install needed — every
`bao` command can run inside the container:

```bash
docker exec -it meridian-openbao bao status
```

### The lab scripts

| Script | What it does |
|---|---|
| `scripts/prepare-lab.sh` | Pre-flight: checks Docker, ports and directories before you start |
| `scripts/init-lab.sh` | Initialises and unseals the server; saves the root token and unseal keys to `lab/secrets/` (mode `600`) |
| `scripts/setup-platform.sh` | Mounts the engines, writes the five policies, seeds the four secrets, creates the AppRole |
| `scripts/bao-lab.sh` | Exports `BAO_ADDR` / `BAO_TOKEN` / `BAO_BIN`; provides `use_lab_token` |
| `scripts/unseal-lab.sh` | Unseals after a restart, using the saved shares |
| `scripts/refresh-credentials.sh` | Mints a fresh AppRole `secret_id` and **verifies it logs in** — the saved one expires after an hour by design |
| `scripts/break-glass.sh` | Generates a new root token and **verifies it works** before printing it |
| `validate/validate-module02.sh` | An acceptance check for Module 02 — every assertion the module makes, run for real |

> **If your app suddenly cannot authenticate.** The AI harness's `secret_id`
> has a one-hour TTL — that is the whole point of AppRole. When it expires,
> the login fails with `403 permission denied` or `400 invalid role or secret
> ID`. Run `./scripts/refresh-credentials.sh`; it mints a new one and proves
> it works before you point your app at it.

### The lab layout

```
lab/
├── config/openbao.hcl        # pinned image, declarative audit device, storage
├── scripts/                  # the six scripts above
├── policies/                 # ai-harness-service, data-pipeline-service,
│                              # platform-operator, platform-admin, secret-rotation-bot
├── app/                      # openbao_client.py, main.py, FastAPI service,
│                              # Dockerfile, and the unit + integration test suites
├── keycloak/                 # realm export for the OIDC module
├── validate/                 # acceptance checks
├── secrets/                  # gitignored; created by init-lab.sh
└── logs/                     # audit log
```

---

## Ground rules

1. **Never `latest`.** The image is pinned to `2.7.1`.
2. **Never `-dev` after Module 01.** It skips the seal, which is the point.
3. **Never commit a token.** `lab/secrets/` is gitignored.
4. **Prefer the CLI.** The GUI is equivalent for most operations, but the CLI
   is what CI/CD uses, and it exposes things the GUI hides.
5. **Read the errors.** Most OpenBao errors are precise. The course
   deliberately includes the confusing ones and explains them — and
   [the troubleshooting runbook](docs/TROUBLESHOOTING.md) reproduces sixteen of
   them verbatim.

---

## A note on versions

OpenBao tracks upstream Vault closely but diverges. Since 2.6/2.7 the
following changed and are **breaking**:

| Change | Impact |
|---|---|
| `file` storage backend **removed** (2.7.0) | Use `pebbledb` or `raft` |
| Audit devices **cannot be created via API** (2.7.0) | Use the declarative `audit` stanza in config |
| Legacy `sys/renew`, `sys/revoke*` **removed** (2.7.0) | Use `sys/leases/renew`, `sys/leases/revoke` |
| KMS seals moved to **external plugins** (2.6.0+) | `awskms`, `gcpckms`, etc. need plugins |
| Kerberos auth & LDAP secrets moved to **plugins** (2.7.0) | Not in the base binary |
| `sys/generate-root` **deprecated** (2.6.0) | Use `sys/generate-root-token` |
| Recovery keys are **auto-unseal only** | Shamir mode has none |
| `pebbledb` storage backend **added** (2.7.0) | Modern non-HA durable storage |
| Control Groups **added** (2.7.0) | Two-person approval for sensitive paths |
| ML-DSA / post-quantum **added** (2.7.0) | In PKI, Transit, and TLS |
| PostgreSQL **horizontal scalability** (2.7.0) | Read replicas for Postgres storage |

If a tutorial contradicts this table, the tutorial is wrong.

The full list of divergences — the ones that bite — is in
**[`docs/VERIFIED-FACTS.md`](docs/VERIFIED-FACTS.md)**, every entry of it
verified against a live 2.7.1 server.

---

## When you get stuck

| | |
|---|---|
| **[`docs/GLOSSARY.md`](docs/GLOSSARY.md)** | Every term the course uses, with a plain-language definition and a pointer to where it first appears |
| **[`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md)** | Sixteen errors you *will* hit, each with the exact server text, the cause and the fix |
| **[`docs/VERIFIED-FACTS.md`](docs/VERIFIED-FACTS.md)** | Where 2.7.1 behaves differently from the documentation you remember |
| **`modules/*/VERIFICATION.md`** | What was checked live for each module, and what could not be checked here |

---

## Module 01 → 02

Module 01 is complete when you can unseal from a cold restart and mint a new
root token without panicking. Continue to
**[Module 02 — KV v2 Secrets](modules/02-kv-secrets/)**.
