# Level 4 — The Secrets Engines

> **Goal:** you can pick the right engine for every job, configure it properly,
> and use it in a way that survives contact with a real production system.

---

## 4.0 Choosing the right engine

```
  "I need to store an API key"                    →  KV v2
  "I need to encrypt data my app stores in S3"     →  Transit
  "I need internal TLS certs for my services"      →  PKI
  "I need a Postgres user that expires"            →  Database
  "I need step-up MFA codes"                       →  TOTP
  "I need to replace authorized_keys"              →  SSH
  "I need to pass a secret through a workflow"     →  Cubbyhole
  "I need a credential but must not see it"        →  Response Wrapping
  "I need to encrypt it myself and OpenBao holds
   the key in an HSM"                              →  Transit + External Keys (2.7)
```

---

## 4.1 KV v2 — the workhorse

### Enable and configure

```bash
bao secrets enable -path=secret kv-v2

# Tune
bao secrets tune -default-lease-ttl=24h -max-lease-ttl=168h secret
```

> 💡 KV v2 doesn't use leases, but `max-lease-ttl` **does** bound how long a
> *deleted-but-not-destroyed* version can be undeleted, and it bounds the
> `cas` window. Set it deliberately.

### The path anatomy

```
secret/data/myapp          ← the VALUE
secret/metadata/myapp      ← versions, created_time, deletion_time, custom_metadata
secret/delete/myapp        ← mark a version deleted
secret/undelete/myapp      ← restore a deleted version
secret/destroy/myapp       ← permanently destroy a version
secret/config              ← engine-wide config (max_versions, cas_required)
```

### Versioning in practice

```bash
bao kv put -mount=secret myapp password=v1
bao kv put -mount=secret myapp password=v2
bao kv put -mount=secret myapp password=v3

bao kv get -mount=secret -version=1 myapp    # → v1
bao kv get -mount=secret myapp               # → v3 (latest)
bao kv get -mount=secret -version=2 myapp    # → v2

bao kv metadata get -mount=secret myapp
# → { "current_version": 3, "versions": { "1": {...}, "2": {...}, "3": {...} } }
```

### Deletion semantics (this confuses everyone)

```bash
bao kv delete -mount=secret myapp          # soft delete: marks version deleted
bao kv get -mount=secret myapp             # → Error: data deleted
bao kv undelete -mount=secret myapp        # → version is back
bao kv destroy -mount=secret myapp         # → data permanently gone (current version)
bao kv metadata delete -mount=secret myapp # → ALL versions + metadata gone
```

Each of these operations is a **separate path** and therefore a **separate
capability**. That is a feature: you can let a service read values, let a
pipeline soft-delete, and forbid permanent destruction except for a break-glass
role.

### Check-and-Set (CAS) — optimistic concurrency

CAS prevents a lost update when two writers race.

```bash
# Read the current version number
CURRENT=$(bao kv get -mount=secret -field=metadata.version myapp)

# Write only if nobody else has written since
bao kv put -mount=secret myapp password=v4 cas=$CURRENT
# → if someone else wrote first, this FAILS

# Or require CAS on every write to the engine
bao write secret/config cas_required=true
```

> 💡 CAS is essential for "the deploy pipeline updates the secret" workflows
> where a human might also be editing it.

### `max_versions` and pruning

```bash
bao write secret/config max_versions=5
```

Old versions beyond the limit are pruned automatically. If you need long
audit history of secret *values*, use a *separate* audit trail — don't keep
hundreds of KV versions around.

### Custom metadata

```bash
bao kv put -mount=secret myapp password=v1 \
  custom_metadata=owner=platform \
  custom_metadata=rotated_at=2026-10-20
```

### The sub-key pattern (recommended)

```bash
bao kv put -mount=secret myapp/db     db_host=postgres db_port=5432 db_user=app db_password=...
bao kv put -mount=secret myapp/llm    provider=anthropic api_key=sk-ant-...
bao kv put -mount=secret myapp/jwt    signing_key=... issuer=...

bao kv get -mount=secret myapp        # → folder listing
bao kv get -mount=secret myapp/db     # → just the db bundle
```

This gives you **per-sub-path policies**, which means the LLM service can read
`secret/data/myapp/llm` and cannot read `secret/data/myapp/db`.

### KV v1 vs v2 — final word

Use **v2**. Always. v1 has no versioning, no CAS, no metadata separation, and
you cannot retrofit it. If you inherit a v1 mount, migrate it:

```bash
# v1 → v2 migration is supported via the upgrade guide
# (read it, do not improvise — the mount type must change)
bao secrets tune -default-lease-ttl=0 secret    # v1 is non-versioned
```

> ⚠️ Actually migrating v1→v2 requires the documented upgrade procedure
> (read `/docs/guides/upgrade/`), not a casual `enable`. Do it in a lab first.

---

## 4.2 Transit — encryption as a service

**The principle: your application never holds the encryption key.**

```
   app:  plaintext ──▶ bao transit/encrypt ──▶ ciphertext (stored in S3/DB)
   app:  ciphertext ──▶ bao transit/decrypt ──▶ plaintext
                              │
                        key never leaves OpenBao
```

### Setup

```bash
bao secrets enable -path=transit transit

# Create a key
bao write transit/keys/app-data type=aes256-gcm96
bao write transit/keys/app-data \
    type=aes256-gcm96 \
    convergent_encryption=true \
    min_decryption_version=0 \
    deletion_allowed=false
```

| Key type | Use |
|---|---|
| `aes128-gcm96`, `aes256-gcm96` | General purpose, authenticated encryption |
| `chacha20-poly1305` | Fast, no AES-NI requirement |
| `ed25519` | Signatures |
| `ecdsa-p256` / `ecdsa-p384` | Signatures |
| `rsa-2048` / `rsa-4096` | Signatures + encryption (wrap/unwrap) |
| `mldsa-44/65/87` | **2.7.0** — post-quantum signatures (NIST FIPS 204) |

### Encrypt / decrypt

```bash
# Encrypt (input is base64)
CIPHER=$(bao write -format=json transit/encrypt/app-data \
          plaintext=$(echo -n "sensitive" | base64) | jq -r .data.ciphertext)
# → vault:v1:<base64>

# Decrypt
bao write -format=json transit/decrypt/app-data ciphertext="$CIPHER" | jq -r .data.plaintext
# → (base64) → decode with `base64 -d`

# Deterministic (convergent) encryption — same input → same ciphertext
bao write -format=json transit/encrypt/app-data \
    plaintext=$(echo -n "sensitive" | base64) | jq -r .data.ciphertext
# → vault:v1:<same ciphertext>   (because convergent_encryption=true)
```

> 💡 **Convergent encryption** is what lets you do a *searchable* encrypted
> field: you can encrypt a column and still index it, because equal plaintexts
> produce equal ciphertexts. Trade-off: it leaks equality (which is inherent to
> searchable encryption).

### Key versioning and rotation

```bash
bao read transit/keys/app-data
# → { "latest_version": 3, "min_decryption_version": 0, ... }

bao write -format=json transit/keys/app-data/rotate   # → latest_version: 4
bao write transit/keys/app-data/min_decryption_version=2   # archive v0,v1
```

**Key rotation is non-destructive**: old ciphertext still decrypts because it's
tagged `vault:v1:...` (v1 = key *version* 1).

```bash
# Re-encrypt everything with the latest key (batch rewrap)
bao write transit/rewrap/app-data
```

### Datakey generation — the "envelope encryption" pattern

```bash
bao write -format=json transit/datakey/plaintext/app-data bits=256
```

```json
{
  "plaintext": "AAAAB3NzaC1yc2EAAAADAQABAAABAQ...",   // the actual key
  "ciphertext": "vault:v1:..."                          // the key, encrypted
}
```

The app encrypts data with the plaintext datakey (kept only in memory), stores
only the ciphertext, and stores the *encrypted* datakey alongside. To decrypt,
it asks OpenBao to decrypt the datakey. **The key is never persisted in the
clear**, and OpenBao never sees the data.

### Other transit powers

```bash
bao write transit/hash sha256      # hash input
bao write transit/hmac/sha256      # keyed HMAC
bao write transit/sign/mykey       # sign
bao write transit/verify/mykey     # verify
bao write transit/random/32        # 32 random bytes
bao write transit/export/mykey     # export key material (needs strict policy!)
bao write transit/backup/mykey     # backup key (for disaster recovery)
bao write transit/restore/mykey    # restore
bao write transit/trim/mykey       # permanently trim key versions
```

> 🔒 **`transit/export` and `transit/backup` are the most dangerous paths in
> OpenBao.** Export gives you the raw key. Backup gives you key material that
> can restore the key on another cluster. Both should be on a separate, tightly
> controlled policy — ideally break-glass only, and always audited.

### Transit for your AI harness

Your LangChain app might need to encrypt prompts, RAG documents, or cached
embeddings before writing them to Postgres/Redis. Transit is the right tool:

```python
import base64, hvac

client = hvac.Client(url=os.environ["BAO_ADDR"], token=os.environ["BAO_TOKEN"])

def encrypt(plaintext: str) -> str:
    b64 = base64.b64encode(plaintext.encode()).decode()
    return client.secrets.transit.encrypt_data(name="rag-documents", plaintext=b64)["ciphertext"]

def decrypt(ciphertext: str) -> str:
    b64 = client.secrets.transit.decrypt_data(name="rag-documents", ciphertext=ciphertext)["plaintext"]
    return base64.b64decode(b64).decode()
```

---

## 4.3 PKI — your internal certificate authority

### The three-tier model (the only sane production model)

```
┌─────────────────────────────────────────────────────────────┐
│  OFFLINE ROOT CA                                            │
│  • Generated on an air-gapped machine                        │
│  • 10–20 year lifetime                                      │
│  • Private key NEVER in OpenBao, NEVER on a server           │
│  • Used exactly twice: to sign the intermediate              │
└───────────────────────────┬─────────────────────────────────┘
                            │ signs
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  INTERMEDIATE CA  (lives in OpenBao)                        │
│  • 1–5 year lifetime                                        │
│  • Signs leaf certificates                                  │
│  • Private key in OpenBao (or in an HSM via External Keys)  │
└───────────────────────────┬─────────────────────────────────┘
                            │ signs
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  LEAF CERTIFICATES                                          │
│  • 24 hours – 7 days                                        │
│  • Auto-renewed by the client                               │
│  • Revocation is a non-issue: they expire fast               │
└─────────────────────────────────────────────────────────────┘
```

### Build it

> ⚠️ **Three PKI gotchas that will bite you** (all verified against 2.7.1):
>
> 1. **`bao secrets tune -max-lease-ttl=...` FIRST.** The CA's lifetime is
>    capped by the mount's max lease TTL (default 768h = 32 days). If you
>    generate a 10-year root before tuning, OpenBao caps it and warns:
>    *"TTL '87600h0m0s' is longer than permitted maxTTL '768h0m0s', so maxTTL
>    is being used"*. The certificate is then only 32 days old.
> 2. **`key_bits` is an INTEGER, not a string.** `key_bits=ecdsa-p521` fails
>    with *"error converting input for field 'key_bits': '' cannot parse
>    value as 'int'"*. Use `key_type=ec` + `key_bits=521`.
> 3. **`issuer_name` cannot contain spaces.** Use hyphens: `Corp-Offline-Root`.
>    Or just omit `issuer_name` — the official quick-start does.

**Step 1 — the root CA (run once, offline):**

```bash
bao secrets enable -path=pki_root pki
bao secrets tune -max-lease-ttl=87600h pki_root     # 10 years — DO THIS FIRST

bao write pki_root/root/generate/internal \
    common_name="Corp-Offline-Root" \
    issuer_name="Corp-Offline-Root" \
    key_type=ec \
    key_bits=521 \
    ttl=87600h
```

> 💡 The root becomes the **default issuer** automatically once generated, so
> you can immediately issue from it. You can check with:
> ```bash
> bao read pki_root/issuer/default
> ```

Export the root cert (public, safe) and the private key (**very sensitive**):

```bash
# The generated cert + key come back in the write response:
bao write -format=json pki_root/root/generate/internal \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['certificate'])" > root-ca.crt

# The CA chain endpoint serves raw PEM (not JSON) — use curl:
curl -s --cacert ca.crt https://openbao:8200/v1/pki_root/cert/ca > ca-chain.crt

# The private key (⚠️ CONTAINS THE PRIVATE KEY)
bao read pki_root/root/export > root-ca-bundle.json
```

> 🔒 The root private key must be moved **off** the OpenBao server immediately
> and stored offline. If it stays in OpenBao, your "offline root" is a lie.

**Step 2 — the intermediate CA (in OpenBao):**

```bash
bao secrets enable -path=pki_int pki
bao secrets tune -max-lease-ttl=43800h pki_int      # 5 years — DO THIS FIRST

# Generate the intermediate's CSR (writes csr + key_id)
bao write -format=json pki_int/intermediate/generate/internal \
    common_name="Corp-Intermediate" \
    issuer_name="Corp-Intermediate" \
    key_type=ec \
    key_bits=384 \
    ttl=43800h > csr.json

# Extract just the CSR to a file (the `csr=@file` syntax needs a real file)
python3 -c "import json;print(json.load(open('csr.json'))['data']['csr'])" > csr.pem

# Sign it with the root (this is the ONLY time the root key is used)
bao write -format=json pki_root/root/sign-intermediate \
    csr=@csr.pem \
    format=pem_bundle \
    ttl=43800h > signed.json

# Extract the signed certificate
python3 -c "import json;print(json.load(open('signed.json'))['data']['certificate'])" > signed-intermediate.crt
```

**Step 3 — import the signed intermediate:**

```bash
bao write pki_int/intermediate/set-signed \
    certificate=@signed-intermediate.crt
```

**Step 4 — a role for your services:**

```bash
bao write pki_int/roles/myapp \
    allowed_domains="myapp.internal" \
    allowed_subdomains="true" \
    allow_bare_domains="true" \
    allow_localhost="true" \
    max_ttl="72h" \
    key_type="ec" \
    key_bits=256 \
    server_flag="true" \
    client_flag="true" \
    use_csr_common_name="true" \
    use_csr_sans="true" \
    key_usage="DigitalSignature,KeyAgreement" \
    ext_key_usage="ServerAuth,ClientAuth"
```

**Step 5 — issue:**

```bash
# Returns certificate, private_key, ca_chain, serial_number, expiration, ...
bao write -format=json pki_int/issue/myapp \
    common_name="myapp.internal" \
    ttl="24h" > issued.json

python3 -c "import json;d=json.load(open('issued.json'))['data'];print(d['certificate'])" > cert.pem
python3 -c "import json;d=json.load(open('issued.json'))['data'];print(d['private_key'])" > key.pem
```

> 💡 `bao write -f` (raw format) does **not** reliably give you a single bare
> value for multi-field responses. Use `-format=json` and parse it — that's
> what the scripts in this course do.

Or let OpenBao generate the whole thing (key + CSR + cert) in one call —
which is what the command above already does.

**Step 6 — publish the issuing URLs and grab the chain:**

```bash
bao write pki_int/config/urls \
    issuing_certificates="$BAO_ADDR/v1/pki_int/ca" \
    crl_distribution_points="$BAO_ADDR/v1/pki_int/crl"

# The CA chain endpoint serves raw PEM, not JSON — use curl:
curl -s --cacert ca.crt "$BAO_ADDR/v1/pki_int/ca" > ca-chain.crt
```

> 💡 **Distribute `ca-chain.crt` (intermediate + root) to every client** as the
> trust anchor. Clients validate the leaf against it. The root cert alone is
> NOT enough — you need the chain. And the chain endpoint returns **raw PEM**,
> so `bao read` (which expects JSON) will fail on it — use `curl`.

### PKI roles — the important knobs

| Parameter | Meaning | Recommendation |
|---|---|---|
| `allowed_domains` | Exact list of permitted CNs | Always set it. Empty = any domain. |
| `allowed_subdomains` | Allow `*.domain` | Only if you need it |
| `allow_bare_domains` | Allow `domain` without prefix | Usually `true` alongside subdomains |
| `allow_localhost` | Allow `localhost` | Dev only |
| `allow_ip_sans` | Allow IP SANs | Usually `true` for k8s |
| `allow_any_name` | ⚠️ Allow **any** common name | **Never in production** |
| `enforce_hostnames` | Reject CNs not matching allowed list | `true` |
| `allow_bare_domains` + `use_csr_sans` | SAN handling | Understand before enabling |
| `server_flag` / `client_flag` | EKU | Set both for mTLS |
| `max_ttl` | Max leaf lifetime | 72h–168h |

> 🚨 **`allow_any_name = true` is the PKI equivalent of `path "*" { capabilities
> = ["*"] }`.** It lets anyone request a cert for `*.corp.internal` and MITM
> your services. Never enable it outside a lab.

### PKI in 2.7.0 — two big upgrades

**ML-DSA (post-quantum, NIST FIPS 204):**

```bash
bao write pki_int/roles/pqc-app \
    key_type="mldsa-44" \
    signature_bits=0 \
    max_ttl="24h"
```

> ⚠️ The 2.7.0 notes carry an explicit warning: *"Go's OCSP implementation does
> not support ML-DSA so will be unusable with ML-DSA typed issuers."* If you
> rely on OCSP/CRL revocation checking, ML-DSA roles will not work with it.

**External Keys — PKI private key in an HSM (2.7.0):**

```bash
# Map a mount to an HSM/KMS-backed key
bao write sys/external-keys/pki_int \
    keys=my-hsm-key \
    backend=kms \
    # ... backend-specific parameters
```

The PKI engine then signs with the HSM key and **never holds the private key
in OpenBao at all**. See Level 8.

### Cert revocation

```bash
# Revoke a specific serial
bao write pki_int/revoke serial=<serial>

# Build and publish a CRL
bao write pki_int/crl/config expiration=72h
bao write pki_int/crl/rotate
```

> 💡 **The real answer to revocation is short lifetimes.** If your leaves live
> 24h, a compromised cert is worthless tomorrow. Build CRL/OCSP distribution
> anyway, but don't depend on it.

### ACME (for browsers/Let\'s Encrypt-style clients)

```bash
bao write pki_int/config/acme \
    enabled=true \
    directory="https://acme-v02.api.letsencrypt.org/directory" \
    email="pki@corp.internal" \
    dns_resolver="10.0.0.53:53" \
    http_01_port=5002
```

> ⚠️ 2.7.0 security fix: *"Forbid issuance of non-validated SANs through ACME"*
> (GHSA-x8fg-h69x-p28f) — the ACME path now refuses to issue certs with SANs
> it hasn't validated. Also 2.7.0 added optional ACME client port/host
> configuration so you can run non-privileged behind a load balancer.

---

## 4.4 Database — dynamic credentials (the highest-value engine)

### Why dynamic creds change everything

```
  BEFORE:  app ──► postgres_user "app" (password in every env file, forever)
  AFTER:   app ──► OpenBao ──► postgres_user "v-token-approle-x-2026-10-20"
                              (exists for 1 hour, then deleted)
```

Benefits: no shared password, per-request attribution in the DB's own logs,
automatic revocation, no rotation job.

### Step 1 — the OpenBao admin account in Postgres

```sql
-- Run as a superuser, ONCE
CREATE ROLE openbao_admin WITH LOGIN PASSWORD 'strong-password' CREATEROLE;
GRANT CONNECT ON DATABASE appdb TO openbao_admin;
```

`CREATEROLE` is enough. **Never give it `SUPERUSER`.** OpenBao needs to create
roles; it does not need to own the database.

### Step 2 — configure the connection

```bash
bao secrets enable -path=db database

bao write db/config/postgres \
    plugin_name=postgresql-database-plugin \
    connection_url="postgresql://{{username}}:{{password}}@postgres:5432/appdb?sslmode=require" \
    username="openbao_admin" \
    password="strong-password" \
    verify_connection=true \
    allowed_roles="app,readonly"
```

> 💡 The `{{username}}:{{password}}` placeholders in `connection_url` are
> substituted from the `username`/`password` fields. Don't put the real
> credentials in the URL.

### Step 3 — define a role (a "dynamic role")

```bash
bao write db/roles/app \
    db_name=postgres \
    creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT SELECT ON ALL TABLES IN SCHEMA public TO \"{{name}}\";" \
    revocation_statements="DROP ROLE IF EXISTS \"{{name}}\";" \
    default_ttl="1h" \
    max_ttl="24h" \
    renew_statements="ALTER ROLE \"{{name}}\" VALID UNTIL '{{expiration}}';" \
    username_template="v-token-{{identity.entity.id}}-{{random 8}}-{{timestamp}}"
```

Template variables available in `creation_statements`:

| Variable | Value |
|---|---|
| `{{name}}` | The generated username |
| `{{password}}` | The generated password |
| `{{expiration}}` | Lease expiry timestamp (RHS of `VALID UNTIL`) |
| `{{creation_timestamp}}` | Issue time |
| `{{identity.entity.id}}` | Requesting entity |
| `{{random 8}}` | Random string |

> 💡 **`username_template` matters for attribution.** Include the identity ID
> so you can map a DB login back to an OpenBao entity in an incident. The
> default (`v-token-approle-...`) is fine but less useful.

### Step 4 — request credentials

```bash
bao read db/creds/app
```

```json
{
  "data": {
    "username": "v-token-abc123-8f3a-2026-10-20",
    "password": "A1b2C3d4E5f6G7h8",
    "lease_duration": 3600,
    "lease_id": "database/creds/app/..."
  }
}
```

### Step 5 — revoke

```bash
bao lease revoke database/creds/app/...
# or all of them:
bao lease revoke -prefix database/creds/
```

The revocation statement runs → the Postgres role is dropped → the credential
dies immediately. **Not "in 1 hour" — now.**

### Static roles (rotate an existing user's password)

```bash
bao write db/static-roles/app \
    db_name=postgres \
    username="legacy_app_user" \
    rotation_statements="ALTER USER \"{{name}}\" WITH PASSWORD '{{password}}';" \
    rotation_period="24h"
```

OpenBao rotates the password on a schedule and hands the current value to
whoever asks. Good for migrating legacy systems off static passwords.

### Revocation safety

> ⚠️ `revocation_statements` **must** clean up properly, or you leak database
> roles. Every leaked role is a credential you forgot about. Monitor the role
> count:
> ```sql
> SELECT count(*) FROM pg_roles WHERE rolname LIKE 'v-token-%';
> ```
> If that number is much larger than your active lease count, revocation is
> failing.

### Other database plugins

| Plugin | Notes |
|---|---|
| `postgresql-database-plugin` | ✅ Built-in |
| `mysql-database-plugin` | ✅ Built-in. 2.6.0 added **multi-host failover** (`tcp(host1:3306,host2:3306)`) |
| `cassandra-database-plugin` | ✅ Built-in |
| `influxdb-database-plugin` | ✅ Built-in |
| `valkey-database-plugin` | ✅ Built-in |
| `mongodb-database-plugin` | ❌ Removed (SSPL licence) — external plugin |
| `custom-database-plugin` | Your own, via the plugin SDK |

> 💡 **`valkey-database-plugin` exists** — that covers Redis-compatible
> servers (Valkey). See §4.9.

---

## 4.5 TOTP — step-up MFA inside OpenBao

```bash
bao secrets enable -path=totp totp

# Register a key (from a user's authenticator app enrolment URI)
bao write totp/keys/alice \
    url="otpauth://totp/OpenBao:alice@corp.com?secret=Y64VEVMBTSXCYIWRSHRNDZW62MPGVU2G&issuer=OpenBao"

# Generate a code (OpenBao acts as the authenticator)
bao read totp/code/alice

# Validate a code the user typed in
bao write totp/verify/alice code=123456
```

> 🔒 TOTP as a *generator* inside OpenBao means the **seed never leaves
> OpenBao** — a genuinely stronger design than a phone app, and fully audited.
> It also means OpenBao can be a **TOTP provider** (like Google Authenticator
> does for Google).

---

## 4.6 SSH — certificates instead of authorized_keys

```bash
bao secrets enable -path=ssh ssh

# CA key
bao write ssh/config/ca generate_signing_key=true

# Sign user keys with the CA
bao write ssh/sign/root \
    public_key=@~/.ssh/id_ed25519.pub \
    valid_principals="alice" \
    valid_after="1h" \
    valid_before="8h"

# Sign host keys
bao write ssh/sign/host \
    public_key=@/etc/ssh/ssh_host_ed25519_key.pub \
    valid_principals="myapp.internal" \
    valid_after="1h" \
    valid_before="720h"
```

Clients then trust the CA cert instead of a list of keys:

```
TrustedUserCAKeys /etc/ssh/trusted_ca.pub
```

> 💡 One CA cert replaces hundreds of `authorized_keys` entries. Revoking a
> user is a CA revocation, not editing 500 servers.

---

## 4.7 Cubbyhole — per-token private storage

Every token gets its own `cubbyhole/` — a private namespace nothing else can
read, and which is destroyed when the token dies.

```bash
bao write cubbyhole/my-step secret=intermediate-value
bao read cubbyhole/my-step
```

**Use it for multi-step flows** where a value must pass from one operation to
another without being visible in a shared path. Batch tokens don't have a
cubbyhole.

---

## 4.8 Response Wrapping — hand a secret to someone else, not to yourself

Response wrapping encrypts a response into a **single-use token** that must be
explicitly unwrapped.

```bash
# Wrap (any read command supports -wrap-ttl)
bao kv get -mount=secret -wrap-ttl=60s myapp
```

```json
{
  "wrap_info": {
    "token": "hvs.CAESIJ...",
    "accessor": "6f1c...",
    "ttl": 60,
    "creation_time": "...",
    "creation_path": "secret/myapp"
  }
}
```

```bash
# Unwrap — single use, and it deletes itself
bao unwrap hvs.CAESIJ...
```

**Why it matters:**

1. The secret never appears in a log, a shell history, or a terminal scrollback.
2. The token is **single-use** — replaying it fails.
3. It's **time-boxed**.
4. You can **hand it to a broker** (a message queue, a ticket, a person) who
   then unwraps it and gets the secret — without you revealing it.

```bash
# Server-side: wrap a read
WRAPPED=$(bao read -field=wrap_info.token -wrap-ttl=60s secret/myapp)
# ... pass $WRAPPED through a queue ...
# Consumer side:
bao unwrap "$WRAPPED"
```

### Wrapping TTL control in policies

```hcl
path "secret/data/very-sensitive" {
  capabilities = ["read"]
  min_wrapping_ttl = "30s"
  max_wrapping_ttl = "120s"
}
```

Prevents someone wrapping it for 30 days.

### Cubbyhole vs wrapping vs control groups

| Mechanism | Who can unwrap | When it dies | Use for |
|---|---|---|---|
| **Cubbyhole** | Only the token's own identity | Token dies | Private scratch space |
| **Response wrapping** | Anyone with the wrap token | TTL, or on unwrap | Passing a secret through a channel |
| **Control groups** (2.7.0) | Only after a second person approves | TTL | Guarding access behind two-person rule |

---

## 4.9 Redis / Valkey — what actually exists

> **Straight answer: there is no `redis-database-plugin` in OpenBao 2.7.1.**

What *does* exist:

| Option | Description | Trade-off |
|---|---|---|
| **`valkey-database-plugin`** | ✅ Built-in. Valkey is the Linux Foundation's Redis fork. | Works against Valkey; against Redis it depends on the commands used. |
| **Static KV v2** | Store the Redis password in KV. | Simple, but static. |
| **Redis ACL user rotation via `transit`/scripts** | You'd script the rotation yourself. | You own the complexity. |
| **The `redis` auth method** | ❌ Not an OpenBao thing. | n/a |

### The pragmatic recommendation for your stack

**Use KV v2 with a short TTL and a rotation process** for Redis, and treat the
Redis password as a *lower-value* secret (Redis is usually network-isolated
and bound to a private network anyway).

```bash
bao kv put -mount=secret myapp/redis \
    host=redis \
    port=6379 \
    password='...redis-password...' \
    tls=true

bao policy write redis-reader - <<'EOF'
path "secret/data/myapp/redis" {
  capabilities = ["read"]
}
EOF
```

**Better**: issue Redis **ACL users** with per-service permissions and rotate
them on a schedule via a small script that calls `ACL SETUSER` using the
OpenBao-stored admin password. That gets you the *dynamic credential* property
even without a dedicated plugin.

```bash
# Example rotation script (run from a controlled environment)
PASSWORD=$(bao kv get -mount=secret -field=password myapp/redis/admin)
redis-cli -a "$PASSWORD" ACL SETUSER "app-$SERVICE" on '>~app:*' '+@read' '+@write' '+ping' '+get'
redis-cli -a "$PASSWORD" ACL SAVE
```

> 🔒 **Never grant `+@all` to a service ACL user.** Scope the command
> categories and key patterns.

**Postgres, by contrast, *does* have a first-class dynamic credential
engine** — use it there (§4.4). That asymmetry is real: Postgres dynamic creds
are a solved problem in OpenBao; Redis dynamic creds are not, out of the box.

---

## 4.10 Engine tuning and lifecycle

```bash
bao secrets list -detailed
bao secrets tune -default-lease-ttl=1h -max-lease-ttl=24h db
bao secrets tune -listing-visibility=false secret     # hide from `bao secrets list`
bao secrets disable db        # revokes all leases + deletes the data
bao secrets move db db-old    # ⚠️ revokes all leases (leases are path-bound)
```

> ⚠️ **`bao secrets move` revokes every lease** under the old path, because
> leases are bound to the path they were created at. Same for `disable`.

---

## 4.11 Level 4 checkpoint

1. Why does KV v2 need `data/` AND `metadata/` paths in your policy?
2. What does `cas` protect you from, and what happens if you lose the race?
3. Why is `transit/export` the most dangerous path in OpenBao?
4. What is the difference between a KV v2 "delete" and a "destroy"?
5. Draw the three-tier PKI model. Which tier holds the private key that signs
   leaves? Which one must be offline?
6. What privilege does OpenBao's Postgres admin account need, and what should
   you never give it?
7. How do you revoke a dynamic database credential *immediately*?
8. What is response wrapping good for, and what makes it safe?
9. Is there a Redis dynamic-credentials engine in OpenBao 2.7.1? What do you
   do instead?
10. Why should `allow_any_name` never be enabled on a PKI role?

**Next → [Level 5: SECURITY-HARDENING.md](05-SECURITY-HARDENING.md)** — the
production security baseline that everything else assumes.

---

## 4.12 Scratchpad

```
Mounts:        secret/(kv-v2) transit/ pki_root/ pki_int/ db/ totp/ ssh/
KV v2 paths:   <m>/data/<k>  <m>/metadata/<k>  <m>/delete/<k>  <m>/undelete/<k>  <m>/destroy/<k>
Transit:       transit/keys/<name>  transit/encrypt/<name>  transit/datakey/plaintext/<name>
PKI:           pki/root/generate/internal  pki/intermediate/generate/internal
               pki/root/sign-intermediate  pki/intermediate/set-signed  pki/issue/<role>
Database:      db/config/<name>  db/roles/<name>  db/creds/<role>  db/static-roles/<name>
Wrapping:      -wrap-ttl=<dur>   → bao unwrap <token>
```
