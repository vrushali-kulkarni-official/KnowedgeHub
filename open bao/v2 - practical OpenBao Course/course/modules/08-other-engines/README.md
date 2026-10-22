# Module 08 — PKI, SSH, Transit, TOTP & the Postgres Database Engine

> **Where we are.** KV v2 stores *static* secrets. But production systems
> shouldn't have static secrets at all where they can be avoided. This
> module covers **dynamic secrets** — credentials OpenBao generates,
> leases, and revokes on a schedule.

**Status: outline — full lesson in a later session.**

---

## 1. What built-in engines exist in 2.7.1

Verified from the live plugin catalog:

```
SECRET ENGINES          AUTH METHODS
kv                      approle
pki                     cert
ssh                     jwt
transit                 kubernetes
totp                    oidc
database                userpass
rabbitmq
kubernetes
```

Plus the `postgresql-database-plugin`, `redis-database-plugin`,
`mysql-database-plugin` variants, and `valkey-database-plugin` under the
`database` type.

⚠️ **Not built-in:** `aws`, `gcp`, `azure`, `ad`, `ldap`, `consul`,
`nomad` secret engines, and `ldap`/`kerberos` auth. These moved to
`openbao-plugins` and must be installed as external plugins. The KMS
seals (`awskms`, `gcpckms`, `azurekeyvault`, `alicloudkms`, `ocikms`,
`pkcs11`) are **also** external plugins as of 2.6/2.7.

**How to check on your own server:**
```bash
bao plugin list
```

---

## 2. The Postgres database engine — dynamic credentials

Instead of a static password in KV v2, OpenBao **creates a real Postgres
role** on demand, leases it, and drops it when the lease expires.

```bash
bao secrets enable -path=ai/database database
bao write ai/database/config/meridian-postgres \
  plugin_name=postgresql-database-plugin \
  allowed_roles=meridian_ai_app \
  connection_url="postgresql://{{username}}:{{password}}@postgres:5432/meridian_ai?sslmode=require" \
  username="meridian_vault_admin" \
  password="..." \
  verify_connection=true

bao write ai/database/roles/meridian-ai-app \
  db_name=postgresql \
  creation_statements='CREATE ROLE "{{name}}" WITH LOGIN PASSWORD '\''{{password}}'\'' VALID UNTIL ...; GRANT ...;' \
  default_ttl=1h max_ttl=24h
```

Read a credential:
```bash
bao read ai/database/creds/meridian-ai-app
```

**The magic:** the returned username is something like
`v-token-meridian-ai-app-Xy9Kp2Lm4Qw7`. It works *right now* and stops
working when the lease expires. Postgres itself has no idea OpenBao
exists — except that OpenBao used an admin role to create the user.

**Audit trail:** every dynamic credential issuance is in the audit log.

---

## 3. PKI — your own internal certificate authority

```bash
bao secrets enable -path=ai/pki pki
bao secrets tune -max-lease-ttl=8760h ai/pki
bao write ai/pki/root/generate/internal \
  common_name="Meridian AI Internal CA" \
  issuer_name="meridian-ai-ca-2026" \
  key_type=ec \
  key_bits=256
```

Then an intermediate CA and role definitions. Issue a leaf cert:
```bash
bao write ai/pki/issue/ai-harness \
  common_name="ai-harness.meridian-ai.internal" \
  alt_names="ai-harness.meridian-ai.internal,ai-harness" \
  ttl=72h
```

**2.7 additions:** ML-DSA (FIPS 204) post-quantum signatures, and
**External Keys** — sign with a key that lives in an HSM/KMS and never
enters OpenBao.

---

## 4. SSH — one-time credentials for humans

```bash
bao secrets enable -path=ai/ssh ssh
bao write ai/ssh/config/generate_signing_key=true
bao write ai/ssh/roles/meridian-admin \
  key_type=ca \
  default_user=meridian \
  allow_user_certificates=true
```

An engineer logs in with their **existing** corporate SSH key and gets a
short-lived cert. No per-user `authorized_keys` management, and every
login is attributable to an OpenBao entity.

---

## 5. TOTP as a secret engine

```bash
bao secrets enable -path=ai/totp totp
bao write ai/totp/keys/alice-rahman type=otp
```

Used for MFA on human logins.

---

## 6. The comparison table

| Engine | Secret type | Lifetime | Revocation |
|---|---|---|---|
| KV v2 | Static value | Until rotated | Manual |
| Database | Dynamic role | Lease (1–24h) | Automatic on expiry |
| PKI | Dynamic cert | Lease (h–y) | Automatic + CRL |
| SSH | Dynamic cert | Lease (h) | Automatic |
| Transit | Encrypted data | n/a (key) | Key rotation |

**The strategic point:** static secrets are a liability. Every module you
can move from "static" to "dynamic" removes an entire class of incident
(credential leaked and never rotated because nobody noticed).

---

**Next:** [Module 09 — Production Hardening](09-production-hardening/)
