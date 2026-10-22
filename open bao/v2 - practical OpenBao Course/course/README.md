# OpenBao: From Zero to Production

**A hands-on course for the Meridian AI platform team.**

Everything here is executed against a real **OpenBao v2.7.1** server. Every
command, every error message, and every output block in these modules was run
and captured — not copied from a tutorial. Where the behaviour of 2.7 differs
from older docs (and it does, in several important ways), the difference is
called out explicitly.

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

## The modules

| # | Module | What you'll build | Production outcome |
|---|---|---|---|
| 01 | [Foundations](modules/01-foundations/) | Init, seal/unseal, break-glass recovery | A vault that survives restarts and stolen disks |
| 02 | [KV v2 Secrets](modules/02-kv-secrets/) | Gemini API key store, metadata, CAS, TTL | Versioned, auditable, safe-to-share secrets |
| 03 | [Policies & ACLs](modules/03-policies/) | Least-privilege policies, default/root | Apps can read *only* their own keys |
| 04 | [Namespaces, Entities & Leases](modules/04-namespaces-entities/) | Multi-tenancy, identity, lease lifecycle | Tenant isolation + understand token lifetimes |
| 05 | [Auth Methods, MFA & OIDC](modules/05-auth-mfa-oidc/) | userpass, AppRole, OIDC↔Keycloak, TOTP | Humans and machines each authenticate correctly |
| 06 | [Crypto Tooling](modules/06-crypto-tooling/) | wrap/unwrap, random, hash, Transit | Encrypt data that never enters the store |
| 07 | [App Integration](modules/07-app-integration/) | FastAPI + Docker secret injection | Real app, real container, no secrets on disk |
| 08 | [Other Engines](modules/08-other-engines/) | PKI, SSH, Transit, TOTP, Postgres | Dynamic secrets instead of static ones |
| 09 | [Production Hardening](modules/09-production-hardening/) | TLS, HA, audit, backups, CI/CD | Ready for Meridian AI's real environment |

---

## Setup (once)

```bash
git clone <your-repo> meridian-openbao-course
cd meridian-openbao-course/lab

cp -r config config.example.bak   # keep a pristine copy
docker compose up -d openbao
./scripts/init-lab.sh
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

---

## Ground rules

1. **Never `latest`.** The image is pinned to `2.7.1`.
2. **Never `-dev` after Module 01.** It skips the seal, which is the point.
3. **Never commit a token.** `lab/secrets/` is gitignored.
4. **Prefer the CLI.** The GUI is equivalent for most operations, but the CLI
   is what CI/CD uses, and it exposes things the GUI hides.
5. **Read the errors.** Most OpenBao errors are precise. The course
   deliberately includes the confusing ones and explains them.

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

---

## Module 01 → 02

Module 01 is complete when you can unseal from a cold restart and mint a new
root token without panicking. Continue to
**[Module 02 — KV v2 Secrets](modules/02-kv-secrets/)**.
